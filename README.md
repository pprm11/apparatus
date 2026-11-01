# superego

General harness layer of an agent context, shared by Claude Code and Codex. It holds what does not
depend on a company or on the user as a person: the tooling (`tools/`), the sync, harvest and weekly scripts,
generic skills (`skills/`), agent rules (`global/`, `rules/`), the harness adapters (`harness/`) and the
search evals. Company content lives in an ego layer (`ego-<company>`), personal content in `id-context`.
The meta repo `psique` ties the three together with `manifest.json`.

`~/.claude` stays the source of truth. Codex gets a rendered copy (`tools/render_harness.py`).

## Levels and routing

| Level | Repo | What |
|---|---|---|
| superego | this repo | tools, generic skills, agent rules, harness adapters |
| ego | `ego-<company>` (for example `ego-<company>`) | project memories, work skills, glossary, team maps, plans |
| id | `id-context` | personal development plan, career, preferences, settings; sensitive paths are sealed |

Three things decide where a file goes:

1. `level:` in the frontmatter of a memory or of a skill's `SKILL.md` (`superego`, `ego` or `id`). A file
   without it goes to the manifest's `default_level`, normally `ego`. `tools/layers.py unlabeled` lists
   those files, and sync adds one decision-inbox item when there are any.
2. `layer.json` at the root of each layer repo lists what that layer owns outside memories and skills:
   `globals` (files at the root of `~/.claude`, copied to `global/`), `rules` (files of `~/.claude/rules`),
   `dirs` (folders mirrored as they are), `files` (single files copied to the same relative path) and, for
   the id layer, `sealed` paths. A memory may also carry `sealed: true` in its frontmatter: the export skips it
   under any project key, so a repo move (which renames the key) cannot leak it the way a fixed path did on
   31/10/2026; the id repo's `seal.sh` and pre-commit honor the same flag.
3. `psique/manifest.json` names the active layers in load order, with the local path and the GitHub repo
   of each, and the default level.

`tools/layers.py export` copies each file to its layer repo and removes files under the managed folders
that the export did not produce, so a memory whose `level:` changed moves to the other repo on the next
sync. The repo's own files (README, `layer.json`, `.gitignore`, `tools/`, `tests/`) are never touched.
`tools/compose.py` writes the root `~/.claude/CLAUDE.md` from the layers' global files, in manifest
order, and appends any `MEMORY.md` index lines a layered restore left out.

## Installing for another person

A teammate who is not the owner installs with `install.sh` (macOS, Linux) or `install.ps1` (Windows), which find
Python 3.10+ and run `tools/onboard.py`. `init` creates the person's own private `psique` and `id-context` repos from
`templates/psique` and `templates/id`, clones the shared layers read-only (`--layer collective:NAME=URL`,
`--layer ego:NAME=URL`), restores them into `~/.claude`, composes `CLAUDE.md` and `AGENTS.md`, registers one
Python `update` job for the OS and runs the doctor (profile `person`: no vault, no bash). `update`, `contribute`
(PR from a worktree) and `uninstall` come with it. A privacy gate (`ci/privacy-terms.json`, `tools/privacy.py`)
scans the layers before they are restored and the composed files after, and refuses the owner's personal or other
companies' repos. Skills that cannot ship yet are listed in `layer.json` under `install_exclude`. Guide in
Portuguese: [docs/instalar.pt-BR.md](docs/instalar.pt-BR.md). Tests: `tests/test_onboard.py` and the end-to-end
`tests/e2e_onboard.py` (CI job `onboarding`, three OS).

## Readonly layers (collective)

A layer entry in `psique/manifest.json` with `"mode": "readonly"` is a shared repo that many people consume
(the `collective` level, between superego and ego). It is restored and composed like any layer, but
`layers.py export --all` skips it, `sync.sh` never commits or pushes into it, and `layers.py pull` brings it
to the entry's `ref` (tag or SHA) or fast-forwards it. Its skills carry `level: collective`, so a restored
copy in `~/.claude/skills` is not routed into the ego repo. Off by default (`"active": false`).
Its always-loaded files count against the same 32 KiB Codex budget as every other layer.

