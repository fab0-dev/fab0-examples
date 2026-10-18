"""Exit check for the `story` agents: headless Claude Code runs the story example end to end on a small
codebase, through `/fab0:run`, against a fake tracker (FAB0_GH_FAKE) and a bare `origin`.

1. The first session runs the spec: `spec-author` writes the spec and the task list, which `record` checks and
   keeps in the run store. The run then waits on the product owner's gate, in a review pull request of the runs
   repository (a local bare repository, where git's `url.<base>.insteadOf` sends https://github.com/).
2. This script merges that pull request, as the product owner would.
3. The second session runs every task: `implementer` per task, `reviewer` as each task's gate. `apply` merges
   approved tasks into the run branch, and the run ends waiting for a person to merge it into main.

Then the run branch's tests must pass, and the product repository must hold only the tasks' changes.

With `--example feature`, it runs the `feature` composition instead: the parent in a product repository, and a copy
of `delivery` in a service and a web repository beside it, each factory's run in its own session and checkout, as
its people would run it. The script merges each review pull request as its owner would (the parent's requirements
and wrap-up, each team's plan), and stops when the parent's run is done. Then each team was built against what the
parent accepted, and the product repositories hold no ledger and no empty commit.

It costs tokens and needs a logged-in `claude`, and the engine of a sibling fab0-core checkout (or $FAB0_CORE,
the path of its `plugins/fab0`).

    uv run python scripts/check-agents.py [--example story|feature] [--model sonnet] [--budget 5] [--keep]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = Path(os.environ.get("FAB0_CORE", ROOT.parent / "fab0-core" / "plugins" / "fab0"))
_loader = SourceFileLoader("check_examples", str(ROOT / "scripts" / "check-examples"))
examples = module_from_spec(spec_from_loader("check_examples", _loader))
_loader.exec_module(examples)

INTENT = """Guests sometimes want to stay longer. The front desk should be able to extend a booking by a number \
of nights, as long as the room is free for those nights; when another booking is in the way, the extension is \
refused and the guest is told which dates collide. The front desk also wants a one-line text summary of a \
booking (room, check-in, check-out, nights) to read out to guests."""

BOOKING = '''"""Room bookings for a small hotel."""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class Booking:
    room: str
    check_in: date
    nights: int

    @property
    def check_out(self) -> date:
        return self.check_in + timedelta(days=self.nights)


class Hotel:
    def __init__(self) -> None:
        self.bookings: list[Booking] = []

    def is_free(self, room: str, start: date, end: date, ignore: Booking | None = None) -> bool:
        """No booking of `room` overlaps the nights from `start` up to `end`."""
        return all(
            b.room != room or b.check_out <= start or end <= b.check_in for b in self.bookings if b is not ignore
        )

    def book(self, room: str, check_in: date, nights: int) -> Booking:
        if nights < 1:
            raise ValueError("a booking is at least one night")
        if not self.is_free(room, check_in, check_in + timedelta(days=nights)):
            raise ValueError(f"room {room} is taken for some of those nights")
        booking = Booking(room, check_in, nights)
        self.bookings.append(booking)
        return booking
'''

TESTS = """import unittest
from datetime import date

from hotel.booking import Hotel


class BookTest(unittest.TestCase):
    def test_a_free_room_is_booked(self):
        hotel = Hotel()
        booking = hotel.book("101", date(2026, 5, 1), 2)
        self.assertEqual(booking.check_out, date(2026, 5, 3))

    def test_an_overlapping_booking_is_refused(self):
        hotel = Hotel()
        hotel.book("101", date(2026, 5, 1), 2)
        with self.assertRaises(ValueError):
            hotel.book("101", date(2026, 5, 2), 1)


if __name__ == "__main__":
    unittest.main()
"""

README = """# hotel

Bookings for a small hotel. Python 3.12, standard library only.

