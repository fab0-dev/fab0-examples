# fab0-recipes

Recipes: complete `.fab0/` setups that projects copy. The product's home repo is `fab0-dev/fab0`, a sibling checkout; its `CLAUDE.md` holds the working rules and principles that apply here too.

- Each recipe is a directory with:
  - a `README.md`: when to use it, how to copy it, its setup checklist;
  - a `.fab0/` that copies as is;
  - `claude-settings.json`, the settings to merge into the project's `.claude/settings.json`.
- Every file under `.fab0/` starts with `# from fab0-dev/fab0-recipes <recipe>--v<version>`. Releases are tagged `<recipe>--v<version>`.
- A recipe must pass `fab0-resolve validate` when copied into an empty repo. `scripts/check-recipes` does this against the resolver of a fab0-core checkout or tag.
- Recipes hold wiring only. Agents, skills and scripts belong in plugins (`fab0-dev/fab0-core`, `fab0-dev/fab0-plugins`).
