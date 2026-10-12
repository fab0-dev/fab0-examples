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

## Develop

Copy each recipe into an empty repo and validate it with the resolver of a sibling `fab0-core` checkout (or `FAB0_RESOLVE=<path>`):

```bash
scripts/check-recipes
```

CI runs the same check against the `fab0-core` release that the recipes' settings pin. When a recipe moves to a new release, change both that tag and the one in `.github/workflows/check.yml`.