Run the tests with `python3 -m unittest discover -s tests -t .`.
"""


def engine_path() -> str:
    """The engine under test first, and no installed fab0 plugin's `bin`: a session started from one that has the
    plugin installed inherits it, and it would come first."""
    kept = [
        p
        for p in os.environ["PATH"].split(os.pathsep)
        if "/plugins/cache/fab0/" not in p
    ]
    return os.pathsep.join([str(CORE / "bin"), *kept])


SETTINGS = {
    "permissions": json.loads((ROOT / "story" / "claude-settings.json").read_text())[
        "permissions"
    ],
    "hooks": json.loads((ROOT / "story" / "claude-settings.json").read_text())["hooks"],
    # the engine under test first on PATH: an installed fab0 plugin's bin would come before --plugin-dir's
    "env": {"PATH": engine_path()},
}
RUNS = "acme/hotel-runs"
REVIEW = "fab0/hotel/1/spec"  # the spec's review branch in the runs repository


def git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


class Check:
    def __init__(self, keep: bool, model: str, budget: str):
        self.tmp = Path(tempfile.mkdtemp(prefix="fab0-agents-"))
        self.keep, self.model, self.budget = keep, model, budget
        self.home = (
            self.tmp / "workspace" / "hotel"
        )  # the check's own files stay outside the workspace
        self.gh = self.tmp / "gh.json"
        self.failures: list[str] = []

    def setup(self) -> None:
        examples.assemble(ROOT / "story", self.home)
        (
            self.home / ".claude" / "settings.json"
        ).unlink()  # the plugin comes from --plugin-dir instead
        (self.tmp / "settings.json").write_text(json.dumps(SETTINGS))
        wiring = self.home / ".fab0" / "fab0.yaml"
        text = (
            wiring.read_text()
            .replace("OWNER/REPO", "acme/hotel")
            .replace("[USER]", "[po-user]")
        )
        wiring.write_text(text.replace("owner: OWNER", "owner: acme"))
        for rel, body in {
            "hotel/__init__.py": "",
            "hotel/booking.py": BOOKING,
            "tests/__init__.py": "",
        }.items():
            (self.home / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.home / rel).write_text(body)
        (self.home / "tests" / "test_booking.py").write_text(TESTS)
        (self.home / "README.md").write_text(README)
        (self.home / ".gitignore").write_text(
            "__pycache__/\n"
        )  # what running the tests leaves is no one's change
        git(self.home, "config", "user.email", "check@example.com")
        git(self.home, "config", "user.name", "check")
        git(self.home, "add", "-A")
        git(self.home, "commit", "-q", "-m", "start")
        self.start = git(self.home, "rev-parse", "HEAD")
        bare = self.tmp / "remotes" / "hotel.git"
        bare.parent.mkdir()
        git(self.tmp, "init", "-q", "--bare", str(bare))
        git(self.home, "remote", "add", "origin", str(bare))
        git(self.home, "push", "-q", "origin", "main")
        self.runs = self.tmp / "github" / f"{RUNS}.git"
        git(self.tmp, "init", "-q", "--bare", "-b", "main", str(self.runs))
        issue = {"title": "Extend a booking", "body": INTENT, "type": "Story"}
        self.gh.write_text(
            json.dumps({"user": "po-user", "issues": {"acme/hotel#1": issue}}, indent=2)
        )

    def env(self) -> dict:
        github = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"url.{self.tmp / 'github'}/.insteadOf",
            "GIT_CONFIG_VALUE_0": "https://github.com/",
        }
        return {
            **os.environ,
            "FAB0_GH_FAKE": str(self.gh),
            "PATH": engine_path(),
            **github,
        }

    def claude(self, prompt: str) -> None:
        args = [
            "claude",
            "-p",
            prompt,
            "--plugin-dir",
            str(CORE),
            "--settings",
            str(self.tmp / "settings.json"),
        ]
        args += [
            "--setting-sources",
            "project,local",
            "--model",
            self.model,
            "--dangerously-skip-permissions",
        ]
        args += ["--max-budget-usd", self.budget, "--output-format", "json"]
        print(f"$ claude -p {prompt!r} (in {self.home})", flush=True)
        run = subprocess.run(
            args,
            cwd=self.home,
            env=self.env(),
            capture_output=True,
            text=True,
            timeout=5400,
        )
        try:
            out = json.loads(run.stdout)
        except ValueError:
            out = {"result": run.stdout + run.stderr}
        print(out.get("result", ""), flush=True)
        print(
            f"(cost ${out.get('total_cost_usd', 0):.2f}, {out.get('num_turns', '?')} turns)\n",
            flush=True,
        )

    def resolve(self, *args: str) -> dict:
        run = subprocess.run(
            [str(CORE / "bin" / "fab0-resolve"), *args],
            cwd=self.home,
            env=self.env(),
            capture_output=True,
            text=True,
        )
        return json.loads(run.stdout)

    def units(self) -> dict:
        return {
            u["unit"]: u
            for u in self.resolve("status", "1", "--profile", "cheap")["units"]
        }

    def expect(self, ok: bool, what: str) -> None:
        print(("  ok    " if ok else "  FAIL  ") + what, flush=True)
        if not ok:
            self.failures.append(what)

    def merge_spec(self) -> None:
        """What the product owner does: merge the spec's review pull request in the runs repository."""
        tree = self.tmp / "merge"
        git(self.tmp, "clone", "-q", str(self.runs), str(tree))
        git(tree, "config", "user.email", "po@example.com")
        git(tree, "config", "user.name", "po-user")
        git(tree, "merge", "-q", "--no-ff", "-m", "Merge the spec", f"origin/{REVIEW}")
        git(tree, "push", "-q", "origin", "main")
        shutil.rmtree(tree)
        data = json.loads(self.gh.read_text())
        for pull in data.get("pulls", {}).get(RUNS, []):
            if pull["branch"] == REVIEW:
                pull.update(state="merged", merged_by="po-user")
        self.gh.write_text(json.dumps(data, indent=2))

    def empty_commits(self) -> list[str]:
        """Commits on any branch of the product repository that change nothing."""
        found = []
        for line in git(self.home, "rev-list", "--all", "--parents").splitlines():
            commit, *parents = line.split()
            if len(parents) == 1 and git(
                self.home, "rev-parse", f"{commit}^{{tree}}"
            ) == git(self.home, "rev-parse", f"{parents[0]}^{{tree}}"):
                found.append(git(self.home, "log", "-1", "--format=%s", commit))
        return found

    def run(self) -> int:
        self.setup()
        self.claude("/fab0:run 1 --profile cheap")
        spec = self.units().get("spec", {})
        self.expect(
            spec.get("reason") == {"gate": "human"},
            f"the spec waits on its owner ({spec.get('reason')})",
        )
        pulls = json.loads(self.gh.read_text()).get("pulls", {})
        self.expect(
            any(p["branch"] == REVIEW for p in pulls.get(RUNS, [])),
            "the spec has a review pull request",
        )
        self.expect(
            not pulls.get("acme/hotel"),
            "the product repository has no pull request yet",
        )
        review = git(
            self.runs,
            "ls-tree",
            "-r",
            "--name-only",
            REVIEW,
            "--",
            "runs/hotel/1/review/spec",
        )
        self.expect(
            len(review.split()) == 2,
            f"the spec and the task list are on its branch ({review.split()})",
        )
        if self.failures:
            return self.finish()

        self.merge_spec()
        self.claude("/fab0:run 1 --profile cheap")
        status = self.resolve("status", "1", "--profile", "cheap")
        tasks = [u for u in status["units"] if u.get("step") == "implement"]
        self.expect(bool(tasks), f"the spec's tasks became units ({len(tasks)})")
        for unit in tasks:
            self.expect(
                unit["state"] == "done",
                f"{unit['unit']} is reviewed and merged ({unit['state']})",
            )
        self.expect(
            status["kind"] == "waiting",
            f"the run waits for a person to merge it ({status['kind']})",
        )
        tree = self.tmp / "result"
        git(self.home, "worktree", "add", "-q", "--detach", str(tree), "fab0/1/base")
        tests = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
            cwd=tree,
            capture_output=True,
        )
        self.expect(tests.returncode == 0, "the run branch's tests pass")
        files = git(
            self.home, "log", "--all", "--name-only", "--format=", "--not", self.start
        ).split()
        run_files = sorted(set(files))  # every file a commit of the run touched
        only_code = bool(run_files) and all(
            f.startswith(("hotel/", "tests/")) for f in run_files
        )
        self.expect(
            only_code, f"the run's commits touch only code and tests ({run_files})"
        )
        self.expect(
            self.empty_commits() == [],
            f"no empty commit in the product repository ({self.empty_commits()})",
        )
        stored = git(
            self.runs, "ls-tree", "-r", "--name-only", "main", "--", "runs/hotel/1"
        )
        self.expect(
            "runs/hotel/1/ledger/spec-1.yaml" in stored,
            "the ledger is in the runs repository",
        )
        self.expect(
            "runs/hotel/1/review/spec/spec.md" in stored,
            "the approved spec is in the runs repository",
        )
        return self.finish()

    def finish(self) -> int:
        print(f"\n{len(self.failures)} failed" if self.failures else "\nall passed")
        if self.keep or self.failures:
            print(f"kept in {self.tmp}")
        else:
            shutil.rmtree(self.tmp)
        return 1 if self.failures else 0


