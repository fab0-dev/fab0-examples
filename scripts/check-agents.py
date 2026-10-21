"""Exit check for the examples: headless Claude Code runs the `story` example end to end on a small codebase,
through `/fab0:run`, against a fake tracker (FAB0_GH_FAKE) and local bare origins. Nothing reaches GitHub.

The workspace is set up as the example's README says: the home checkout `hotel` holds a copy of `story` (with `acme`
for OWNER, `hotel` for REPO and `po-user` as the product owner), beside the runs repository `hotel-runs`, each
repository with a bare `origin` of its own. The fake tracker holds the Story `acme/hotel#1`. `fab0-resolve validate`
must pass in every checkout before any session starts; if the engine is missing or older than 0.10, or a `validate`
fails, the check says why, starts no session and keeps the workspace.

1. The first session runs `/fab0:run #1 --profile cheap` in the home checkout. The run's Pipeline Run opens in
   `acme/hotel-runs`, under the Story, and its number is the run id (taken from the tracker). `spec-author` writes the
   spec, in a pull request of the runs repository, where the run waits on the product owner's gate; the product
   repository has no pull request and no commit yet.

With `--example feature`, it runs the `feature` composition instead: the parent in a product repository, and a copy
of `delivery` in a service and a web repository beside it, each factory's run in its own session and checkout, as
its people would run it. The script merges each review pull request as its owner would (the parent's requirements
and wrap-up, each team's plan), and stops when the parent's run is done. Then each team was built against what the
parent accepted, and the product repositories hold no ledger and no empty commit.

It costs tokens and needs a logged-in `claude`, `uv`, and the engine of a sibling fab0-core checkout (or $FAB0_CORE,
the path of its `plugins/fab0`), at 0.10 or later.

    uv run python scripts/check-agents.py [--example story|feature] [--model sonnet] [--budget 5] [--keep]

It prints each expectation as `ok` or `FAIL`, each session's cost and the total, and exits 0 when all passed or 1
otherwise. It removes its workspace only when all passed and `--keep` isn't given; otherwise it prints where it kept it.
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
PO = "po-user"  # the fake tracker has one user, who is every person the examples name
MIN_ENGINE = (0, 10)  # a 0.10 run: its state on the run tracker, its merges `apply`'s


def git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def engine_problem() -> str | None:
    """Why there is no engine to test: none at $FAB0_CORE or the sibling fab0-core checkout, one that doesn't run
    (no `uv`), or one older than 0.10."""
    resolve = CORE / "bin" / "fab0-resolve"
    if not resolve.is_file():
        return f"no fab0 engine at {CORE}: check out fab0-core beside this repository, or set FAB0_CORE"
    try:
        run = subprocess.run(
            [str(resolve), "--version"],
            capture_output=True,
            text=True,
            timeout=300,
            env={**os.environ, "PATH": engine_path()},
        )
        version = json.loads(run.stdout)["fab0_version"]
        found = tuple(int(n) for n in version.split(".")[:2])
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        return f"the engine at {CORE} doesn't answer `--version` (needs uv): {exc}"
    if found < MIN_ENGINE:
        return f"the engine at {CORE} is {version}: this check drives a {'.'.join(map(str, MIN_ENGINE))} run"
    return None


class Check:
    def __init__(self, keep: bool, model: str, budget: str):
        self.tmp = Path(tempfile.mkdtemp(prefix="fab0-agents-"))
        self.keep, self.model, self.budget = keep, model, budget
        self.workspace = self.tmp / "workspace"
        self.home = self.workspace / "hotel"
        self.gh = self.tmp / "gh.json"  # the check's own files stay outside the workspace
        self.cost = 0.0
        self.failures: list[str] = []

    def origin(self, github: str) -> Path:
        """The local bare repository that stands for `github` (`acme/hotel`): `origin` of its checkout, and where
        git sends https://github.com/<github> to."""
        return self.tmp / "github" / f"{github}.git"

    def publish(self, path: Path, github: str) -> None:
        """A checkout's commits, on main, and a bare `origin` that holds them."""
        git(path, "config", "user.email", "check@example.com")
        git(path, "config", "user.name", "check")
        git(path, "add", "-A")
        git(path, "commit", "-q", "-m", "start")
        bare = self.origin(github)
        bare.parent.mkdir(parents=True, exist_ok=True)
        git(self.tmp, "init", "-q", "--bare", "-b", "main", str(bare))
        git(path, "remote", "add", "origin", str(bare))
        git(path, "push", "-q", "origin", "main")

    def setup(self) -> None:
        """What the `story` README says to do, in a workspace of the check's own: the example copied into the home
        checkout `hotel`, OWNER and REPO replaced, the product owner named; the runs repository `hotel-runs` beside
        it; a bare origin for each; the Story on the fake tracker."""
        examples.assemble(ROOT / "story", self.home)
        # the plugin comes from --plugin-dir, and the marketplace of the example's settings would reach GitHub
        (self.home / ".claude" / "settings.json").unlink()
        (self.tmp / "settings.json").write_text(json.dumps(SETTINGS))
        for file in (self.home / ".fab0").rglob("*"):
            if file.is_file():
                text = file.read_text()
                if "OWNER" in text or "REPO" in text or "[USER]" in text:
                    file.write_text(
                        text.replace("OWNER", "acme")
                        .replace("REPO", "hotel")
                        .replace("[USER]", f"[{PO}]")
                    )
        for rel, body in {
            "hotel/__init__.py": "",
            "hotel/booking.py": BOOKING,
            "tests/__init__.py": "",
            "tests/test_booking.py": TESTS,
            "README.md": README,
            ".gitignore": "__pycache__/\n",  # what running the tests leaves is no one's change
        }.items():
            (self.home / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.home / rel).write_text(body)
        self.publish(self.home, "acme/hotel")
        self.start = git(self.home, "rev-parse", "HEAD")
        runs = self.workspace / "hotel-runs"
        runs.mkdir()
        git(runs, "init", "-q", "-b", "main")
        (runs / "README.md").write_text("# hotel-runs\n\nThe runs of the hotel's factories.\n")
        self.publish(runs, RUNS)
        self.runs = self.origin(RUNS)
        issue = {"title": "Extend a booking", "body": INTENT, "type": "Story"}
        self.gh.write_text(
            json.dumps({"user": PO, "issues": {"acme/hotel#1": issue}}, indent=2)
        )

    def env(self) -> dict:
        """What every session and engine command runs with: the fake tracker, the local origins in place of GitHub,
        and no `gh` login, so that nothing reaches GitHub even if a session tried."""
        github = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"url.{self.tmp / 'github'}/.insteadOf",
            "GIT_CONFIG_VALUE_0": "https://github.com/",
        }
        kept = {
            k: v
            for k, v in os.environ.items()
            if k not in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN")
        }
        return {
            **kept,
            "FAB0_GH_FAKE": str(self.gh),
            "GH_CONFIG_DIR": str(self.tmp / "gh-config"),
            "GIT_TERMINAL_PROMPT": "0",
            "PATH": engine_path(),
            **github,
        }

    def claude(self, prompt: str) -> bool:
        """One session in the home checkout, a line of its result and its cost; False when it didn't end."""
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
        try:
            run = subprocess.run(
                args,
                cwd=self.home,
                env=self.env(),
                capture_output=True,
                text=True,
                timeout=5400,
            )
        except subprocess.TimeoutExpired:
            self.expect(False, f"the session `{prompt}` ended within its timeout")
            return False
        try:
            out = json.loads(run.stdout)
        except ValueError:
            out = {"result": run.stdout + run.stderr, "is_error": True}
        cost = out.get("total_cost_usd") or 0.0
        self.cost += cost
        print(out.get("result", ""), flush=True)
        print(f"(cost ${cost:.2f}, {out.get('num_turns', '?')} turns)\n", flush=True)
        self.expect(not out.get("is_error"), f"the session `{prompt}` ended without an error")
        return not out.get("is_error")

    def resolve(self, *args: str, cwd: Path | None = None) -> dict:
        """A command of the engine, in a checkout (the home one by default): its JSON, with `ok` false and the
        output when it isn't."""
        run = subprocess.run(
            [str(CORE / "bin" / "fab0-resolve"), *args],
            cwd=cwd or self.home,
            env=self.env(),
            capture_output=True,
            text=True,
        )
        try:
            return json.loads(run.stdout)
        except ValueError:
            return {"ok": False, "error": (run.stdout + run.stderr).strip()}

    def validate(self) -> bool:
        """`validate` in every checkout of the workspace that has a wiring, before any session: what it says, if it
        fails."""
        passed = True
        for path in sorted(self.workspace.iterdir()):
            if not (path / ".fab0").is_dir():
                continue
            result = self.resolve("validate", cwd=path)
            if not result.get("ok"):
                passed = False
                errors = result.get("errors") or [result.get("error") or result]
                print(f"validate fails in {path.name}:", flush=True)
                for error in errors:
                    if isinstance(error, dict) and "message" in error:
                        error = f"{error.get('file', '')}: {error['message']}".lstrip(": ")
                    print(f"  {error}", flush=True)
            else:
                print(f"validate passes in {path.name}", flush=True)
        self.expect(passed, "the wiring validates in every checkout, before any session")
        return passed

    def status(self, run: str) -> dict:
        return self.resolve("status", run, "--profile", "cheap")

    def units(self, run: str) -> dict:
        return {u["unit"]: u for u in self.status(run).get("units", [])}

    def issues(self) -> dict:
        return json.loads(self.gh.read_text()).get("issues", {})

    def pulls(self, repo: str) -> list[dict]:
        return json.loads(self.gh.read_text()).get("pulls", {}).get(repo, [])

    def expect(self, ok: bool, what: str) -> None:
        print(("  ok    " if ok else "  FAIL  ") + what, flush=True)
        if not ok:
            self.failures.append(what)

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

    def run_of(self, story: str, repo: str) -> str | None:
        """The id of the run the Story has: the number of its Pipeline Run in `repo`, a sub-issue of the Story."""
        issues = self.issues()
        found = [
            ref
            for ref in issues.get(story, {}).get("sub_issues", [])
            if ref.startswith(f"{repo}#")
            and issues.get(ref, {}).get("type") == "Pipeline Run"
            and issues[ref].get("state_reason") != "not_planned"  # a run opened twice: the other one stands
        ]
        self.expect(
            len(found) == 1,
            f"the Story {story} has one Pipeline Run in {repo} ({found})",
        )
        if len(found) != 1:
            return None
        number = found[0].split("#")[1]
        fields = issues[found[0]].get("issue_fields", {})
        self.expect(
            fields.get("Run ID") == number,
            f"its Run ID is its number ({fields.get('Run ID')})",
        )
        return number

    def run(self) -> int:
        self.setup()
        if not self.validate():
            return self.finish()
        if not self.claude("/fab0:run #1 --profile cheap"):
            return self.finish()
        run = self.run_of("acme/hotel#1", RUNS)
        self.expect(
            self.pulls("acme/hotel") == [],
            "the product repository has no pull request yet",
        )
        product = git(self.origin("acme/hotel"), "rev-list", "--all", "--not", self.start)
        self.expect(
            product == "",
            f"the product repository has no new commit yet ({product.split()})",
        )
        if run is None:
            return self.finish()
        spec = self.units(run).get("spec", {})
        self.expect(
            spec.get("state") == "waiting" and spec.get("reason") == {"gate": "human"},
            f"the spec waits on its human gate ({spec.get('state')}, {spec.get('reason')})",
        )
        path = f"runs/hotel/{run}/spec.md"
        opened = [p for p in self.pulls(RUNS) if p.get("state", "open") == "open"]
        added = {
            p["number"]: git(
                self.runs,
                "diff",
                "--name-status",
                "--no-renames",
                f"{p.get('base', 'main')}...{p['branch']}",
            ).splitlines()
            for p in opened
        }
        spec_pulls = [n for n, changes in added.items() if f"A\t{path}" in changes]
        self.expect(
            len(spec_pulls) == 1,
            f"an open pull request of {RUNS} adds {path} ({added})",
        )
        self.expect(
            not any("tasks.yaml" in change for changes in added.values() for change in changes),
            "no task list is on any open pull request of the runs repository yet",
        )
        return self.finish()

    def finish(self) -> int:
        print(f"\ntotal cost ${self.cost:.2f}")
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
    problem = engine_problem()
    if problem:
        print(f"FAIL  {problem}", flush=True)
        return 1  # no workspace yet, and no session
    return (Composition if args.example == "feature" else Check)(
        args.keep, args.model, args.budget
    ).run()


if __name__ == "__main__":
    sys.exit(main())
