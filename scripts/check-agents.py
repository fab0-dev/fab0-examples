"""Exit check for the examples: headless Claude Code runs the `story` example end to end on a small codebase,
through `/fab0:run`, against a fake tracker (FAB0_GH_FAKE) and local bare origins. Nothing reaches GitHub.

The workspace is set up as the example's README says: the home checkout `hotel` holds a copy of `story` (with `acme`
for OWNER, `hotel` for REPO and `po-user` as the product owner), beside the runs repository `hotel-runs`, each
repository with a bare `origin` of its own. The fake tracker holds the Story `acme/hotel#1`. `fab0-resolve validate`
must pass in every checkout before any session starts; if the engine is missing or older than 0.10, or a `validate`
fails, the check says why, starts no session and keeps the workspace.

The check drives a 0.10 run, one session at a time, and acts between sessions only where the example names a person:

1. The first session runs `/fab0:run #1 --profile cheap` in the home checkout. The run's Pipeline Run opens in
   `acme/hotel-runs`, under the Story, and its number is the run id (taken from the tracker). `spec-author` writes the
   spec, in a pull request of the runs repository, where the run waits on the product owner's gate; the product
   repository has no pull request and no commit yet.
2. The approval: as the product owner, the check comments `/approve` as `po-user` on the spec's pull request, timed
   after its head commit, as a person does on a pull request they opened. It merges, pushes and approves nothing else:
   the next session's `apply` merges the pull request, and the planner writes the task list.
3. The confirmation: a unit that waits for a confirmation at the prompt (the task list) is confirmed with
   `fab0-resolve confirm <run> <unit>` as `po-user`, in the home checkout, between sessions: a headless session has
   nobody to ask. A session that confirmed for the person fails the check.
4. The questions: a unit that waits on an agent's questions gets one fixed reply, which tells the agent to decide
   and say what it chose, where its step takes answers, as its wiring says: a comment on the unit's pull request when
   the step reads its own pull request, else appended to the body of the run's Story when the step reads that (a pull
   request the step doesn't read, which `apply` may have opened, gets nothing). A second set of questions from the
   same unit fails the check.
5. The run's merge into `main`: `apply` marks each run pull request merged in the fake tracker, which doesn't move
   the base; the check stands in for GitHub there and merges that pull request's branch into the base on that
   repository's `origin`, and does so for no other pull request or branch. The next session finishes the run.

Anything else that stops the run fails the check, which starts no further session and names the unit and why: an
escalation, a unit blocked on a failure or another signal for people (as the engine's inbox lists them), a person's
decision the check doesn't make. So does a run that isn't done within eight
sessions, with the run's position as `fab0-resolve status` gives it.

The outcome is read from the fake tracker's file, git and `fab0-resolve status`, never from a session's report: the
run is done; every Pipeline Run and Pipeline Step of the run carries the run id and is closed; each task of the task
list has one Task sub-issue of the Story, closed, and an `implement` unit that the `reviewer` agent approved and `apply`
merged into the run branch; `apply` merged each run pull request; the tests pass on `main` of the product repository,
which differs from its starting commit only in files a task claims, with no empty commit and no spec, task list or
run state in it; and the runs repository's `main` holds the run's spec and task list.

`--rehearse` (with `--example story`) shows the two acts a live run rarely needs, with no session and no cost: it
sets up the same workspace and plays each agent with a scripted stand-in against the real engine and the fake tracker,
so that the questions of a step that reads its pull request and of one that doesn't are answered where each reads
them, and the unit is reworked (4); and a confirmation a session made is told from the check's own, by attempt, and
the check's own is refused as "a session confirmed for the person" (3).

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
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from fnmatch import fnmatchcase
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
ROUNDS = 8  # the most sessions a run may take
STORY_REF = "acme/hotel#1"
# why a unit is blocked on something that needs a person's attention, as the engine's inbox lists them
SIGNALS = ("tracker", "invalid-dependency", "failed", "cross-run", "condition", "unsupported", "factory")
# the one reply to every set of questions: deciding product questions is the person's, and the check doesn't play at it
ANSWER = (
    "Decide this yourself, as you judge best, and say in your reply what you chose and why. "
    "Don't ask again: a person won't answer further questions."
)
FACT = re.compile(r"```yaml\n# fab0 (?P<name>[A-Za-z0-9][A-Za-z0-9._@+-]*)\n(?P<body>.*?)\n```", re.S)


def git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def yaml_load(text: str):
    """A YAML text as data: with PyYAML when this interpreter has it, else through `uv`, which the check needs
    anyway (no dependency of its own)."""
    try:
        import yaml
    except ImportError:
        run = subprocess.run(
            ["uv", "run", "--quiet", "--with", "pyyaml", "python", "-I", "-c",
             "import json, sys, yaml; print(json.dumps(yaml.safe_load(sys.stdin)))"],
            input=text, capture_output=True, text=True, check=True, cwd=tempfile.gettempdir(),
        )  # fmt: skip
        return json.loads(run.stdout)
    return yaml.safe_load(text)


def covers(glob: str, path: str) -> bool:
    """Whether a task's claimed glob covers one changed file, as the engine reads a claim (`claims.covers`)."""
    if glob == "**":
        return True
    for suffix in ("/**", "/"):
        folder = glob[: -len(suffix)]
        if glob.endswith(suffix) and not any(c in folder for c in "*?["):
            return path == folder or path.startswith(folder + "/")
    return fnmatchcase(path, glob)


