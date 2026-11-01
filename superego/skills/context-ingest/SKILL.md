---
level: superego
name: context-ingest
description: "Save an authorized fact in shared Claude Code and Codex memory, with deduplication, keywords and index rebuild. Use for "remember this", "save this", "save to memory" or an authorized correction; context-recall finds and verifies existing facts."
---

# context-ingest

This is the user's canonical memory; do not use productivity:memory-management for it.

A recall that discovers a stale fact does not by itself authorize a memory write. Follow the active harness
memory-write policy, including any restricted destination, before applying this workflow. The context home is
resolved by the environment and company context; `search_memory.py` resolves its default root. Pass
`--root <path>` when an explicit different root is intended and authorized.

## What is worth saving

Save: who the user is and how they want things done (`user`, `feedback`), ongoing work, decisions and
constraints the code does not show (`project`), and pointers to outside systems (`reference`).
Skip: what the repo, git history or a CLAUDE.md/AGENTS.md already records, and anything only this
session needs. A rule that holds in every project goes to `proposals.md`, not to memory (step 6).

## Steps

1. Look for an existing memory first. Read the project's `MEMORY.md` and run
   `python -I <your-folder>/superego/tools/search_memory.py "<terms>"`. If one covers the subject, update
   it. Do not create a second one.
2. When the harness permits this destination, write `<context-home>/projects/<key>/memory/<slug>.md` (`<key>` = cwd with `:`, `\`, `/` turned into `-`):
   ```markdown
   ---
   name: <slug, short-kebab-case>
   description: <one line used to decide relevance>
   metadata:
     keywords: <6 to 15 terms, in the user's language and English: synonyms, acronyms, people, systems, how the user would ask>
     type: user | feedback | project | reference
   ---
   <the fact, in the user's language. feedback/project add **Why:** and **How to apply:** lines.
   Absolute dates (2026-10-26), never "yesterday". Link related memories with [[their-name]].>

   ## Related

   - [[<memory-name>]]: why, in at most 10 words
   - [[<skill>/SKILL|<skill>]]: the skill that applies this fact
   - [[rules/<rule>|<rule>]]: the rule it backs, if any
   ```
   Every memory ends with a `## Related` block of 1 to 4 links (memories, skills, rules), so it is not an
   orphan in the Obsidian graph. Check with `python -I <your-folder>/superego/tools/graph_view.py --check`.
3. Add or update one line in that folder's `MEMORY.md`: `- [Title](<slug>.md) — hook`. The index has no
   memory content and no frontmatter.
4. Rebuild the search index. Claude Code does this through a hook; in any other harness, run:
   ```bash
   python -I <your-folder>/superego/tools/search_memory.py --build --quiet
   ```
5. If `<your-folder>/superego/.work/weekly.lock` exists, the weekly pass is rewriting memory. Wait, or
   tell the user and save after it ends.
6. Schema files (`~/.claude/CLAUDE.md`, `agent-rules.md`, `ubiquitous-language.md`, `rules/`,
   `harness/`) change only after the user says yes. Without that, append a `P-<date>-<n>` proposal to
   `<your-folder>/ego-<company>/proposals.md`.

## Never

Secrets, tokens, client personal data or raw conversation text. Check the effective context home and its
sync configuration: applicable context content may reach layer repositories within an hour.

## Related

- [[context-recall/SKILL|context-recall]]: look up memory before saving a new one
- [[rules/context-map|context-map]]: where each kind of context lives
- [[backup-contexto-claude]]: sync hourly and weekly pass that carry the saved memory
- [[global/agent-rules]]: every saved rule must hold in both harnesses
- [[global/agent-rules|agent-rules]]: schema file that changes only with the user's yes
