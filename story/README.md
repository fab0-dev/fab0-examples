# `story` example

Delivery of one work item, a GitHub issue of type **Story**, on its own branch:

| Step | Who | What | Gate |
|---|---|---|---|
| start | `apply` | The run branch `fab0/<run>/base` in every repository the run writes, and a draft run pull request into `main` that closes the Story | — |
| `spec` | `spec-author` agent | `specs/<run>.md` and `work/<run>/tasks.yaml`, on the sub-branch `fab0/<run>/spec` | **human**: the product owner merges the spec's pull request into the run branch |
| tasks | `apply` | A Task sub-issue per task, blocked by the sub-issues of the tasks it depends on | — |
| `implement`, per task | `implementer` agent | The task's files, with tests, on `fab0/<run>/implement-<task>`. Tasks run in parallel where their files don't overlap and their order allows | **auto**: the `reviewer` agent; on approval and green checks, `apply` merges the task into the run branch. Two rejections, or an escalation, hand it to a person |
| end | `apply` | Closes the Task sub-issues, brings `main` into the run branch, removes the task list, and marks the run pull request ready | **human**: a person merges the run into `main` |

People take part at two points: approving the spec, and merging the finished run. Everything between is agents, unless a gate hands something to a person, or a person changes the order of tasks with blocked-by relations on their sub-issues.

## Files

| From here | To your home repository | Notes |
|---|---|---|
| `.fab0/` | `.fab0/` | Edit `fab0.yaml` where it says `EDIT`. The rest works as is |
| `agents/*.md` | `.claude/agents/` | `spec-author`, `implementer`, `reviewer` |
| `skills/spec-format/` | `.claude/skills/spec-format/` | The spec and task list format |
| `hooks/merge-guard.py` | `.claude/hooks/merge-guard.py` | Blocks merges, pushes to `main` and force pushes the model issues |
| `claude-settings.json` | merge into `.claude/settings.json` | The `fab0` marketplace with auto-update, the plugin, deny rules and the merge guard hook |

Each file's first line names this example and its release. Keep it, so you can compare against a later release.

Instead of copying `agents/`, `skills/` and `hooks/`, you can install them as the `story@fab0-examples` plugin; see the [repository README](../README.md). The plugin brings the merge guard as its own hook. Then prefix the names in `.fab0/steps/`: `agent: story:spec-author`, `skills: [story:spec-format]`, and so on.

## Set up

### 1. Copy and edit

From your home repository, with this repository checked out beside it:

```bash
cp -R ../fab0-examples/story/.fab0 .fab0
```

```bash
mkdir -p .claude/agents .claude/skills .claude/hooks && cp ../fab0-examples/story/agents/*.md .claude/agents/ && cp -R ../fab0-examples/story/skills/spec-format .claude/skills/ && cp ../fab0-examples/story/hooks/merge-guard.py .claude/hooks/
```

Merge `claude-settings.json` into `.claude/settings.json`, or copy it there in a new project.

Edit `.fab0/fab0.yaml`:
- **`repos`:** this repository as `home`, and one entry per other repository tasks may change. Each is a sibling checkout on every machine that runs fab0. A repository's `owner` is the role whose turn its tasks are when a gate hands one to a person.
- **`people`:** the GitHub users in each role.
- **`tracker`:** the owner of the issues, and optionally a GitHub Project to show each item's state in a text field (`fields: {signal: <field name>}`).
- **`profiles`:** `cheap` runs the deep steps on a cheaper model: `/fab0:run <run> --profile cheap`.

### 2. GitHub

1. **Issue types:** the organisation needs `Story` and `Task`. An organisation owner adds them in the organisation's settings, under issue types.
2. **The base branch:** protect `main` with a ruleset that requires a pull request, with your tests as required checks. Leave `fab0/**` branches unprotected: `apply` merges approved tasks into run branches.
3. **Checks on run branches:** if your CI runs on pull requests into any branch, task pull requests get checks, and `apply` waits for them to pass before it merges.
4. **Board (optional):** a GitHub Project with a text field named as in `tracker.fields.signal`.
5. **Access:** everyone who runs fab0 needs `gh` logged in, with the `project` scope if there is a board: `gh auth refresh -s project`.

The `fab0:github` skill checks all of this: ask Claude Code to set up GitHub for fab0.

### 3. Claude Code

1. Install [`uv`](https://docs.astral.sh/uv/); the engine runs on it.
2. Open Claude Code in the home repository and trust the folder: Claude Code applies a project's marketplaces only in a trusted folder.
3. Install the plugin for this repository, once per clone:
   ```bash
   claude plugin install fab0@fab0 --scope project
   ```
4. Check the wiring; it must print `"ok": true`:
   ```bash
   fab0-resolve validate
   ```

## Use

1. Open an issue of type Story and write the intent in its body.
2. The product owner runs `/fab0:run <issue>`. The spec's pull request opens against the run branch. Ask for changes, or answer the agent's questions, with a **Comment** review or a conversation comment on the pull request, then run `/fab0:run <issue>` again. Either reaches the agent. On your own pull request GitHub allows only a **Comment** review, and that is enough; a plain conversation comment works too. Merging the pull request approves the spec.

   Keep the home checkout on `main` while a run goes on: the engine reads the wiring from it, and warns when it is on another branch.
3. Anyone runs `/fab0:run <issue>`. Tasks are implemented, reviewed and merged in parallel, as far as their files and dependencies allow. Run it again after a person answers questions or decides an escalation.
4. `/fab0:inbox` shows what each run waits for and on whom.
5. A person reviews the run pull request and merges it into `main`, which closes the Story.