def run_state(path: str) -> bool:
    """Whether a path is the run's own: its spec, task list or state, which belong in the runs repository."""
    parts = path.split("/")
    return parts[0] == "runs" or "ledger" in parts or parts[-1] in ("spec.md", "tasks.yaml")


def is_ancestor(path: Path, older: str, newer: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(path), "merge-base", "--is-ancestor", older, newer], capture_output=True
        ).returncode
        == 0
    )


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
        self.approved: set[tuple] = set()  # pull requests the check approved, at which head
        self.answered: set[str] = set()  # units whose questions it answered
        self.confirmed: set[tuple[str, int]] = set()  # (unit, attempt) it confirmed at the prompt

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

    def empty_commits(self, path: Path | None = None) -> list[str]:
        """Commits on any branch of a repository (the home checkout by default) that change nothing."""
        path = path or self.home
        found = []
        for line in git(path, "rev-list", "--all", "--parents").splitlines():
            commit, *parents = line.split()
            if len(parents) == 1 and git(path, "rev-parse", f"{commit}^{{tree}}") == git(
                path, "rev-parse", f"{parents[0]}^{{tree}}"
            ):
                found.append(git(path, "log", "-1", "--format=%s", commit))
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

    # ------------------------------------------------------------ what a person does between sessions

    def change_gh(self, change) -> None:
        """Write the fake tracker's file as a person's act on GitHub would change it: read whole, written whole
        through a rename, between sessions, so that no engine command reads it half-written."""
        data = json.loads(self.gh.read_text())
        change(data)
        temp = self.gh.with_name(self.gh.name + ".check")
        temp.write_text(json.dumps(data, indent=2))
        os.replace(temp, self.gh)

    def pull_of(self, branch: str) -> tuple[str, dict] | None:
        """The latest pull request, in any repository, whose head is `branch`."""
        found = [
            (repo, p)
            for repo, pulls in json.loads(self.gh.read_text()).get("pulls", {}).items()
            for p in pulls
            if p["branch"] == branch
        ]
        return max(found, key=lambda f: f[1]["number"], default=None)

    @staticmethod
    def clock(seconds: float) -> str:
        return datetime.fromtimestamp(int(seconds), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def approve(self, unit: dict) -> str | None:
        """The product owner approves the unit's pull request with `/approve`, as they would on one they opened:
        a comment by `po-user`, after the head commit of the branch. Why it can't, if it can't."""
        branch = unit.get("branch")
        found = self.pull_of(branch) if branch else None
        if found is None or found[1].get("state", "open") != "open":
            return "waits on a human gate and has no open pull request to approve"
        github, pull = found
        head = git(self.origin(github), "rev-parse", branch)
        if (github, pull["number"], head) in self.approved:
            return f"still waits on its human gate after the check approved {github}#{pull['number']} at {head[:8]}"
        stamp = max(time.time(), int(git(self.origin(github), "log", "-1", "--format=%ct", head)) + 1)

        def comment(data: dict) -> None:
            target = next(p for p in data["pulls"][github] if p["number"] == pull["number"])
            comments = target.setdefault("comments", [])
            comments.append({"id": len(comments) + 1, "body": "/approve", "user": PO, "at": self.clock(stamp)})

        self.change_gh(comment)
        self.approved.add((github, pull["number"], head))
        print(f"  {PO} comments /approve on {github}#{pull['number']} ({unit['unit']})", flush=True)
        return None

    def reads(self, unit: dict) -> set[str]:
        """Where a unit's step takes answers, from its wiring: `pr` when it reads its own pull request (its reviews
        and conversation comments), `item` when it reads the body of the run's item."""
        found = set()
        wiring = self.home / ".fab0"
        step = yaml_load((wiring / "steps" / f"{unit['step']}.yaml").read_text())
        for name in step.get("inputs", []):
            file = wiring / "artifacts" / f"{name}.yaml"
            if not file.is_file():  # `unit` is no artifact: the task the unit is for
                continue
            artifact = yaml_load(file.read_text())
            spec = artifact.get(artifact.get("kind"), {})
            if artifact.get("kind") == "pr" and spec.get("of") == "unit":
                found.add("pr")
            elif artifact.get("kind") == "issue" and spec.get("of") == "run" and spec.get("part") == "body":
                found.add("item")
        return found

    def answer(self, unit: dict) -> str | None:
        """The one reply to a unit's questions, where its step takes answers (`reads`): a comment on its pull request
        when it reads that, else appended to the body of the run's Story, which it reads as `intent`. Why it can't,
        if it can't."""
        if unit["unit"] in self.answered:
            return "asks questions a second time: the check answers each unit once"
        reads = self.reads(unit)
        found = self.pull_of(unit["branch"]) if "pr" in reads and unit.get("branch") else None
        if found is None and "item" not in reads:
            return "asks questions, and the check finds no pull request or item the step reads to answer them on"
        self.answered.add(unit["unit"])

        def reply(data: dict) -> None:
            if found is None:
                data["issues"][STORY_REF]["body"] += f"\n\n{ANSWER}"
                return
            target = next(p for p in data["pulls"][found[0]] if p["number"] == found[1]["number"])
            comments = target.setdefault("comments", [])
            comments.append({"id": len(comments) + 1, "body": ANSWER, "user": PO, "at": self.clock(time.time())})

        self.change_gh(reply)
        where = f"{found[0]}#{found[1]['number']}" if found else f"the Story {STORY_REF}"
        print(f"  {PO} answers the questions of {unit['unit']} on {where}", flush=True)
        return None

    def confirm(self, run: str, unit: dict) -> str | None:
        """The product owner confirms a unit at the prompt, in the home checkout: `confirm`, the command a person's
        yes runs. Why it can't, if it can't."""
        result = self.resolve("confirm", run, unit["unit"], "--profile", "cheap")
        if not result.get("ok"):
            error = str(result.get("error") or result)
            if "decided already" in error or "isn't waiting for a confirmation" in error:
                return f"a session confirmed for the person ({error})"
            return f"can't be confirmed: {error}"
        self.confirmed.add((unit["unit"], int(result["attempt"])))
        print(f"  {PO} confirms {unit['unit']} at the prompt: {result.get('line', '')}", flush=True)
        return None

    def confirmed_by_a_session(self, run: str) -> list[str]:
        """Attempts whose confirmation at the prompt the run's Pipeline Steps hold, which the check didn't make: each
        as `unit` and its attempt."""
        found = []
        for name, fact in self.step_facts(run).items():
            if name.endswith("-gate") and fact.get("gate", {}).get("via") == "prompt":
                unit, attempt = name.removesuffix("-gate").rsplit("-", 1)
                if (unit, int(attempt)) not in self.confirmed:
                    found.append(f"{unit}, attempt {attempt}")
        return sorted(found)

    def merge_runs(self, run_branch: str) -> list[str]:
        """What GitHub does and the fake doesn't: a run pull request that `apply` marked merged reaches the base of
        its repository's `origin`. Only those, and only the run branch."""
        merged = []
        for github, pulls in json.loads(self.gh.read_text()).get("pulls", {}).items():
            for pull in pulls:
                bare, base = self.origin(github), pull.get("base", "main")
                if pull["branch"] != run_branch or pull.get("state") != "merged":
                    continue
                if not git(bare, "branch", "--list", run_branch):
                    continue
                if is_ancestor(bare, f"refs/heads/{run_branch}", f"refs/heads/{base}"):
                    continue
                tree = self.tmp / "merge"
                git(self.tmp, "clone", "-q", "-b", base, str(bare), str(tree))
                git(
                    tree,
                    "-c", f"user.name={PO}", "-c", "user.email=po@example.com",
                    "merge", "-q", "--no-ff", "-m", f"Merge pull request #{pull['number']} from {run_branch}",
                    f"origin/{run_branch}",
                )  # fmt: skip
                git(tree, "push", "-q", "origin", base)
                shutil.rmtree(tree)
                print(f"  as GitHub would: {github}#{pull['number']} merges {run_branch} into {base}", flush=True)
                merged.append(f"{github}#{pull['number']}")
        return merged

    @staticmethod
    def classify(unit: dict) -> str:
        """What a unit after a session asks for: `approve`, `confirm` or `answer` (a person the examples name),
        `go` (an agent, `apply` or the engine goes on with it) or `stuck` (what no named person decides)."""
        state, reason = unit["state"], unit.get("reason") or {}
        if state == "waiting":
            if reason.get("gate") == "human":
                return "approve"
            if reason.get("gate") == "prompt":
                return "confirm"
            if "questions" in reason:
                return "answer"
            if reason.get("gate") in ("merge", "gate", "running", "ack") or "done" in reason:
                return "go"
            return "stuck"  # an escalation, a decision by issue or label, anything else a person decides
        if state == "blocked" and set(reason) & set(SIGNALS):
            return "stuck"
        return "go"

    def between(self, run: str, status: dict) -> bool:
        """The product owner's acts between two sessions, from what the run waits on; False, with each unit named,
        when it stopped on what no named person decides, and nothing is done then."""
        units = status.get("units", [])
        stuck = [u for u in units if self.classify(u) == "stuck"]
        for u in stuck:
            reason = f"{u['state']} {u.get('reason')}"
            self.expect(False, f"{u['unit']} stops the run, and no named person decides it: {reason}")
        if stuck:
            return False
        refused = []
        for u in units:
            act = self.classify(u)
            why = None
            if act == "approve":
                why = self.approve(u)
            elif act == "answer":
                why = self.answer(u)
            elif act == "confirm":
                why = self.confirm(run, u)
            if why:
                refused.append(u)
                self.expect(False, f"{u['unit']}: {why}")
        return not refused

    # ------------------------------------------------------------ what the run left

    def step_facts(self, run: str) -> dict[str, dict]:
        """The facts on the run's Pipeline Steps (the comments `fab0-resolve` writes), by name."""
        found: dict[str, dict] = {}
        for ref, issue in self.issues().items():
            if not ref.startswith(f"{RUNS}#") or issue.get("type") != "Pipeline Step":
                continue
            if issue.get("issue_fields", {}).get("Run ID") != run or issue.get("state_reason") == "not_planned":
                continue
            for comment in issue.get("comments", []):
                for m in FACT.finditer(comment.get("body") or ""):
                    found.setdefault(m["name"], yaml_load(m["body"]))
        return found

    def tasks_of(self, run: str) -> list[dict] | None:
        """The run's task list, from `main` of the runs repository."""
        shown = subprocess.run(
            ["git", "-C", str(self.runs), "show", f"main:runs/hotel/{run}/tasks.yaml"], capture_output=True, text=True
        )
        return yaml_load(shown.stdout) if shown.returncode == 0 else None

    def judge_issues(self, run: str, tasks: list[dict] | None) -> None:
        """S7 and S9, on the tracker: the Task sub-issues, and the run's issues, all closed with the run's id."""
        issues = self.issues()
        mine = {
            ref: issue
            for ref, issue in issues.items()
            if ref.startswith(f"{RUNS}#") and issue.get("type") in ("Pipeline Run", "Pipeline Step")
        }
        ids = {ref: issue.get("issue_fields", {}).get("Run ID") for ref, issue in mine.items()}
        wrong = {ref: found for ref, found in ids.items() if found != run}
        self.expect(
            bool(mine) and not wrong,
            f"every Pipeline Run and Pipeline Step carries the run id {run}, and no other ({wrong or len(mine)})",
        )
        opened = sorted(r for r, i in mine.items() if i.get("state", "open") != "closed")
        self.expect(not opened, f"every Pipeline Run and Pipeline Step is closed (open: {opened})")
        children = [
            r for r in issues.get(STORY_REF, {}).get("sub_issues", []) if issues.get(r, {}).get("type") == "Task"
        ]
        if tasks is not None:
            titles = sorted(issues[r]["title"] for r in children)
            self.expect(
                titles == sorted(t["title"] for t in tasks),
                f"each of the {len(tasks)} tasks has one Task sub-issue of the Story ({titles})",
            )
        self.expect(
            all(issues[r].get("state", "open") == "closed" for r in children),
            f"every Task sub-issue is closed ({[r for r in children if issues[r].get('state', 'open') != 'closed']})",
        )

    def judge_units(self, run: str, status: dict, tasks: list[dict] | None) -> None:
        """S7, on the units and their facts: every `implement` unit is done, its latest gate decision an approval by
        the `reviewer` agent, and the commit it recorded is in the run branch."""
        implement = [u for u in status.get("units", []) if u.get("step") == "implement"]
        self.expect(
            tasks is not None and len(implement) == len(tasks),
            f"each task has an implement unit ({len(implement)} for {len(tasks or [])} tasks)",
        )
        facts = self.step_facts(run)
        bare = self.origin("acme/hotel")
        target = status.get("branch", "")
        if not git(bare, "branch", "--list", target):
            target = "main"  # the run branch is gone once merged
        for u in implement:
            name = u["unit"]
            gates = sorted(
                int(m[1]) for n in facts if (m := re.fullmatch(rf"{re.escape(name)}-([1-9][0-9]*)-gate", n))
            )
            gate = facts.get(f"{name}-{gates[-1]}-gate", {}) if gates else {}
            self.expect(
                u["state"] == "done"
                and gate.get("gate", {}).get("agent") == "reviewer"
                and gate.get("gate", {}).get("decision") == "approve",
                f"{name} is done, approved by the reviewer agent ({u['state']}, {gate.get('gate')})",
            )
            head = (facts.get(f"{name}-{gates[-1]}", {}) if gates else {}).get("heads", {}).get("home")
            self.expect(
                bool(head) and is_ancestor(bare, head, target),
                f"{name}'s commit is in the run branch ({head and head[:8]} in {target})",
            )

    def judge_pulls(self, run_branch: str) -> None:
        """S9: `apply` marked each run pull request merged (only `apply`'s merge names who merged it)."""
        for github in ("acme/hotel", RUNS):
            runs = [
                p
                for p in json.loads(self.gh.read_text()).get("pulls", {}).get(github, [])
                if p["branch"] == run_branch and p.get("base", "main") == "main"
            ]
            seen = [(p["number"], p.get("state"), p.get("merged_by")) for p in runs]
            self.expect(
                len(runs) == 1 and runs[0].get("state") == "merged" and runs[0].get("merged_by") == PO,
                f"apply merged the run pull request of {github} ({seen})",
            )

    def judge_repositories(self, run: str, tasks: list[dict] | None) -> None:
        """S10: the product repository holds only the tasks' changes, and its tests pass; the runs repository holds
        the spec and the task list."""
        bare = self.origin("acme/hotel")
        tree = self.tmp / "verify"
        git(self.tmp, "clone", "-q", "-b", "main", str(bare), str(tree))
        tests = subprocess.run(
            ["python3", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
            cwd=tree, capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )  # fmt: skip
        self.expect(
            tests.returncode == 0,
            f"the tests pass on main of acme/hotel ({tests.stderr.strip().splitlines()[-1:]})",
        )
        shutil.rmtree(tree)
        changed = git(bare, "diff", "--name-only", "--no-renames", self.start, "main").splitlines()
        claims = [g for t in tasks or [] if t.get("repo") == "home" for g in t.get("files", [])]
        loose = [f for f in changed if not any(covers(g, f) for g in claims)]
        self.expect(
            tasks is not None and bool(changed) and not loose,
            f"every file that changed on main of acme/hotel is claimed by a task ({loose or changed})",
        )
        for where, path in (("its origin", bare), ("its checkout", self.home)):
            empty = self.empty_commits(path)
            self.expect(empty == [], f"no commit of acme/hotel is empty, in {where} ({empty})")
        files = set(git(bare, "log", "--all", "--not", self.start, "--name-only", "--format=").split())
        self.expect(
            not [f for f in files if run_state(f)],
            f"no spec, task list or run state is in acme/hotel ({sorted(f for f in files if run_state(f))})",
        )
        for name in ("spec.md", "tasks.yaml"):
            shown = subprocess.run(
                ["git", "-C", str(self.runs), "show", f"main:runs/hotel/{run}/{name}"], capture_output=True, text=True
            )
            self.expect(
                shown.returncode == 0 and bool(shown.stdout.strip()),
                f"main of {RUNS} holds runs/hotel/{run}/{name}",
            )

    def judge(self, run: str, status: dict) -> None:
        """What the finished run left, from the tracker and the repositories."""
        tasks = self.tasks_of(run)
        self.expect(bool(tasks), f"the task list is on main of {RUNS}")
        self.judge_units(run, status, tasks)
        self.judge_issues(run, tasks)
        self.judge_pulls(status.get("branch", ""))
        self.judge_repositories(run, tasks)

    # ------------------------------------------------------------ the run

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
        if self.failures:
            return self.finish()
        return self.drive(run)

    def snapshot(self, run: str) -> str:
        """What a session can change: the run's units, the fake tracker, and the branches of the origins."""
        refs = [git(self.origin(github), "for-each-ref") for github in ("acme/hotel", RUNS)]
        return json.dumps([self.status(run).get("units"), self.gh.read_text(), refs])

    def drive(self, run: str) -> int:
        """The rest of the run: the product owner's acts between sessions, one session at a time, until the run is
        done after a session, something stops it, or the sessions are used up."""
        sessions = 1  # the first has been taken
        while True:
            status = self.status(run)
            if status.get("kind") == "done":
                break
            if not self.between(run, status):
                return self.finish()
            if status.get("branch"):
                self.merge_runs(status["branch"])
            if sessions >= ROUNDS:
                break
            before = self.snapshot(run)
            if not self.claude(f"/fab0:run {run} --profile cheap"):
                return self.finish()
            sessions += 1
            if self.snapshot(run) == before:  # nothing changed, and the check changed nothing: the next one won't
                position = self.status(run).get("position")
                self.expect(False, f"the session changed nothing, and the run isn't done ({position})")
                return self.finish()
            for unit in self.confirmed_by_a_session(run):
                self.expect(False, f"a session confirmed for the person ({unit})")
            if self.failures:
                return self.finish()
        status = self.status(run)
        self.expect(
            status.get("kind") == "done",
            f"the run is done within {ROUNDS} sessions ({status.get('position') or status.get('error') or status})",
        )
        if status.get("kind") == "done":
            self.judge(run, status)
        return self.finish()

    def finish(self) -> int:
        print(f"\ntotal cost ${self.cost:.2f}")
        print(f"\n{len(self.failures)} failed" if self.failures else "\nall passed")
        if self.keep or self.failures:
            print(f"kept in {self.tmp}")
        else:
            shutil.rmtree(self.tmp)
        return 1 if self.failures else 0


SPEC = """# Extend a booking

## Intent

The front desk extends a booking.

## Scope

- In: extending a booking.

## Scenarios

### S1: a free room is extended

- Given a booking
- When the front desk extends it by a night
- Then the booking ends a day later

## Constraints

- Standard library only.

## Decisions

- None.

## Open questions

None
"""


class Rehearsal(Check):
    """What a live run rarely shows: the product owner's answer to an agent's questions (S5) and the refusal of a
    confirmation a session made (S6), against the real engine and the fake tracker, with a scripted stand-in for each
    agent. It starts no Claude Code session and costs nothing."""

    def __init__(self, keep: bool, model: str, budget: str):
        super().__init__(keep, model, budget)
        self.versions = 0

    def write(self, run: str, hand: dict, tree: str) -> None:
        """What the stand-in for the unit's agent writes: a new version of its output each time."""
        self.versions += 1
        if hand["unit"] == "spec":
            path, text = f"runs/hotel/{run}/spec.md", SPEC + f"\nVersion {self.versions}.\n"
        else:
            path = f"runs/hotel/{run}/tasks.yaml"
            text = f"- id: T1\n  title: Extend, version {self.versions}\n  repo: home\n  files: [hotel/booking.py]\n"
        (Path(tree) / path).parent.mkdir(parents=True, exist_ok=True)
        (Path(tree) / path).write_text(text)

    def round(self, run: str, questions: dict[str, list[str]] | None = None) -> None:
        """One round of a run session: `next --apply`, what its hand-outs ask of an agent (checkouts, the work, the
        return, `record`), then `next --apply` again, as the next round does: it opens the pull requests."""
        repos = {"home": self.home, "runs": self.workspace / "hotel-runs"}
        for hand in self.resolve("next", run, "--apply", "--profile", "cheap").get("handouts", []):
            if hand["executor"] != "agent" or hand.get("gate") is True:
                continue
            for branch in hand["branches"]:
                repo = repos[branch["repo"]]
                if Path(branch["worktree"]).exists():  # an earlier attempt's checkout of the branch
                    continue
                if branch["exists"]:
                    git(repo, "worktree", "add", branch["worktree"], branch["branch"])
                else:
                    git(repo, "worktree", "add", "-b", branch["branch"], branch["worktree"], branch["from"])
            self.write(run, hand, hand["branches"][0]["worktree"])
            returned = {"summary": f"wrote {hand['unit']}"}
            if (questions or {}).get(hand["unit"]):
                returned["questions"] = questions[hand["unit"]]
            file = self.tmp / "return.json"
            file.write_text(json.dumps(returned))
            done = self.resolve("record", run, hand["unit"], "--return", str(file), "--profile", "cheap")
            if not done.get("ok"):
                self.expect(False, f"the stand-in's {hand['unit']} is recorded ({done})")
        self.resolve("next", run, "--apply", "--profile", "cheap")

    def comments(self, unit: dict) -> list[str]:
        found = self.pull_of(unit["branch"])
        return [c["body"] for c in found[1].get("comments", [])] if found else []

    def run(self) -> int:
        self.setup()
        if not self.validate():
            return self.finish()
        run = self.resolve("start", "#1", "--session", "--profile", "cheap").get("run")
        if not run:
            self.expect(False, "the run starts")
            return self.finish()
        unit = lambda name: self.units(run).get(name, {})  # noqa: E731
        asks = lambda u: u.get("state") == "waiting" and "questions" in (u.get("reason") or {})  # noqa: E731

        # S5, a step that reads its own pull request: the answer is a comment there, and the unit is reworked
        self.round(run, {"spec": ["Which dates collide?"]})
        spec = unit("spec")
        self.expect(asks(spec) and self.classify(spec) == "answer", f"spec waits on questions ({spec.get('reason')})")
        self.expect(self.reads(spec) == {"pr", "item"}, f"spec reads its pull request and the item ({self.reads(spec)})")
        self.expect(self.answer(spec) is None, "the check answers the questions of spec")
        self.expect(self.comments(spec) == [ANSWER], f"the answer is a comment on spec's pull request ({self.comments(spec)})")
        spec = unit("spec")
        self.expect(
            spec.get("state") == "ready" and bool((spec.get("reason") or {}).get("rework")),
            f"spec is reworked with the answer ({spec.get('state')}, {spec.get('reason')})",
        )
        # and only once
        self.round(run, {"spec": ["And which rooms?"]})
        spec = unit("spec")
        self.expect(asks(spec), f"spec asks a second time ({spec.get('reason')})")
        why = self.answer(spec)
        self.expect(bool(why) and "second time" in why, f"the check doesn't answer a second time ({why})")
        self.change_gh(  # a person's own words, which the check never writes: a review of its kind
            lambda data: data["pulls"][RUNS][0].setdefault("comments", []).append(
                {"id": 9, "body": "Keep it small.", "user": PO, "at": self.clock(time.time())}
            )
        )
        self.round(run)
        spec = unit("spec")
        self.expect(spec.get("reason") == {"gate": "human"}, f"spec waits on its human gate ({spec.get('reason')})")
        self.expect(self.approve(spec) is None, "the check approves spec's pull request")

        # S5, a step that doesn't: its pull request is no place for the answer, which goes on the run's item
        self.round(run, {"plan": ["Which room?"]})
        plan = unit("plan")
        self.expect(asks(plan) and self.classify(plan) == "answer", f"plan waits on questions ({plan.get('reason')})")
        self.expect(self.pull_of(plan["branch"]) is not None, "plan has a pull request, which it doesn't read")
        self.expect(self.reads(plan) == {"item"}, f"plan reads the item, not its pull request ({self.reads(plan)})")
        self.expect(self.answer(plan) is None, "the check answers the questions of plan")
        self.expect(self.comments(plan) == [], f"nothing is said on plan's pull request ({self.comments(plan)})")
        story = self.issues()[STORY_REF]["body"]
        self.expect(story.endswith(ANSWER), "the answer is appended to the body of the run's Story")
        self.expect(not asks(unit("plan")), f"plan no longer waits on its questions ({unit('plan').get('state')})")

        # S6: the refusal, and the confirmations of a session that the check didn't make, by attempt
        for _ in range(8):
            plan = unit("plan")
            if plan.get("reason") == {"gate": "prompt"}:
                break
            for u in self.status(run)["units"]:
                if self.classify(u) == "approve":
                    self.approve(u)
            self.round(run)
        self.expect(plan.get("reason") == {"gate": "prompt"}, f"plan waits for a confirmation ({plan.get('reason')})")
        first = plan.get("attempt")
        decided = self.resolve("confirm", run, "plan", "--reject", "Add a task.", "--profile", "cheap")
        self.expect(decided.get("ok") is True, f"a session decides at the prompt, for the person ({decided.get('error')})")
        self.round(run)
        plan = unit("plan")
        self.expect(plan.get("reason") == {"gate": "prompt"} and plan.get("attempt") == first + 1, "plan is reworked")
        self.expect(self.confirm(run, plan) is None, "the check confirms the reworked plan")
        self.expect(
            self.confirmed_by_a_session(run) == [f"plan, attempt {first}"],
            f"only the session's decision is told apart, by attempt ({self.confirmed_by_a_session(run)})",
        )
        why = self.confirm(run, plan)
        self.expect(
            bool(why) and why.startswith("a session confirmed for the person"), f"a decided plan is refused ({why})"
        )
        return self.finish()


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
    parser.add_argument(
        "--rehearse",
        action="store_true",
        help="with --example story: the product owner's acts against the engine and a stand-in for each agent, "
        "with no session",
    )
    args = parser.parse_args()
    if args.rehearse and args.example != "story":
        parser.error("--rehearse is for --example story")
    problem = engine_problem()
    if problem:
        print(f"FAIL  {problem}", flush=True)
        return 1  # no workspace yet, and no session
    kind = Rehearsal if args.rehearse else Composition if args.example == "feature" else Check
    return kind(args.keep, args.model, args.budget).run()


if __name__ == "__main__":
    sys.exit(main())
