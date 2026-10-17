#!/usr/bin/env -S uv run --quiet --script
# from fab0-dev/fab0-examples triage--v0.2.0
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""The classification gate: the `classify` attempt it judges names an area from .fab0/areas.txt, and doesn't call
the report a duplicate of itself. Exit 0 approves; anything else rejects, with this output as the finding.

    classification.py RUN ATTEMPT

ATTEMPT is the attempt's ledger entry, a YAML file, which the gate's `{attempt}` names.
"""

import sys
from pathlib import Path

import yaml

run, attempt = sys.argv[1], Path(sys.argv[2])
entry = yaml.safe_load(attempt.read_text()) or {}
data = entry.get("data") or {}
areas = [x.strip() for x in Path(".fab0/areas.txt").read_text().splitlines() if x.strip() and not x.startswith("#")]
problems = []
if data.get("area") not in areas:
    problems.append(f"area {data.get('area')!r} is not one of {', '.join(areas)}")
if str(data.get("duplicate_of")) == run:
    problems.append("a report can't duplicate itself")
if problems:
    sys.exit("; ".join(problems))
print(f"{data['severity']} in {data['area']}: fine")