## Routines

| Task | When | What | Cost |
|---|---|---|---|
| `ClaudeContextSync` | every hour | `sync.sh --push [--manifest M]`: exports every active layer, lints each layer's memory into `lint-report.md` (local, not versioned), renders the Codex copy, then commits and pushes each layer repo in up to three Conventional Commit groups (`chore(memory)`, `chore(context)`, `chore(state)`) | no model |
| `ClaudeContextHarvest` | every hour at :30 | `harvest.sh`: each session the user archived becomes a redacted digest (`tools/harvest.py`); Sonnet (`prompts/harvest.md`) writes a memory or a skill draft only when worth it. Memories go to `~/.claude` and reach their layer on the next sync; the harvest log goes to the ego layer's `log.md` | Claude login, `--max-budget-usd 0.60` per session, at most 6 sessions per run, 20 per day |
| `ClaudeContextWeekly` | Mondays 09:00 | `weekly.sh`: decay score, then Sonnet reads the week's prompts and the ego layer's memory, fixes lint findings, adds memories, writes proposals and a report in the ego repo, commits there and syncs | Claude login, `--max-budget-usd 3`; API keys are unset |
| `caixa-de-decisoes-diaria` (Claude desktop scheduled task) | daily 09:00 | scans the decision inbox, republishes the pinned page, asks what is open | one Claude session |

`psique/schedule.ps1` registers the Windows tasks. All scripts take `--manifest` (default
`$SYNC_MANIFEST`, then `~/Codes/psique/manifest.json`). Tools, prompts, `.work/`, `.harvest/` and the
locks (`.sync.lock/`, `.memory.lock/`) stay in this repo; the weekly pass holds `.sync.lock/` for its whole
run, so a skipped hourly sync exits 75. `sync.sh` refuses to run without `~/.claude/CLAUDE.md` and 20 or
more memories, aborts when a layer would lose more than 50 tracked files in one commit, and never commits a
file over 1 MB (it unstages it and adds an inbox item).

Known limitation: only the ego layer's memory is maintained by the weekly and harvest passes (lint fixes,
compile, merges, log, proposals, reports). Superego and id memories are edited by hand or by the
`context-ingest` skill, and the passes do not lint-fix or merge them. The lint report still covers all
layers.

## Restore on a new machine

Needs Git for Windows, Python 3.10+, GitHub CLI and Claude Code. The normal path is `psique/restore.sh`,
which clones the three layers, restores them in order (this repo's `restore.sh --from <layer>` runs once per
layer), composes `CLAUDE.md` and registers the tasks. To restore only this layer:

    git clone --filter=blob:none https://github.com/<user>/superego ~/Codes/superego
    ~/Codes/superego/restore.sh --from ~/Codes/superego
    claude /login

`--filter=blob:none` fetches history blobs on demand, so the clone is about the size of the current tree.
Size watch: when a layer's history passes about 50 MB, archive it with `git bundle create` and restart
history from the current tree. That rewrites the remote (force push) and needs the user's yes first.

