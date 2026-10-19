# fab0-examples

Example factories for [fab0](https://github.com/fab0-dev/fab0), the toolkit for building and operating software factories. Each example is a complete, working factory for one way of working: its `.fab0/` wiring, its agents and skills, and the settings it needs. Copy one into a project and make it yours.

## Examples

| Example | What it shows |
|---|---|
| [`story`](story/) | Delivery. A product owner approves a spec and task list; agents implement each task in parallel on sub-branches, another agent reviews and merges them into the run's branch, and a person merges the run into `main`, or `apply` does where the merge policy allows |
| [`feature`](feature/) | Composition. A Story of a Feature is specified, then built by connected factories side by side, each in its own repository, and wrapped up from what they hand back: follow-up Stories under the Feature, or the Feature closed |
| [`delivery`](delivery/) | A connected factory: one team's delivery, called by a parent such as `feature` or run on its own. It plans, provides a contract when other teams build against it, implements each task, and reports on its own area |
| [`triage`](triage/) | Not delivery. New bug reports are classified by an agent, checked by a command, labelled, and escalated when severe, all in the tracker, with no pull requests |

## Copy or install

**Copy** (recommended). The files become yours: versioned with your project, editable, and a diff against a newer release shows what changed. Every copied file names its source and release on its first line, for example `# from fab0-dev/fab0-examples story--v0.4.0`. Each example's README lists what to copy where.

**Install** the example's agents, skills and hooks as a plugin instead, if you want updates without owning the files. The wiring in `.fab0/` is always copied. Then name the agents and skills with the plugin's prefix in your steps, for example `agent: story:spec-author` and `skills: [story:spec-format]`.

```bash
claude plugin marketplace add fab0-dev/fab0-examples --scope project
```

```bash
claude plugin install story@fab0-examples --scope project
```

## Develop

Each example must work when copied into an empty repository:

```bash
scripts/check-examples
```

It copies each example as its README says, checks every file's source line, the JSON, and the merge guard, and runs `fab0-resolve validate`. It checks `feature` with a copy of `delivery` beside it for each factory it calls, so the connections are checked too. It uses the engine of a sibling `fab0-core` checkout, or `$FAB0_RESOLVE`. CI runs it on every change and weekly.

The agents are checked by running the `story` example, and the `feature` composition with two `delivery` factories, end to end, headlessly. It costs tokens, so run it by hand when an agent, a skill or the example's wiring changes:

```bash
python3 scripts/check-agents.py
```

```bash
claude plugin validate --strict .
```

## Licence

[Apache 2.0](LICENSE)
