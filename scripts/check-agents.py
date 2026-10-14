"""Exit check for the `story` agents: headless Claude Code runs the story example end to end on a small
codebase, through `/fab0:run`, against a fake tracker (FAB0_GH_FAKE) and a bare `origin`.

1. The first session runs the spec: `spec-author` writes the spec and the task list, which `record` checks.
   The run then waits on the product owner's gate.
2. This script merges the spec into the run branch, as the product owner would by merging its pull request.
3. The second session runs every task: `implementer` per task, `reviewer` as each task's gate. `apply` merges
   approved tasks into the run branch, and the run ends waiting for a person to merge it into main.

Then the run branch's tests must pass. It costs tokens and needs a logged-in `claude`, and the engine of a
sibling fab0-core checkout (or $FAB0_CORE, the path of its `plugins/fab0`).

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
}


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
        git(self.home, "config", "user.email", "check@example.com")
        git(self.home, "config", "user.name", "check")
        git(self.home, "add", "-A")
        git(self.home, "commit", "-q", "-m", "start")
        bare = self.tmp / "remotes" / "hotel.git"
        bare.parent.mkdir()
        git(self.tmp, "init", "-q", "--bare", str(bare))
        git(self.home, "remote", "add", "origin", str(bare))
        git(self.home, "push", "-q", "origin", "main")
        issue = {"title": "Extend a booking", "body": INTENT, "type": "Story"}
        self.gh.write_text(json.dumps({"user": "po-user", "issues": {"acme/hotel#1": issue}}, indent=2))

    def env(self) -> dict:
        return {**os.environ, "FAB0_GH_FAKE": str(self.gh)}

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
        """What the product owner does: merge the spec's pull request into the run branch."""
        tree = self.tmp / "merge"
        git(self.home, "worktree", "add", "-q", str(tree), "fab0/1/base")
        git(tree, "merge", "-q", "--no-ff", "-m", "Merge the spec", "fab0/1/spec")
        git(tree, "push", "-q", "origin", "fab0/1/base")
        git(self.home, "worktree", "remove", str(tree))
        data = json.loads(self.gh.read_text())
        for pull in data.get("pulls", {}).get("acme/hotel", []):
            if pull["branch"] == "fab0/1/spec":
                pull["state"] = "merged"
        self.gh.write_text(json.dumps(data, indent=2))

    def run(self) -> int:
        self.setup()
        self.claude("/fab0:run 1 --profile cheap")
        spec = self.units().get("spec", {})
        self.expect(spec.get("reason") == {"gate": "human"}, f"the spec waits on its owner ({spec.get('reason')})")
        pulls = json.loads(self.gh.read_text()).get("pulls", {}).get("acme/hotel", [])
        self.expect(any(p["branch"] == "fab0/1/spec" for p in pulls), "the spec has a pull request")
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
        self.expect((tree / "specs" / "1.md").is_file(), "the spec is on the run branch")
        self.expect(not (tree / "work" / "1" / "tasks.yaml").exists(), "the task list was removed at the end")
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
