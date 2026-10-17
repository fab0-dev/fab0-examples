# `triage` example

A factory that delivers no code. Each new bug report is classified, checked, labelled and, when severe, handed to on-call, all in the tracker:

| Step | Who | What | Gate |
|---|---|---|---|
| start | `apply` | Swaps the `needs-triage` label for `triaging` | — |
| `classify` | `triager` agent | Severity, area, and a duplicate if there is one, as structured data | **auto**: a command reads the attempt it judges and checks the area against `.fab0/areas.txt`. One rejection is retried; a second stops the run |
| `label` | `apply` | Adds `severity-<severity>` and `area-<area>` | — |
| `escalate`, when `severity-high` | `apply` | Assigns the report to the `on-call` role | — |
| end | `apply` | Removes `triaging` and comments with the classification | — |

There are no pull requests, and nothing is committed to your repository. The run's record, its ledger, lives in the run store: a runs repository beside your own, which every fab0 factory of the product shares.

## Files

| From here | To your repository | Notes |
|---|---|---|
| `.fab0/` | `.fab0/` | Edit `fab0.yaml` and `areas.txt` where they say `EDIT` |
| `agents/triager.md` | `.claude/agents/` | |
| `claude-settings.json` | merge into `.claude/settings.json` | The `fab0` marketplace with auto-update, the plugin, and deny rules |

## Set up

1. Copy the files:
   ```bash
   cp -R ../fab0-examples/triage/.fab0 .fab0 && mkdir -p .claude/agents && cp ../fab0-examples/triage/agents/triager.md .claude/agents/
   ```
2. Edit `.fab0/fab0.yaml` (the repository, the people in `support` and `on-call`, the tracker owner, and the runs repository in `store`) and `.fab0/areas.txt`.
3. Create the labels `needs-triage`, `triaging`, `severity-low`, `severity-medium`, `severity-high`, and `area-<area>` for each area.
4. Create the runs repository named in `store.github`, if the product has none yet: private, with a ruleset that blocks force pushes to `main` and its deletion, and write access for everyone in `people`. The `fab0:github` skill checks the labels and the runs repository, and creates the runs repository when you ask.
5. Install [`uv`](https://docs.astral.sh/uv/), trust the folder in Claude Code, and install the plugin: `claude plugin install fab0@fab0 --scope project`. Check with `fab0-resolve validate`: it also checks that the runs repository can be reached.

## Use

Label a report `needs-triage` and run `/fab0:run <issue>`. `/fab0:inbox` lists the reports waiting to be triaged.
