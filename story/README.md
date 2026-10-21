# `story` example

Delivery of one work item, a GitHub issue of type **Story**, on its own branch:

| Step | Who | What | Gate |
|---|---|---|---|
| start | `apply` | The run's **Pipeline Run**: an issue in the runs repository, under the Story, whose number is the run id, with a **Pipeline Step** sub-issue per step. The run branch `fab0/<run>/base` in every repository the run writes. A repository gets its draft run pull request into `main` once its run branch has work | — |
| `spec` | `spec-author` agent | The spec (Markdown), a file in the runs repository: `runs/<factory>/<run>/spec.md` | **human, in a pull request:** the product owner approves the spec's pull request in the runs repository; fab0 merges it |
| `plan` | `planner` agent | The task list (YAML), from the approved spec: `runs/<factory>/<run>/tasks.yaml` | **human, at the prompt:** the product owner confirms it in the run session, or rejects it with what to change |
| tasks | `apply` | A Task sub-issue per task, blocked by the sub-issues of the tasks it depends on | — |
| `implement`, per task | `implementer` agent | The task's files, with tests, on `fab0/<run>/implement-<task>`. Tasks run in parallel where their files don't overlap and their order allows | **auto:** the `reviewer` agent; on approval and green checks, `apply` merges the task into the run branch. Two rejections, or an escalation, hand it to a person |
| end | `apply` | Closes the Task sub-issues, brings `main` into the run branch, and merges each run pull request into `main` once its required checks pass, which closes the Story | — |

Your repositories receive only the tasks' changes. The spec and the task list are files of the runs repository, a repository beside yours that every fab0 factory of the product shares; they reach its `main` with the run. A repository the run only reads gets no commit and no pull request.

The run's state is on its issues in the runs repository, where anyone can follow it:
- the Pipeline Run's fields say where it stands (`Stage`, the `Step` in progress, who it is `Waiting on`);
- each Pipeline Step's fields say its `Revision` and its `Output`: its pull request while it is in review, then the commit it was accepted at;
- their comments are the run's log, and each closes when it is done.

People take part at two points: approving the spec in its pull request, and confirming the task list at the prompt. Everything else is agents and `apply`, merges into `main` included, unless a gate hands something to a person, or a person changes the order of tasks with blocked-by relations on their sub-issues. To keep a person on the merge into `main`, end the pipeline with `pr.ready` in place of `pr.merge`: the run pull requests are marked ready, and the run is done once a person has merged them.

## Files

| From here | To your home repository | Notes |
|---|---|---|
| `.fab0/` | `.fab0/` | Edit `fab0.yaml` where it says `EDIT`, and replace `OWNER` and `REPO` everywhere. The rest works as is |
| `agents/*.md` | `.claude/agents/` | `spec-author`, `planner`, `implementer`, `reviewer` |
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

Replace `OWNER` with your organisation and `REPO` with this repository's name, everywhere in `.fab0/` (here `acme` and `shop`). `REPO` is also the factory's name: it keeps this factory's files apart from other factories' in the runs repository.

```bash
perl -pi -e 's/OWNER/acme/g; s/REPO/shop/g' $(grep -rlE 'OWNER|REPO' .fab0)
```

Then edit `.fab0/fab0.yaml`:
- **`repos`:** this repository as `home`, and one entry per other repository tasks may change. Each is a sibling checkout on every machine that runs fab0. A repository's `owner` is the role whose turn its tasks are when a gate hands one to a person.
- **`repos.runs`** and **`tracking`:** the runs repository, a sibling checkout too. If the product already has one, for another factory, name the same one.
- **`people`:** the GitHub users in each role.
- **`tracker`:** the owner of the Stories, and optionally a GitHub Project to show each item's state in a text field (`fields: {signal: <field name>}`).
- **`profiles`:** `cheap` runs the deep steps on a cheaper model: `/fab0:run <run> --profile cheap`.

### 2. GitHub

