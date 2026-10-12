# fab0-recipes

Ready-made `.fab0/` setups for [fab0](https://github.com/fab0-dev/fab0): complete, working sets of wiring files for one way of working, which you copy into a project.

A recipe is copied, not installed:
- **The copied files are yours.** Edit them freely; your pipeline changes only through a commit in your project.
- **The recipe and the plugins move separately.** The behaviour the files point at (agents and skills) comes from plugins pinned by tag, and moves with the plugin tag. A recipe update reaches a project only when someone copies it again.
- **Every copied file names its source** on its first line, for example `# from fab0-dev/fab0-recipes story--v0.1.0`, so a later diff against a newer release is easy.

## Recipes

| Recipe | When to use it |
|---|---|
| [`story`](story/) | The core flow. A product owner's spec and task list is approved by merging its PR; each task is implemented and reviewed in its repository; one delivery PR closes the Story |

## Licence

[Apache 2.0](LICENSE)
