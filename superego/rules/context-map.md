# Agent context map (where each thing lives)

Holds for Claude Code and Codex. The source of truth is the Claude home (`~/.claude`); Codex reads the same
content from a generated `~/.codex/AGENTS.md` (`render_harness.py`; do not edit the generated file).

Each layer (see the superego glossary) is a repo under the layers root; the `self` repo generates the root
`CLAUDE.md`. Every memory and every skill carries `level:` in its frontmatter; without it the manifest's default
level applies. Every layer has a glossary (the `glossary` field of `layer.json`, same format: version,
collisions, standard terms, how to read requests); sync runs `tools/lint_glossary.py` and stops an undeclared
collision.

Always loaded: `~/.claude/CLAUDE.md` (generated: the globals of each layer in order, plus the adapter
`harness/<harness>.md`) and `~/.claude/rules/*.md`. Change these files only with the user's yes.

Memory is split by project under `~/.claude/projects/<key>/memory/`, each with a `MEMORY.md` index. Only the
index of the current project is loaded. When the subject belongs to another project, read that project's
`MEMORY.md`.

To search beyond the current index use `context-recall`; to save a memory and rebuild the index use
`context-ingest`.

Procedures live in `~/.claude/skills/` (the portable ones also in `~/.codex/skills/`, as links). Scripts live in
`~/.claude/scripts/`. A personal skill, hook or script stays there and never goes into a branch or PR of a team
repo: a team repo receives only changes in the scope of its task.
