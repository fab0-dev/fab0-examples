# `delivery` example

A connected factory: one team's delivery in its own repository. A parent factory such as the [`feature`](../feature/) example calls it, binding a spec and maybe another team's contract, and takes back what it hands back. It also runs on its own, from an item labelled `delivery` whose body is the spec.

| Step | Who | What | Gate |
|---|---|---|---|
| start | `apply` | Binds the run to the call that started it, if one did. The run branch `fab0/<run>/base`; the run pull request once it has work | — |
| `plan` | `planner` agent | The task list, and whether this team provides a contract that other teams build against. Kept in the run store | **human**: the developer merges its review pull request in the runs repository |
| `contract`, when the team provides one | `implementer` agent | `contract.yaml`, in the caller's format | **auto**: the `reviewer` agent; then the caller acknowledges it, and a rejection brings a rework with the caller's findings |
| `implement`, per task | `implementer` agent | The task's files, with tests, against any contract the caller bound (`upstream`). A task waits until that contract is accepted | **auto**: the `reviewer` agent; `apply` merges approved tasks into the run branch |
| `report` | `reporter` agent | What this team delivered, deviations and open questions, about its own area only | the caller acknowledges it |
| end | `apply` | Brings `main` into the run branch, and marks the run pull request ready | **human**: a person merges the run into `main` |

## What a caller binds, and what it takes back

| | Name | What |
|---|---|---|
| input | `spec` | What to build. Without a caller, the run's own item body |
| input | `upstream` | Another team's contract to build against. Optional |
| output | `contract` | What this team offers other teams, when it provides one |
| output | `feedback` | The report: `Delivered`, `Deviations`, `Open questions` |

The caller decides the format it accepts for each output, and `record` checks it here before anything goes back. The brief of each step that writes one says what that format is.

## Files

| From here | To this repository | Notes |
|---|---|---|
| `.fab0/` | `.fab0/` | Edit `fab0.yaml` where it says `EDIT` |
| `agents/*.md` | `.claude/agents/` | `planner`, `implementer`, `reviewer`, `reporter` |
| `hooks/merge-guard.py` | `.claude/hooks/merge-guard.py` | Blocks merges, pushes to `main` and force pushes the model issues |
| `claude-settings.json` | merge into `.claude/settings.json` | The `fab0` marketplace with auto-update, the plugin, deny rules and the merge guard hook |

Each file's first line names this example and its release. Or install the agents and the hook as the `delivery@fab0-examples` plugin, and prefix the agent names: `agent: delivery:planner`.

## Set up

```bash
cp -R ../fab0-examples/delivery/.fab0 .fab0
```

```bash
mkdir -p .claude/agents .claude/hooks && cp ../fab0-examples/delivery/agents/*.md .claude/agents/ && cp ../fab0-examples/delivery/hooks/merge-guard.py .claude/hooks/
```

Edit `.fab0/fab0.yaml`: `repos.home` as the parent's `factories` names this repository; `people`; the parent's tracker owner; the parent's runs repository under `store`. Commit it to `main`, where the parent reads it. On GitHub: the label `delivery` in this repository, and the `Task` issue type.

Run `/fab0:run <item>` here when `/fab0:inbox` lists a run: a call filed it, or someone labelled an item `delivery`.
