---
level: superego
name: context-recall
description: "Search and verify existing shared project memory, rules and skills before answering or acting. Use for o que decidimos, lembra do, já falamos disso, quem aprova or where context is located; context-ingest handles authorized memory updates."
---

# context-recall

This is the user's canonical memory; do not use productivity:memory-management for it.

The effective context home is selected by the environment and company context. `search_memory.py` resolves
its default root; pass `--root <path>` explicitly when a different root is intended. A project memory has a
`projects/<key>/memory/MEMORY.md` index beneath its applicable context home. Follow the active harness policy
for its own memory sources and destinations.

## Steps

1. Current project index. `<key>` is the cwd with `:`, `\` and `/` replaced by `-`
   (for example `<home>\Codes\project-x`; the result is the folder name `<chave-do-projeto>`). Claude Code loads this index
   by itself; in other harnesses read `projects/<chave-do-projeto>/memory/MEMORY.md` beneath the effective context home, when applicable.
2. Open only the memory files whose index line matches the subject.
3. Not enough? Search every project, the rules and the skills (local, free, no network):
   ```bash
   python -I ~/Codes/superego/tools/search_memory.py "<terms>" -k 8
   ```
   Use the user's words plus the standard glossary term. Collision words such as "brain" also search their
   standard terms.
4. If local ranking is poor, consult the active company's declared reference or provider for any available
   semantic adapter and its conditions. Verify the adapter and follow its data-sharing and authorization
   requirements before sending content outside the machine.
5. Before acting on a memory, check it. Memories are dated: a file, flag, branch or PR they name may have
   changed. Verify it in the repo, git or the PR, and say what you verified.

## Output

Use what you found in the answer and cite the memory by `name`. If a memory turns out to be wrong or stale,
report the discrepancy and use `context-ingest` to fix it when memory writes are authorized. Follow the active
harness memory-write policy; a read-only recall does not itself authorize a write.

## Related

- [[context-ingest/SKILL|context-ingest]]: fix or save a memory found stale or missing
- [[rules/mapa-do-contexto|mapa-do-contexto]]: paths of each project MEMORY.md and the search tool
- [[backup-contexto-claude]]: how the shared memory is synced and backed up
- [[global/regras-de-agente]]: recall works the same in both harnesses
- [[global/ubiquitous-language|ubiquitous-language]]: glossary terms to use in search queries
