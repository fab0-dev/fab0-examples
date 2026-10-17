"""Exit check for the `story` agents: headless Claude Code runs the story example end to end on a small
codebase, through `/fab0:run`, against a fake tracker (FAB0_GH_FAKE) and a bare `origin`.

1. The first session runs the spec: `spec-author` writes the spec and the task list, which `record` checks and
   keeps in the run store. The run then waits on the product owner's gate, in a review pull request of the runs
   repository (a local bare repository, where git's `url.<base>.insteadOf` sends https://github.com/).
2. This script merges that pull request, as the product owner would.
3. The second session runs every task: `implementer` per task, `reviewer` as each task's gate. `apply` merges
   approved tasks into the run branch, and the run ends waiting for a person to merge it into main.

Then the run branch's tests must pass, and the product repository must hold only the tasks' changes.

It costs tokens and needs a logged-in `claude`, and the engine of a sibling fab0-core checkout (or $FAB0_CORE,
the path of its `plugins/fab0`).

    uv run python scripts/check-agents.py [--model sonnet] [--budget 5] [--keep]
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

TESTS = '''import unittest
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
'''

README = """# hotel

Bookings for a small hotel. Python 3.12, standard library only.

Run the tests with `python3 -m unittest discover -s tests -t .`.
"""

SETTINGS = {
    "permissions": json.loads((ROOT / "story" / "claude-settings.json").read_text())["permissions"],
    "hooks": json.loads((ROOT / "story" / "claude-settings.json").read_text())["hooks"],
    # the engine under test first on PATH: an installed fab0 plugin's bin would come before --plugin-dir's
    "env": {"PATH": f"{CORE / 'bin'}{os.pathsep}{os.environ['PATH']}"},
}
RUNS = "acme/hotel-runs"
REVIEW = "fab0/hotel/1/spec"  # the spec's review branch in the runs repository


def git(path: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True).stdout.strip()


class Check:
    def __init__(self, keep: bool, model: str, budget: str):
        self.tmp = Path(tempfile.mkdtemp(prefix="fab0-agents-"))
        self.keep, self.model, self.budget = keep, model, budget
        self.home = self.tmp / "workspace" / "hotel"  # the check's own files stay outside the workspace
        self.gh = self.tmp / "gh.json"
        self.failures: list[str] = []

    def setup(self) -> None:
        examples.assemble(ROOT / "story", self.home)
        (self.home / ".claude" / "settings.json").unlink()  # the plugin comes from --plugin-dir instead
        (self.tmp / "settings.json").write_text(json.dumps(SETTINGS))
        wiring = self.home / ".fab0" / "fab0.yaml"
        text = wiring.read_text().replace("OWNER/REPO", "acme/hotel").replace("[USER]", "[po-user]")
        wiring.write_text(text.replace("owner: OWNER", "owner: acme"))
        for rel, body in {"hotel/__init__.py": "", "hotel/booking.py": BOOKING, "tests/__init__.py": ""}.items():
            (self.home / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.home / rel).write_text(body)
        (self.home / "tests" / "test_booking.py").write_text(TESTS)
        (self.home / "README.md").write_text(README)
        (self.home / ".gitignore").write_text("__pycache__/\n")  # what running the tests leaves is no one's change
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
        self.gh.write_text(json.dumps({"user": "po-user", "issues": {"acme/hotel#1": issue}}, indent=2))

    def env(self) -> dict:
        github = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"url.{self.tmp / 'github'}/.insteadOf",
            "GIT_CONFIG_VALUE_0": "https://github.com/",
        }
        return {**os.environ, "FAB0_GH_FAKE": str(self.gh), **github}

    def claude(self, prompt: str) -> None:
        args = ["claude", "-p", prompt, "--plugin-dir", str(CORE), "--settings", str(self.tmp / "settings.json")]
        args += ["--setting-sources", "project,local", "--model", self.model, "--dangerously-skip-permissions"]
        args += ["--max-budget-usd", self.budget, "--output-format", "json"]
        print(f"$ claude -p {prompt!r} (in {self.home})", flush=True)
        run = subprocess.run(args, cwd=self.home, env=self.env(), capture_output=True, text=True, timeout=5400)
        try:
            out = json.loads(run.stdout)
        except ValueError:
            out = {"result": run.stdout + run.stderr}
        print(out.get("result", ""), flush=True)
        print(f"(cost ${out.get('total_cost_usd', 0):.2f}, {out.get('num_turns', '?')} turns)\n", flush=True)

    def resolve(self, *args: str) -> dict:
        run = subprocess.run(
            [str(CORE / "bin" / "fab0-resolve"), *args], cwd=self.home, env=self.env(), capture_output=True, text=True
        )
        return json.loads(run.stdout)

    def units(self) -> dict:
        return {u["unit"]: u for u in self.resolve("status", "1", "--profile", "cheap")["units"]}

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
            if len(parents) == 1 and git(self.home, "rev-parse", f"{commit}^{{tree}}") == git(
                self.home, "rev-parse", f"{parents[0]}^{{tree}}"
            ):
                found.append(git(self.home, "log", "-1", "--format=%s", commit))
        return found

    def run(self) -> int:
        self.setup()
        self.claude("/fab0:run 1 --profile cheap")
        spec = self.units().get("spec", {})
        self.expect(spec.get("reason") == {"gate": "human"}, f"the spec waits on its owner ({spec.get('reason')})")
        pulls = json.loads(self.gh.read_text()).get("pulls", {})
        self.expect(any(p["branch"] == REVIEW for p in pulls.get(RUNS, [])), "the spec has a review pull request")
        self.expect(not pulls.get("acme/hotel"), "the product repository has no pull request yet")
        review = git(self.runs, "ls-tree", "-r", "--name-only", REVIEW, "--", "runs/hotel/1/review/spec")
        self.expect(len(review.split()) == 2, f"the spec and the task list are on its branch ({review.split()})")
        if self.failures:
            return self.finish()

        self.merge_spec()
        self.claude("/fab0:run 1 --profile cheap")
        status = self.resolve("status", "1", "--profile", "cheap")
        tasks = [u for u in status["units"] if u.get("step") == "implement"]
        self.expect(bool(tasks), f"the spec's tasks became units ({len(tasks)})")
        for unit in tasks:
            self.expect(unit["state"] == "done", f"{unit['unit']} is reviewed and merged ({unit['state']})")
        self.expect(status["kind"] == "waiting", f"the run waits for a person to merge it ({status['kind']})")
        tree = self.tmp / "result"
        git(self.home, "worktree", "add", "-q", "--detach", str(tree), "fab0/1/base")
        tests = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=tree, capture_output=True
        )
        self.expect(tests.returncode == 0, "the run branch's tests pass")
        files = git(self.home, "log", "--all", "--name-only", "--format=", "--not", self.start).split()
        run_files = sorted(set(files))  # every file a commit of the run touched
        only_code = bool(run_files) and all(f.startswith(("hotel/", "tests/")) for f in run_files)
        self.expect(only_code, f"the run's commits touch only code and tests ({run_files})")
        self.expect(self.empty_commits() == [], f"no empty commit in the product repository ({self.empty_commits()})")
        stored = git(self.runs, "ls-tree", "-r", "--name-only", "main", "--", "runs/hotel/1")
        self.expect("runs/hotel/1/ledger/spec-1.yaml" in stored, "the ledger is in the runs repository")
        self.expect("runs/hotel/1/review/spec/spec.md" in stored, "the approved spec is in the runs repository")
        return self.finish()

    def finish(self) -> int:
        print(f"\n{len(self.failures)} failed" if self.failures else "\nall passed")
        if self.keep or self.failures:
            print(f"kept in {self.tmp}")
        else:
            shutil.rmtree(self.tmp)
        return 1 if self.failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", default="sonnet", help="the orchestrating session's model")
    parser.add_argument("--budget", default="5", help="the most one session may spend, in USD")
    parser.add_argument("--keep", action="store_true", help="keep the temporary project")
    args = parser.parse_args()
    if not (CORE / "bin" / "fab0-resolve").is_file():
        sys.exit(f"no fab0 engine at {CORE}: check out fab0-core beside this repository, or set FAB0_CORE")
    return Check(args.keep, args.model, args.budget).run()


if __name__ == "__main__":
    sys.exit(main())