FEATURE = """Customers pay for their order by card at checkout. Done when a customer can pay by card, sees whether \
the payment went through, and the shop can see each payment's outcome."""
STORY = """A customer pays an order by card at checkout: the service takes the payment and says whether it went \
through; the web checkout asks for the card and shows the result."""
CODEBASES = {
    "service": (
        "# service\n\nThe shop's payment service. Python 3.12, standard library only. Tests: "
        "`python3 -m unittest discover -s tests -t .`.\n"
    ),
    "web": "# web\n\nThe shop's web checkout: plain HTML and JavaScript, no build step.\n",
}
PRODUCT_RUNS = "acme/product-runs"


class Composition(Check):
    """The `feature` example, with two `delivery` factories beside it."""

    def __init__(self, keep: bool, model: str, budget: str):
        super().__init__(keep, model, budget)
        self.workspace = self.tmp / "workspace"
        self.home = self.workspace / "product"
        self.cost = 0.0

    def setup(self) -> None:
        examples.assemble(ROOT / "feature", self.home)
        examples.connect(
            ROOT / "feature", self.home
        )  # service and web, beside it, committed
        (self.tmp / "settings.json").write_text(json.dumps(SETTINGS))
        for name in ("product", "service", "web"):
            path = self.workspace / name
            (
                path / ".claude" / "settings.json"
            ).unlink()  # the plugin comes from --plugin-dir instead
            wiring = path / ".fab0" / "fab0.yaml"
            text = (
                wiring.read_text()
                .replace("OWNER/REPO-runs", PRODUCT_RUNS)
                .replace("OWNER/REPO", "acme/product")
            )
            wiring.write_text(
                text.replace("OWNER/", "acme/")
                .replace("owner: OWNER", "owner: acme")
                .replace("[USER]", "[po-user]")
            )
            if name in CODEBASES:
                (path / "README.md").write_text(CODEBASES[name])
                (path / ".gitignore").write_text("__pycache__/\n")
            git(path, "config", "user.email", "check@example.com")
            git(path, "config", "user.name", "check")
            git(path, "add", "-A")
            git(path, "commit", "-q", "-m", "start")
            bare = self.tmp / "remotes" / f"{name}.git"
            git(self.tmp, "init", "-q", "--bare", "-b", "main", str(bare))
            git(path, "remote", "add", "origin", str(bare))
            git(path, "push", "-q", "origin", "main")
        self.runs = self.tmp / "github" / f"{PRODUCT_RUNS}.git"
        git(self.tmp, "init", "-q", "--bare", "-b", "main", str(self.runs))
        issues = {
            "acme/product#1": {
                "title": "Card payments",
                "body": FEATURE,
                "type": "Feature",
                "sub_issues": ["acme/product#2"],
            },
            "acme/product#2": {"title": "Pay by card", "body": STORY, "type": "Story"},
        }
        self.gh.write_text(json.dumps({"user": "po-user", "issues": issues}, indent=2))

    def claude_in(self, factory: str, run: str) -> None:
        """One session in one factory's checkout, streamed: a line per tool call as it happens, then its result."""
        args = [
            "claude",
            "-p",
            f"/fab0:run {run} --profile cheap",
            "--plugin-dir",
            str(CORE),
        ]
        args += [
            "--settings",
            str(self.tmp / "settings.json"),
            "--setting-sources",
            "project,local",
        ]
        args += [
            "--model",
            self.model,
            "--dangerously-skip-permissions",
            "--max-budget-usd",
            self.budget,
        ]
        args += ["--output-format", "stream-json", "--verbose"]
        print(f"\n=== {factory}: /fab0:run {run}", flush=True)
        proc = subprocess.Popen(
            args,
            cwd=self.workspace / factory,
            env=self.env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for line in proc.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "assistant":
                for part in event.get("message", {}).get("content", []):
                    if part.get("type") == "tool_use" and part["name"] == "Agent":
                        given = part.get("input", {})
                        print(
                            f"  - agent {given.get('subagent_type')}: {given.get('description', '')}",
                            flush=True,
                        )
            elif event.get("type") == "result":
                self.cost += event.get("total_cost_usd") or 0.0
                print(f"  = {(event.get('result') or '').strip()[:800]}", flush=True)
                print(
                    f"  (cost ${event.get('total_cost_usd') or 0:.2f}, {event.get('num_turns', '?')} turns)",
                    flush=True,
                )
        proc.wait(timeout=5400)

    def resolve_in(self, factory: str, *args: str) -> dict:
        found = subprocess.run(
            [str(CORE / "bin" / "fab0-resolve"), *args, "--profile", "cheap"],
            cwd=self.workspace / factory,
            env=self.env(),
            capture_output=True,
            text=True,
        )
        return json.loads(found.stdout)

    def has_work(self, factory: str, run: str) -> bool:
        result = self.resolve_in(factory, "status", run)
        if not result.get("ok") or result.get("kind") == "done":
            return False
        return any(
            u["state"] in ("ready", "running")
            or (u.get("reason") or {}).get("gate")
            in ("gate", "running", "ack", "merge")
            for u in result["units"]
        )

    def merge_reviews(self) -> list[str]:
        """What each owner does: merge every open review pull request of the runs repository."""
        data = json.loads(self.gh.read_text())
        merged = []
        for pull in data.get("pulls", {}).get(PRODUCT_RUNS, []):
            if pull.get("state", "open") != "open":
                continue
            tree = self.tmp / "merge"
            git(self.tmp, "clone", "-q", str(self.runs), str(tree))
            git(
                tree,
                "-c",
                "user.name=po-user",
                "-c",
                "user.email=po@example.com",
                "merge",
                "-q",
                "--no-ff",
                "-m",
                "Merge",
                f"origin/{pull['branch']}",
            )
            git(tree, "push", "-q", "origin", "main")
            shutil.rmtree(tree)
            pull.update(state="merged", merged_by="po-user")
            merged.append(pull["branch"])
        self.gh.write_text(json.dumps(data, indent=2))
        return merged

    def facts(self, project: str, run: str) -> dict:
        found = {}
        listing = git(
            self.runs,
            "ls-tree",
            "-r",
            "--name-only",
            "main",
            "--",
            f"runs/{project}/{run}/ledger",
        )
        for path in listing.split():
            found[Path(path).stem] = git(self.runs, "show", f"main:{path}")
        return found

    def run(self) -> int:
        self.setup()
        children = {"service": "1", "web": "1"}
        for _ in range(8):
            if self.resolve_in("product", "status", "2").get("kind") == "done":
                break
            merged = self.merge_reviews()
            if merged:
                print(f"merged as their owners: {', '.join(merged)}", flush=True)
            for factory, run in (("product", "2"), *children.items()):
                if self.has_work(factory, run):
                    self.claude_in(factory, run)
        issues = json.loads(self.gh.read_text())["issues"]
        status = self.resolve_in("product", "status", "2")
        self.expect(
            status.get("kind") == "done",
            f"the Story's run is done ({status.get('kind')})",
        )
        self.expect(
            issues["acme/product#1"]["sub_issues"][:1] == ["acme/product#2"],
            "the Story is under its Feature",
        )
        self.expect(
            {"acme/service#1", "acme/web#1"}
            <= set(issues["acme/product#2"].get("sub_issues", [])),
            "each team's run is a sub-issue of the Story",
        )
        feature = issues["acme/product#1"]
        follow_ups = [r for r in feature.get("sub_issues", []) if r != "acme/product#2"]
        self.expect(
            feature.get("state") == "closed" or bool(follow_ups),
            f"the Feature is closed or has follow-up Stories ({feature.get('state', 'open')}, {follow_ups})",
        )
        product = self.facts("product", "2")
        accepted = [
            n
            for n, f in product.items()
            if n.startswith("ack@") and "decision: accepted" in f
        ]
        self.expect(
            any("+contract" in n for n in accepted),
            f"the parent accepted the service's contract ({sorted(accepted)})",
        )
        self.expect(
            sum("+feedback" in n for n in accepted) >= 2,
            "the parent accepted both teams' reports",
        )
        web = self.facts("web", "1")
        built = [
            f
            for n, f in web.items()
            if n.startswith("implement-") and n[-1].isdigit() and "contract" not in n
        ]
        self.expect(
            bool(built) and all("upstream:" in f for f in built),
            "the web client was built against the contract",
        )
        for name in ("product", "service", "web"):
            self.home_, self.home = self.home, self.workspace / name
            files = git(self.home, "log", "--all", "--name-only", "--format=")
            self.expect("ledger" not in files, f"no ledger file in {name}")
            self.expect(self.empty_commits() == [], f"no empty commit in {name}")
            self.home = self.home_
        print(f"\ntotal cost ${self.cost:.2f}")
        return self.finish()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--example",
        default="story",
        choices=["story", "feature"],
        help="what to run end to end",
    )
    parser.add_argument(
        "--model", default="sonnet", help="the orchestrating session's model"
    )
    parser.add_argument(
        "--budget", default="5", help="the most one session may spend, in USD"
    )
    parser.add_argument(
        "--keep", action="store_true", help="keep the temporary project"
    )
    args = parser.parse_args()
    if not (CORE / "bin" / "fab0-resolve").is_file():
        sys.exit(
            f"no fab0 engine at {CORE}: check out fab0-core beside this repository, or set FAB0_CORE"
        )
    return (Composition if args.example == "feature" else Check)(
        args.keep, args.model, args.budget
    ).run()


if __name__ == "__main__":
    sys.exit(main())