Memory folders are keyed by project path (the folder name, called `<chave-do-projeto>` in the docs, is the project path with `:`, `\` and `/` replaced by `-`). Clone the projects to the same
paths under the same Windows user, or rename the folders in `~/.claude/projects/`.

## Harnesses

Harness-specific names (tools, models, hooks) live only in `harness/<harness>.md`; the rules speak of model
tiers (cheap, mid, top). Claude Code reads `~/.claude/CLAUDE.md` with `@` imports. Codex reads a generated
`~/.codex/AGENTS.md` (imports inlined, adapter `harness/codex.md`, then `rules/*.md`, under 32 KiB) and
junctions to every skill not listed in `harness/skills.json`. `tools/codex_sessions.py` reads
`~/.codex/sessions` for `extract_prompts.py`.

## Memory search

`tools/search_memory.py "<terms>"` searches every project's memory, `~/.claude/rules/` and skills locally
(BM25 over name, `keywords`, description and body, accent insensitive). `--build` writes `index/` and
`INDEX.md` in this repo; both are ignored by git and regenerated by sync. `tools/eval_search.py` measures
hit@1 and hit@3 on `evals/`. `tools/jev_search.py "<question>"` reranks the local hits through an LLM
gateway after `tools/redact.py` strips secrets and personal data (`--dry-run` prints the payload; it needs
`LITELLM_API_KEY` and falls back to the local ranking on any error).

## Decision inbox

Everything waiting on the user, in either harness: `~/.claude/decisions/inbox.json`, managed by
`tools/decisions.py` (`scan`, `list`, `add`, `resolve D-12 A`, `apply`, `applied`, `html`). Each item has a
`level` (`superego`, `ego` or `id`; old items without one are ego). `add --level L` sets it and
`list --level L` filters. `decisions.py export --level L` prints the store with only that level's items, and
sync writes it to `decisions/inbox.json` of that layer repo; `decisions.py import FILE` merges such a file
back (newer item wins, ids never collide), which `restore.sh` does for each layer. `scan` fills the inbox
from waiting or idle sessions, open proposals, skill drafts and dormant items. The pinned page
(`~/.claude/decisions/config.json`) hides personal (`id`) items. Nothing is archived, installed or approved
without the user's answer.

## Self-learning loop

`tools/learn.py` notices what the user repeats, corrects and decides, and turns it into proposals, memories
and inbox items. It is off unless `HARVEST_LEARN=1` is set where `harvest.sh` and `weekly.sh` run. It reads the
new user turns of every Claude Code and Codex session, live or archived (sessions run inside a layer repo are
skipped), and keeps a redacted ledger in `~/.claude/decisions/learning/` (`signals.jsonl`, `state.json`). That
folder is local: only `decisions/inbox.json` is mirrored to the layers.

| Step | What | Model |
|---|---|---|
| extract | each user turn is a `correction`, a `decision` (an approval answering a question the agent asked) or a `prompt` | none |
| cluster | prompts and corrections sharing keywords; a candidate repeats on 2+ days (3+ prompts, 2+ corrections) and is under 80% covered by the global files, rules, skills and memory | none |
| classify | which candidates are real; which decisions are durable (`memory`, `inbox`, `none`) and their `level` | Haiku, 25% of the run budget |
| write | proposal and memory text; Python writes the files | Sonnet, the rest |
| effects (weekly) | matching signals in the 14 days before vs after each approved proposal; `worked` if they fell by half or more | none |

Routing: a repeat becomes an entry in the ego layer's `proposals.md` (`Status: open`, `Level:`, `Source: learn`);
instruction files are never written, the user approves each proposal. A durable decision becomes a new memory
with `level:` in its frontmatter (so sync routes it to the right layer) in the memory folder the model picked
among the existing ones, unless it overlaps an existing memory (keyword Jaccard >= 0.5, any project); a decision
that still needs an action becomes an inbox item with that level. `learn.py applied P-... [--date]` starts the
before/after clock (the weekly pass also starts it the first time it sees `approved`).

The ego folder comes from `--ego`, `$LEARN_EGO` or the manifest. Cost: `LEARN_BUDGET_USD` per run (default 0.40)
and `LEARN_BUDGET_DAY_USD` per day (default 1.00), summed from the `total_cost_usd` that `claude -p` reports.
Model steps run at most once a day unless new decisions arrived. Caps per run: 12 candidates, 3 proposals, 3
memories, 15 decisions. Ledger text is cut to 160 characters and passed through `tools/redact.py` before it is
stored or sent to a model. Only the Claude job calls a model; Codex sessions are read like Claude ones.

    python -I tools/learn.py run --dry-run        # counts and the payload that would go to a model, writes nothing
    python -I tools/learn.py run --no-models      # extract and cluster only
    python -I tools/learn.py effects              # before/after table
    python -I tools/learn.py status | hint        # state; `hint` prints Conventional Commit subjects for the last run

Commits stay distinguishable by subject: `docs(proposal)` for new proposals, `chore(memory)` for memories,
`feat(learning)` for code and `reports/learning-*.md`.

## Decay

`tools/decay.py` scores every memory and skill with R = exp(-t / S), S = base x (1 + ln(1 + uses)), base 45
days for memories and 60 for skills; uses and t come from the transcripts of both harnesses (180-day
window). Sessions run from the context repos (`SKIP_PROJECTS`) are excluded because they read everything on
purpose. R < 0.5 is dormant and goes to the inbox, where "archive" moves the file to `~/.claude/archive/`
and "pin" exempts it. Memories of type user or feedback, `pinned: true`, skills pinned in
`harness/skills.json`, rules and schema never decay.

## Cross-harness children

`tools/delegate.py run --brief-file f --cwd repo --tier cheap|mid|top [--write] [--background]` runs a child
agent in the other harness (`codex exec` from Claude, `claude -p` from Codex). `--write` gives it a worktree
on `delegate/<run-id>`; children cannot delegate again; Claude children have a USD cap, Codex children a
timeout. Runs live in `runs/` (ignored by git, pruned after 14 days). Procedure: skill `orquestrar-cruzado`.

## Starting a company layer

Copy `templates/ego/` to a new repo and follow its README. The personal layer starts from `templates/id/`
(PDI, personal preferences, sealed paths); see its README. Tests: `python -I -m unittest discover -s tests`
(offline).

## Automatic encrypted backup of secret files (age)

`tools/secrets_backup.py` keeps `.env*`, `*.pem`, `*.key`, SSH private keys, `pgpw.txt` and `credentials*` encrypted in the
id layer (`<id repo>/sealed/secrets/`), with no unlock day to day: encrypting needs only the age PUBLIC key.

| Piece | Where |
|---|---|
| Paths to protect (paths only) | `~/.claude/scripts/secrets-manifest.txt` (id layer); new finds are appended automatically |
| Public key | `AGE_RECIPIENT` or `~/.config/id-context/recipient` (the same file `id-context/tools/seal.sh` uses) |
| Last-seen sha256 (no values) | `~/.claude/state/secrets-hashes.json`; only files whose hash changed are re-encrypted |
| Output | `<id repo>/sealed/secrets/<id>.age` + `manifest.json.age`; the destination must be a repo whose `layer.json` level is `id` (default: the id layer of `~/Codes/psique/manifest.json`, or `SECRETS_DEST`) |
| Private key | Bitwarden note `age-identity` (`restore --identity-from-bw`), never on disk after the restore |

`sync.sh` runs `secrets_backup.py run` every hour when `SECRETS_BACKUP=1` (`setx SECRETS_BACKUP 1`). The id repo's own commit and
push carry the `.age` files; its `.gitignore` lets nothing else through `sealed/`. The walk of `~/Codes` takes about a minute, so it runs
at most every 6 hours (`SECRETS_SCAN_HOURS`); `run --full-scan` forces it. New files, vanished files and failures arrive in the
decision inbox (level id). Files that vanish stay in the backup. `~/.codex/auth*` is scanned only with `SECRETS_INCLUDE_CODEX_AUTH=1`.

Restore (one manual Bitwarden unlock; never overwrites existing files):

```bash
export BW_SESSION="$(bw unlock --raw)"
python -I ~/Codes/superego/tools/secrets_backup.py restore --identity-from-bw
```

CI gates and how to run them locally: `docs/ci-gates.md` (`python -I ci/gates.py`).

## Push guard (no force push or delete of `main`)

Private repos on a free GitHub plan have no rulesets or branch protection (the API answers 403). `tools/push_guard.py`
is the local substitute: `sync.sh` installs a `pre-push` hook in every layer repo it syncs, and the hook refuses
deleting `main` and any non-fast-forward update of it. The hourly sync only fast-forwards, so it is not affected.
It sees only pushes made from a clone that has the hook; another machine or the web UI is not covered.
A deliberate rewrite: `PUSH_GUARD_ALLOW=1 git push ...` (the hook says it was used). Other protected branches:
`PUSH_GUARD_BRANCHES="main,release"`. An existing pre-push hook that is not ours is kept, and the install says so.

