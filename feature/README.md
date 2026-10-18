# `feature` example

The parent of a composition. A **Feature** is an open item that holds a goal. Each **Story** under it is one run of this factory, which:
- says what the Story needs;
- has connected factories build it side by side, each in its own repository with its own agents and people;
- wraps up from what they hand back.

The wrap-up either files follow-up Stories under the same Feature or closes it. Here the connected factories are a service and its web client, each a copy of the [`delivery`](../delivery/) example.

| Step | Who | What | Gate |
|---|---|---|---|
| `requirements` | `analyst` agent | The spec: intent, scope, `Done when` statements, the interfaces between the teams. Kept in the run store, not in your repositories | **human**: the product owner merges its review pull request in the runs repository |
| `service`, `web`, side by side | the connected factories | Each call files an item in that factory's repository, labelled `delivery`, as a sub-issue of the Story, and its people run it there with `/fab0:run`. The service hands back its contract and a report; the web client builds against the contract and hands back its report. The web client's work that reads the contract waits until this run accepts it; the rest of its work goes ahead | **auto**: the `acceptor` agent acknowledges each thing a factory hands back. A rejection sends it back to that factory to rework, with the findings |
| `wrap-up` | `analyst` agent | From every team's report, whether the Feature is done, and the follow-up Stories it still needs | **human**: the product owner merges its review pull request |
| follow-ups | `apply` | When the Feature is still open: a Story per follow-up, under the same Feature, with its intent as its body. Each is a run of its own once someone starts it | — |
| close | `apply` | When the Feature is done: it closes. The Story closes either way | — |

Only this run judges the Feature. Each connected factory reports on its own area, and is checked against the format this run accepts (the contract's schema, the report's sections) before it hands anything back. The teams' code reaches `main` through each team's own run pull request, which its people merge; this run doesn't wait for that.

## Files

| From here | To your product repository | Notes |
|---|---|---|
| `.fab0/` | `.fab0/` | Edit `fab0.yaml` where it says `EDIT`. The rest works as is |
| `agents/*.md` | `.claude/agents/` | `analyst`, `acceptor` |
| `hooks/merge-guard.py` | `.claude/hooks/merge-guard.py` | Blocks merges, pushes to `main` and force pushes the model issues |
| `claude-settings.json` | merge into `.claude/settings.json` | The `fab0` marketplace with auto-update, the plugin, deny rules and the merge guard hook |

Each file's first line names this example and its release. Instead of copying `agents/` and `hooks/`, you can install them as the `feature@fab0-examples` plugin, and prefix the agent names in `.fab0/`: `agent: feature:analyst`.

## Set up

### 1. The product repository

A repository where the Features and Stories are filed. It holds no code: this factory writes nothing there.

```bash
cp -R ../fab0-examples/feature/.fab0 .fab0
```

```bash
mkdir -p .claude/agents .claude/hooks && cp ../fab0-examples/feature/agents/*.md .claude/agents/ && cp ../fab0-examples/feature/hooks/merge-guard.py .claude/hooks/
```

Edit `.fab0/fab0.yaml`:
- **`repos.home`:** this repository.
- **`factories`:** one entry per connected factory, with its repository, its checkout beside this one, and the role whose turn it is while its run works. The pipeline's calls name them (`service`, `web`): rename them, or add a call per factory in `.fab0/pipelines/story.yaml`.
- **`people`**, **`tracker`**, **`store`:** as in the `story` example. Every connected factory names the same tracker owner and the same runs repository.

### 2. Each connected factory

In each code repository, copy the [`delivery`](../delivery/) example as its README says, and set its `repos.home` to the repository this factory's `factories` names. Its `.fab0/` must be on its base branch: `validate` here reads it there. Run `fab0-resolve validate` here: it lists each connection, and refuses one whose wiring doesn't fit (another runs repository, a missing input or output, a format that differs).

### 3. GitHub

- **Issue types:** `Feature`, `Story` and `Task`, in the organisation.
- **The label `delivery`** in each code repository: a call files its item with it.
- **The runs repository**, shared by this factory and every connected one, as the `story` example sets it up.

## Run it

File a Feature, with its goal and how you'll know it is done, then a Story under it. Run `/fab0:run <story>` here. It stops while the teams work: `/fab0:inbox` in each code repository lists its run, and its people run it there with `/fab0:run <their item>`. Run `/fab0:run <story>` here again to acknowledge what comes back and to wrap up.
