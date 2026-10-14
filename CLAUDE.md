# fab0-examples

Example factories that projects copy. The product's home repo is `fab0-dev/fab0`, a sibling checkout; its `CLAUDE.md` holds the working rules and principles that apply here too. Until step R8 of its [REFACTOR.md](https://github.com/fab0-dev/fab0/blob/main/REFACTOR.md), that file governs, and nothing here is tagged.

- An example is a directory that is also a plugin of this repository's marketplace:
  - `.fab0/`: the wiring, copied as is into a project, then edited where it says `EDIT`;
  - `agents/`, `skills/`, `hooks/`: copied into the project's `.claude/`, or installed as the plugin;
  - `claude-settings.json`: merged into the project's `.claude/settings.json`;
  - `.claude-plugin/plugin.json`: the plugin, whose `version` is the example's release;
  - `README.md`: what it does, what to copy where, and the setup checklist.
- Every copied file names its source on its first line: `# from fab0-dev/fab0-examples <example>--v<version>` in YAML, text and scripts (after a shebang), `"$comment"` in JSON, `<!-- … -->` after a Markdown file's front matter. Releases are tagged `<example>--v<version>`.
- Agents are plain Claude Code agents (P1). Each works from a fab0 brief and by hand, describes its role and its output, and never names steps, pipelines or the agent that comes next.
- `questions` in a reply is left out or an empty list, never `null`.

## Checks

```bash
scripts/check-examples
```

```bash
claude plugin validate --strict .
```

After changing an agent, a skill or the `story` wiring, run `python3 scripts/check-agents.py`. It costs tokens.