1. **Issue types:** the organisation needs `Story` and `Task`, and the run tracker's `Pipeline Run` and `Pipeline Step`. An organisation owner adds them in the organisation's settings, under issue types.
2. **Issue fields**, in the organisation's settings too, enabled on `Pipeline Run` and `Pipeline Step`: `Run ID` (text), `Stage` (single select: `Todo`, `In Progress`, `Done`), `Pipeline`, `Factory`, `Step`, `Waiting on` and `Output` (text), and `Revision` (number). `validate` checks each one.
3. **The runs repository**, if the product has none yet:
   - private if your GitHub plan allows a ruleset on a private repository;
   - a ruleset on `main` that requires a pull request and blocks force pushes and deletion;
   - write access for everyone in `people`. The product owner approves spec pull requests there, with an approving review, or a comment `/approve` on one they opened, and fab0 merges them: nobody merges or pushes there by hand.
4. **The base branch** of each of your repositories: a ruleset that requires a pull request, with your tests as required checks. `apply` merges each run pull request on GitHub once they pass, so the ruleset applies to it too. Leave `fab0/**` branches unprotected: `apply` merges approved tasks into run branches.
5. **Checks on run branches:** if your CI runs on pull requests into any branch, task pull requests get checks, and `apply` waits for them to pass before it merges.
6. **Board (optional):** a GitHub Project with a text field named as in `tracker.fields.signal`.
7. **Access:** everyone who runs fab0 needs `gh` logged in, with the `project` scope if there is a board: `gh auth refresh -s project`.

The `fab0:github` skill checks all of this, and creates the runs repository when you ask: ask Claude Code to set up GitHub for fab0.

### 3. Claude Code

1. Install [`uv`](https://docs.astral.sh/uv/); the engine runs on it.
2. Open Claude Code in the home repository and trust the folder: Claude Code applies a project's marketplaces only in a trusted folder.
3. Install the plugin for this repository, once per clone:
   ```bash
   claude plugin install fab0@fab0 --scope project
   ```
4. Check the wiring; it must print `"ok": true`. It also checks the run tracker's issue types and fields:
   ```bash
   fab0-resolve validate
   ```

## Use

1. Open an issue of type Story and write the intent in its body.
2. The product owner runs `/fab0:run #<issue>`. The run's Pipeline Run opens in the runs repository, under the Story, and its number is the run id. The spec's pull request opens in the runs repository.
   - **Ask for changes**, or answer the agent's questions, with a Comment review or a conversation comment on the pull request, then run `/fab0:run` again: with one run open, it needs no argument. On your own pull request GitHub allows only a Comment review, and that is enough.
   - **Approve** with an approving review by someone in `product-owner`. GitHub doesn't let you approve a pull request you opened, which fab0 did with your login when you ran it: comment `/approve` instead. An approval counts for the version the pull request holds when it is given.
   - The next `/fab0:run` merges it. Don't merge it yourself.

   Keep the home checkout on `main` while a run goes on: the engine reads the wiring from it, and warns when it is on another branch.
3. The planner writes the task list, and the session asks the product owner to confirm it: yes, or what to change, which the planner reworks. When whoever runs the session isn't in `product-owner`, the step waits, assigned to the product owner, until they run `/fab0:run`.
4. Anyone runs `/fab0:run`, or `/fab0:run <run>` with several runs open. Tasks are implemented, reviewed and merged in parallel, as far as their files and dependencies allow. Run it again after a person answers questions or decides an escalation.
5. `/fab0:inbox` shows, from the tracker, where each run is, what it waits for and on whom.
6. The run ends by itself: each run pull request merges into `main` once its required checks pass, which closes the Story, and the Pipeline Run closes with a summary of every step.

## Keep the specs in your repository

The spec here is a file of the runs repository. If your product keeps its specs with its code, make it a file of your home repository:

1. In `.fab0/artifacts/spec.yaml`: `file: {repo: home, path: "specs/{run}.md", format: markdown}`.
2. In `.fab0/steps/spec.yaml`: `repos: {write: [home], read: [all]}` and `paths: ["specs/{run}.md"]`.
3. In `.fab0/pipelines/story.yaml`, the spec's `done`: `{pr: {repo: home, state: approved}}`.

The spec's pull request then opens in your home repository against the run branch, and reaches `main` with the run. Do the same for the task list, or leave it in the runs repository.
