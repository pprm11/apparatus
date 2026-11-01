### Adapter: Codex

- Session start: read the current project's `MEMORY.md` and open only the relevant memories, following
  `context-recall`; to write, use `context-ingest`.
- Widgets: use the `visualize` plugin when the session has it; otherwise a markdown table.
- Model levels: use the model names the tool offers in the session, and report model and effort when
  delegating: low for mechanical work, medium for reading and writing, high or xhigh for the final judgment. If
  the chosen model is unavailable, say which one replaced it and why.
- Subagents: prefer the native tool when it lets you pick the model; give a self-contained brief; each writer
  works in its own worktree. Start a new thread only when a new session is requested. Without messaging between
  sessions, the child tells its parent with `decisions.py add "Notice to orchestrator: ..."`. For children in
  Claude run `python -I <apparatus>/tools/delegate.py run --brief-file <file> --cwd <repo> --to claude --tier mid
  [--write] [--background]`.
- Decision box: `python -I <apparatus>/tools/decisions.py list | add | resolve | apply`. The claude.ai page is
  republished by the daily Claude task; Codex only edits the data.
- No hooks: nothing blocks a secret in the prompt, nothing stops `find /` (the rule text applies) and nothing
  rebuilds the index by itself (`context-ingest` says to run the rebuild).
- Skills: the portable ones are in `~/.codex/skills` as links to `~/.claude/skills`; skills listed under
  `claude_only` in `harness/skills.json` are Claude-only.
- Jobs: do not run `weekly.sh` or register a scheduled task. Do not edit the copies in layer repos, which sync
  overwrites; edit in `~/.claude`, and sync regenerates `~/.codex/AGENTS.md`.
