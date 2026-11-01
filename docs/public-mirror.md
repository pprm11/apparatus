# Public mirror

The superego is the generic layer: rules and tools that are the same for any person. The `deny` gate
(`docs/ci-gates.md`) keeps every private name, machine path, company and person out of its tree, and the baseline of
known violations is empty. That makes the committed tree safe to publish. The history is not: old commits still hold
what the gate now forbids. So the public copy is a **mirror of the tree without history**.

## How it works

`tools/mirror_public.py` takes the committed tree of `HEAD` (not the working tree) and:

1. lists the tracked files and drops the ones that are never published: `runs/`, `index/`, `.work/`, `.harvest/`,
   generated files (`INDEX.md`, `lint-report.md`, `AGENTS.md`, `CLAUDE.md`) and the deny baseline (`ci/*baseline*`);
2. runs the deny gate's own scan (`scan` in `ci/gates.py`, patterns from `ci/config.json`) on what is left;
3. refuses the whole run on any hit: exit 2, file and pattern name on stderr, never the matched text, nothing written;
4. withholds the files that the gate allows by path (`allow_paths`: the CI files that must name the terms) and that
   still name a term. They stay in the private repo only;
5. copies the rest to `--target` and writes `MIRROR.md` there (source commit, date, "no history, no pull requests");
6. with `--publish --remote URL`: makes one commit in the target and force-pushes it to `main` of the remote. The
   previous tree is replaced; no history accumulates.

    python -I tools/mirror_public.py --dry-run                  # list what would be published and refused
    python -I tools/mirror_public.py --target <DIR>             # build the tree only
    python -I tools/mirror_public.py --target <DIR> --publish --remote <URL>

`--target` refuses to wipe a folder that is not empty and holds no `MIRROR.md`.

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

## What stays private

- the history of the source repo;
- `ci/config.json`, `ci/privacy-terms.json`, `ci/repo_gates.py`, `ci/test_gates.py`, `docs/ci-gates.md`,
  `kits/collective/ci/config.json` and `tests/test_generic.py`: they name the denied terms on purpose, so the mirror
  withholds them (the dry run prints the current list). The mirror therefore cannot run the full CI by itself;
- everything the layers keep outside this repo: the ego, the id, the psique and the collective.

## Create the public repo and publish (run by hand)

Run these yourself after reading the dry run. Nothing in the repo runs them.

1. Check the source: on `main`, clean, up to date.

       git -C ~/Codes/superego status --short --branch
       python -I ~/Codes/superego/tools/mirror_public.py --dry-run

2. Create the empty public repo (no README, no license file; the tree brings its own):

       gh repo create <OWNER>/superego-public --public --description "Generic agent-context layer (mirror, no history)"
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
