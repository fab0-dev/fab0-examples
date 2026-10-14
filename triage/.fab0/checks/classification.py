#!/usr/bin/env -S uv run --quiet --script
# from fab0-dev/fab0-examples triage--v0.1.0
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""The classification gate: the newest `classify` attempt of a run names an area from .fab0/areas.txt, and
doesn't call the report a duplicate of itself. Exit 0 approves; anything else rejects, with this output as
the finding.

    classification.py RUN
"""

import re
import sys
from pathlib import Path

import yaml

run = sys.argv[1]
folder = Path("triage") / run
attempts = sorted(
    (int(m.group(1)), p) for p in folder.glob("classify-*.yaml") if (m := re.fullmatch(r"classify-(\d+)\.yaml", p.name))
)
if not attempts:
    sys.exit(f"no classify attempt in {folder}")
data = (yaml.safe_load(attempts[-1][1].read_text()) or {}).get("data") or {}
areas = [x.strip() for x in Path(".fab0/areas.txt").read_text().splitlines() if x.strip() and not x.startswith("#")]
problems = []
if data.get("area") not in areas:
    problems.append(f"area {data.get('area')!r} is not one of {', '.join(areas)}")
if str(data.get("duplicate_of")) == run:
    problems.append("a report can't duplicate itself")
if problems:
    sys.exit("; ".join(problems))
print(f"{data['severity']} in {data['area']}: fine")
