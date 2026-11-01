### Adapter: Claude Code

- Widgets: use the `show_widget` tool of the visualize server when a persona skill asks for an inline answer;
  call `read_me` of that server silently the first time in a session.
- Model levels: cheap = Haiku, mid = Sonnet, top = Opus. Pass `model` on every `Agent`, `Workflow` and
  `start_session` call.
- Subagents: in the same harness use `Agent`; for several at once use `Workflow`. For children in Codex run
  `python -I <apparatus>/tools/delegate.py run --brief-file <file> --cwd <repo> --to codex --tier mid
  [--write] [--background]`; the helper uses the model configured in Codex, so check the command before saying
  which model ran.
- Orchestrator routes, child reports: start a child with `start_session`; the child tells its parent with
  `SendMessage` to the id in `startedBy` (`list_sessions` with `linked: true`).
- Hooks: `hook-prompt-guard.py` (secret in the prompt), `hook-bash-guard.py` (denies `find`, `grep -r`, `rg`,
  `ls -R`, `du` and `tree` from `/`, `/proc` or the whole disk) and `index_hook.py` (rebuilds the search index
  when a memory, rule or skill is written).
- Memory: the harness loads the project's `MEMORY.md` itself; to write, follow the `context-ingest` skill.
- Jobs: the hourly sync and the weekly job run under the Claude login. See the README of the `self` repo.
