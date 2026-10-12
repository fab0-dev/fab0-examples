# `story` recipe

The core fab0 flow for one work item, a GitHub issue of type **Story**:

| Stage | Who | What | Gate |
|---|---|---|---|
| `spec` | product owner | `fab0:spec-author` writes `specs/<run>.md` and `work/<run>/tasks.yaml` | merging the spec PR |
| `plan` | anyone (action) | Task sub-issues from `tasks.yaml`, each assigned to its repo's owner, with blocked-by links | — |
| `implement` (per task) | the task repo's owner | `fab0:implementer` changes the task's files, with tests | `fab0:reviewer`, on a different model; then merging the task PR |
| `deliver` | anyone (action) | Appends the review results to the spec and removes `work/<run>/tasks.yaml`, in a PR that closes the Story | merging the delivery PR |

Use it when one spec should drive work in one or more repos that share a process. Repos that work differently are the case for nested pipelines, which come later.

## Files

| File | Copy to | Notes |
|---|---|---|
| `.fab0/` | `.fab0/` in the home repo | Edit `fab0.yaml`. The other files work as they are |
| `claude-settings.json` | merge into `.claude/settings.json` | Declares the `fab0` marketplace at a release tag, enables `fab0@fab0`, and denies merging, force pushes, pushes to `main` and edits under `.github/` |

Each file's first line names this recipe and its release. Keep that line, so you can compare against a later release.

## Set up

### 1. Copy and edit

From your home repo (the repo that will hold `.fab0/`, the specs and the run ledgers):

```bash
cp -R ../fab0-recipes/story/.fab0 .fab0
```

Edit `.fab0/fab0.yaml` where it says `EDIT`:
- **`repos.home.github`**: this repo, as `owner/name`.
- **`people`**: the GitHub users in each role. `product-owner` writes and approves specs. The role in a repo's `owner` field gets that repo's tasks, and the delivery PR when the repo is the home repo.
- **`tracker`**: the project owner and number.
- **More repos:** add one entry per repo. Paths are relative to the home repo, and each needs a `key` of two or three capital letters:
  ```yaml
  repos:
    home:    {path: ., github: acme/product, owner: product-owner}
    backend: {path: ../backend, github: acme/backend, owner: backend, key: BE}
    web:     {path: ../web, github: acme/web, owner: frontend, key: FE}
  ```
  Every repo is a sibling checkout on each person's machine.

Merge `claude-settings.json` into `.claude/settings.json`. In a new project, copy it as `.claude/settings.json`.

### 2. GitHub

1. **Issue types:** the organisation needs `Story` and `Task`. An organisation owner adds them under Settings → Planning → Issue types.
2. **Project:** one GitHub Project with three fields. fab0 writes these three and never Status.
   ```bash
   gh project field-create <number> --owner <owner> --name Stage --data-type SINGLE_SELECT --single-select-options "spec,plan,implement,deliver,done"
   ```
   ```bash
   gh project field-create <number> --owner <owner> --name Run --data-type TEXT
   ```
   ```bash
   gh project field-create <number> --owner <owner> --name "Waiting on" --data-type TEXT
   ```
   In the project's settings:
   - turn on the built-in workflows: auto-add issues from your repos, item added → Todo, item closed → Done;
   - add the views:
     - **My turn**: assignee is @me, grouped by Stage;
     - **Board**: grouped by Stage;
     - **Waiting**: `Waiting on` is set;
     - **Hierarchy**: Stories with sub-issue progress.
3. **Branch protection** on `main` of every repo: pull requests required, your linters and tests as required checks, and reviews as your team chooses. fab0 never merges; people do.
4. **Access:** everyone who runs fab0 needs `gh` logged in with the `project` scope:
   ```bash
   gh auth refresh -s project
   ```

### 3. Claude Code

1. Install [`uv`](https://docs.astral.sh/uv/); the resolver runs on it.
2. Open Claude Code in the home repo and **trust the folder**. Claude Code applies a project's marketplaces only in a trusted folder, and ignores them silently otherwise.
3. `/plugin` lists `fab0@fab0`.
4. Check the wiring; it must print `"ok": true`:
   ```bash
   fab0-resolve validate
   ```

## Use

1. Open an issue of type Story, write the intent in its body, and add it to the project.
2. The product owner runs `/fab0:run <issue number>`. The spec PR opens; reviewers request changes with a PR review, and `/fab0:run` revises the spec.
3. Merging the spec PR approves it. `/fab0:inbox` then shows the pending `plan` to everyone, and each person's tasks once they are unblocked.
4. Each developer runs `/fab0:run <issue> --task T<n>`. The reviewer agent gates the result before its PR opens.
5. Once every task PR is merged, anyone runs `/fab0:run <issue>` for the delivery PR. Merging it closes the Story.
