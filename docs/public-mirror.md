# Public mirror

The superego is the generic layer: rules and tools that are the same for any person. The `deny` gate
(`docs/ci-gates.md`) keeps every private name, machine path, company and person out of its tree, and the baseline of
known violations is empty. That makes the committed tree safe to publish. The history is not: old commits still hold
what the gate now forbids. The public copy keeps **snapshot history without source history**. Each publish adds
one commit whose single parent is the previous mirror commit.

## How it works

`tools/mirror_public.py` takes the committed tree of `HEAD` (not the working tree) and:

1. lists the tracked files and drops the ones that are never published: `runs/`, `index/`, `.work/`, `.harvest/`,
   `.staging/`, generated files (`INDEX.md`, `lint-report.md`, `AGENTS.md`, `CLAUDE.md`) and the deny baseline
   (`ci/*baseline*`). Files under `ci/` are excluded except the runtime data in the named `PUBLIC_CI_FILES`
   allow list. Its entry is `ci/privacy-terms.json`, needed by the installer and privacy scanner;
2. runs the deny gate's own scan (`scan` in `ci/gates.py`, patterns from `ci/config.json`) on what is left;
3. refuses the whole run on any hit: exit 2, file and pattern name on stderr, never the matched text, nothing written;
4. withholds other files that the gate allows by path and that still name a term. Runtime data in the allow list
   must pass the deny scan without path exemptions. A private name planted there refuses the whole publish;
5. copies the rest to `--target` and writes `MIRROR.md` there with the source commit, date and update command;
6. with `--publish --remote URL`: fetches remote `main` and makes one snapshot commit with that head as its only
   parent. An empty remote starts with a root commit. The push uses no force flag, so a concurrent publish that
   advances the remote causes a rejection. No source commits enter the mirror history.

    python -I tools/mirror_public.py --dry-run                  # list what would be published and refused
    python -I tools/mirror_public.py --dry-run --remote <URL>   # also show the remote parent
    python -I tools/mirror_public.py --target <DIR>             # build the tree only
    python -I tools/mirror_public.py --target <DIR> --publish --remote <URL>

`--target` refuses to wipe a folder that is not empty and holds no `MIRROR.md`.
The dry run prints `parent: <sha>` when the supplied remote has `main`, or `parent: none` when no remote was
supplied or its `main` does not exist. A remote read failure stops the run.

## In the sync

`sync.sh --push` calls `public_mirror` (`lib.sh`) after the layers are pushed. It does nothing unless
`PUBLIC_MIRROR=1`.

| Variable | Meaning |
|---|---|
| `PUBLIC_MIRROR` | `1` turns the step on; anything else, or unset, skips it |
| `PUBLIC_MIRROR_DIR` | folder that receives the mirror tree (required when the step is on) |
| `PUBLIC_MIRROR_REMOTE` | git URL of the public repo; when set the step also publishes |

A refusal or a failure prints a warning and does not abort the sync.

## What a new person installs from it

The superego part of the install (`gh repo clone <OWNER>/superego`) can come from the public repo instead, so no
invite to the private superego is needed. The collective is still shared by invite. Until the public repo exists, the
invite flow in `docs/instalar.pt-BR.md` is the current one.

An existing clone updates with `git pull --ff-only`. The mirror's linear history also supports the installer's
normal layer update, which uses that command.

The published `ci/privacy-terms.json` holds generic privacy patterns for e-mail, CPF/CNPJ, phone numbers, IP
addresses, long identifiers and secret assignments. Person, company, client, product, account, path and domain
rules belong in `~/.claude/privacy-terms.local.json`, outside the repo. `CLAUDE_CONFIG_DIR` overrides the context
home. The local file is optional and uses the same JSON schema. `tools/privacy.py` combines `patterns`,
`forbidden_layer_repos` and `personal_levels` from both files, preserving order and removing duplicate entries.
Distinct regexes with the same pattern name are both retained. The CI deny configuration stays independent in
`ci/config.json`.

## What stays private

- the history of the source repo;
- CI implementation, configuration and baselines under `ci/`, except the generic runtime privacy file;
- other files that name denied terms, such as `docs/ci-gates.md`, `kits/collective/ci/config.json` and
  `tests/test_generic.py`. The dry run prints the current withheld list. The mirror cannot run the full CI by itself;
- the optional per-person privacy file and `.staging/`, even if staging files were accidentally tracked;
- everything the layers keep outside this repo: the ego, the id, the psique and the collective.

## Create the public repo and publish (run by hand)

Run these yourself after reading the dry run. Nothing in the repo runs them.

1. Check the source: on `main`, clean, up to date.

       git -C ~/Codes/superego status --short --branch
       python -I ~/Codes/superego/tools/mirror_public.py --dry-run

2. Create the empty public repo (no README, no license file; the tree brings its own):

       gh repo create <OWNER>/superego-public --public --description "Generic agent-context layer (mirror, no source history)"
       gh repo edit <OWNER>/superego-public --enable-issues=false --enable-wiki=false

3. First publish:

       python -I ~/Codes/superego/tools/mirror_public.py --target ~/Codes/superego-public-tree --publish --remote https://github.com/<OWNER>/superego-public.git

4. Check: `gh repo view <OWNER>/superego-public --web`, and `git ls-remote https://github.com/<OWNER>/superego-public.git`
   shows one commit on `main`.

5. Later publishes happen on every `sync.sh --push` once the environment has:

       PUBLIC_MIRROR=1
       PUBLIC_MIRROR_DIR=~/Codes/superego-public-tree
       PUBLIC_MIRROR_REMOTE=https://github.com/<OWNER>/superego-public.git

Pull requests cannot be switched off for a public GitHub repo. The `MIRROR.md` notice says the mirror accepts none;
close any that arrive.
