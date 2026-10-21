# `delivery` example

A connected factory: one team's delivery in its own repository. A parent factory such as the [`feature`](../feature/) example calls it, binding a spec and maybe another team's contract, and takes back what it hands back. It also runs on its own, from an item labelled `delivery` whose body is the spec.

| Step | Who | What | Gate |
|---|---|---|---|
| start | `apply` | A call opens the run's Pipeline Run under the caller's, with the caller's run id and what it binds. The run branch `<factory>/<run>/base`; the run pull request once it has work | — |
| `plan` | `planner` agent | The task list, and whether this team provides a contract that other teams build against: files in the runs repository | **human, at the prompt:** the developer confirms them in the run session, or rejects them with what to change |
| `contract`, when the team provides one | `implementer` agent | The contract, a file in the runs repository, in the caller's format | **auto:** the `reviewer` agent |
| `implement`, per task | `implementer` agent | The task's files, with tests, against the contract and any contract the caller bound (`upstream`). A task that reads another team's contract waits until the caller has accepted it | **auto:** the `reviewer` agent; `apply` merges approved tasks into the run branch |
| `report` | `reporter` agent | What this team delivered, deviations and open questions, about its own area only: a file in the runs repository | — |
| end | `apply` | Brings `main` into the run branch, merges each run pull request into `main` once its required checks pass, and closes the Pipeline Run | — |

Once the run is done, the caller decides whether to accept what it hands back, with its own gate. A rejection opens this run again, with the caller's findings, and the steps that made what was rejected rework.

## What a caller binds, and what it takes back

| | Name | What |
|---|---|---|
| input | `spec` | What to build. Without a caller, the run's own item body |
| input | `upstream` | Another team's contract to build against. Optional |
| output | `contract` | What this team offers other teams, when it provides one |
| output | `feedback` | The report: `Delivered`, `Deviations`, `Open questions` |

They are files in the runs repository, which every factory of the product shares: each side reads the other's at the commit that wrote it. The caller decides the format it accepts for each output, and `record` checks it here before anything goes back. The brief of each step that writes one says what that format is.

## Files

| From here | To this repository | Notes |
|---|---|---|
| `.fab0/` | `.fab0/` | Edit `fab0.yaml` where it says `EDIT`, and replace `OWNER`, `REPO` and `PRODUCT` everywhere |
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

Replace `OWNER` with your organisation, `REPO` with this repository's name, as the parent's `factories` names it, and `PRODUCT-runs` with the parent's runs repository, everywhere in `.fab0/` (here `acme`, `service` and `shop-runs`). `REPO` is also this factory's name: it keeps its branches and files apart from the other factories' in the runs repository.

```bash
perl -pi -e 's/OWNER/acme/g; s/PRODUCT-runs/shop-runs/g; s/REPO/service/g' $(grep -rlE 'OWNER|REPO|PRODUCT' .fab0)
```

Then edit `.fab0/fab0.yaml`: `people`, and any other repository tasks may change. Clone the runs repository beside this one. Commit `.fab0/` to `main`, where the parent reads it. On GitHub: the label `delivery` in this repository, and the `Task` issue type; the run tracker's issue types and fields are the parent's.

Run `/fab0:run` here when `/fab0:inbox` lists a run: a call started it, under the caller's run id, or someone labelled an item `delivery` and started it with `/fab0:run #<item>`. The session asks the developer to confirm the plan; the rest goes on by itself.
