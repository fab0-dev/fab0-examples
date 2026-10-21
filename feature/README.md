# `feature` example

The parent of a composition. A **Feature** is an open item that holds a goal. Each **Story** under it is one run of this factory, which:
- says what the Story needs;
- has connected factories build it side by side, each in its own repository with its own agents and people;
- wraps up from what they hand back.

The wrap-up either files follow-up Stories under the same Feature or closes it. Here the connected factories are a service and its web client, each a copy of the [`delivery`](../delivery/) example.

| Step | Who | What | Gate |
|---|---|---|---|
| start | `apply` | The run's Pipeline Run in the runs repository, under the Story; its number is the run id. The run branch `fab0/<run>/base` there | — |
| `requirements` | `analyst` agent | The spec: intent, scope, `Done when` statements, the interfaces between the teams. A file in the runs repository, not in your repositories | **human, in a pull request:** the product owner approves its pull request in the runs repository; fab0 merges it |
| `service`, `web`, side by side | the connected factories | Each call opens that factory's run as a child Pipeline Run under this one, with the same run id, and its people run it in their repository with `/fab0:run`. The service hands back its contract and a report; the web client builds against the contract and hands back its report. The web client's work that reads the contract waits until this run accepts it; the rest of its work goes ahead | **auto:** once a child run is done, the `acceptor` agent judges what it hands back. A rejection opens that run again, and its steps that made what was wrong rework with the findings |
| `wrap-up` | `analyst` agent | From every team's report, whether the Feature is done, and the follow-up Stories it still needs | **human, in a pull request:** the product owner approves its pull request; fab0 merges it |
| follow-ups | `apply` | When the Feature is still open: a Story per follow-up, under the same Feature, with its intent as its body. Each is a run of its own once someone starts it | — |
| close | `apply` | When the Feature is done: it closes | — |
| end | `apply` | Merges the run pull request in the runs repository once its checks pass, closes the Story and the Pipeline Run | — |

Only this run judges the Feature. Each connected factory reports on its own area, and is checked against the format this run accepts (the contract's schema, the report's sections) before it hands anything back. What the factories exchange are files in the runs repository, each read at the commit that wrote it. Each team's code reaches `main` through its own run pull requests, which its run merges once their checks pass.

The whole history is on the tracker: the Story holds this run's Pipeline Run, which holds its steps and both child runs, and each closes when it is done.

## Files

| From here | To your product repository | Notes |
|---|---|---|
| `.fab0/` | `.fab0/` | Edit `fab0.yaml` where it says `EDIT`, and replace `OWNER`, `REPO` and `PRODUCT` everywhere. The rest works as is |
| `agents/*.md` | `.claude/agents/` | `analyst`, `acceptor` |
| `hooks/merge-guard.py` | `.claude/hooks/merge-guard.py` | Blocks merges, pushes to `main` and force pushes the model issues |
| `claude-settings.json` | merge into `.claude/settings.json` | The `fab0` marketplace with auto-update, the plugin, deny rules and the merge guard hook |

Each file's first line names this example and its release. Instead of copying `agents/` and `hooks/`, you can install them as the `feature@fab0-examples` plugin, and prefix the agent names in `.fab0/`: `agent: feature:analyst`.

## Set up

### 1. The product repository

A repository where the Features and Stories are filed. It holds no code: this factory writes only the runs repository.

```bash
cp -R ../fab0-examples/feature/.fab0 .fab0
```

```bash
mkdir -p .claude/agents .claude/hooks && cp ../fab0-examples/feature/agents/*.md .claude/agents/ && cp ../fab0-examples/feature/hooks/merge-guard.py .claude/hooks/
```

Replace `OWNER` with your organisation, `REPO` with this repository's name and `PRODUCT-runs` with the runs repository, everywhere in `.fab0/` (here `acme`, `shop` and `shop-runs`):

```bash
perl -pi -e 's/OWNER/acme/g; s/PRODUCT-runs/shop-runs/g; s/REPO/shop/g' $(grep -rlE 'OWNER|REPO|PRODUCT' .fab0)
```

Then edit `.fab0/fab0.yaml`:
- **`factories`:** one entry per connected factory, with its repository, its checkout beside this one, and the role whose turn it is while its run works. The pipeline's calls name them (`service`, `web`): rename them, or add a call per factory in `.fab0/pipelines/story.yaml`.
- **`people`**, **`tracker`**, **`repos.runs`** and **`tracking`:** as in the [`story`](../story/) example. Every connected factory names the same tracker owner and the same runs repository, and the runs repository is cloned beside each of them.

### 2. Each connected factory

In each code repository, copy the [`delivery`](../delivery/) example as its README says, with its repository's name where its `.fab0/` says `REPO`, as this factory's `factories` names it. Its `.fab0/` must be on its base branch: `validate` here reads it there. Run `fab0-resolve validate` here: it lists each connection, and refuses one whose wiring doesn't fit, such as another runs repository or run tracker, branches named as another factory's in the runs repository, a missing input or output, or a format that differs.

### 3. GitHub

- **Issue types:** `Feature`, `Story` and `Task`, and the run tracker's `Pipeline Run` and `Pipeline Step` with their issue fields, in the organisation, as the [`story`](../story/) example sets them up.
- **The label `delivery`** in each code repository, for a run started there by hand.
- **The runs repository**, shared by this factory and every connected one, as the `story` example sets it up.

## Run it

File a Feature, with its goal and how you'll know it is done, then a Story under it. Run `/fab0:run #<story>` here, and approve the requirements' pull request in the runs repository. Each call then opens a child run, and the run here waits: `/fab0:inbox` in each code repository lists that child run, and its people run it there with `/fab0:run`, confirming its plan at the prompt. Run `/fab0:run` here again to accept what comes back, and approve the wrap-up's pull request.
