# Release process

A release is a tag `vMAJOR.MINOR.PATCH` on `main` with a CHANGELOG section. Rules for the bump are in
[GOVERNANCE.md](../GOVERNANCE.md).

## Every pull request

1. Add a line to `## [Unreleased]` in `CHANGELOG.md` under `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed` or
   `Security` ([Keep a Changelog](https://keepachangelog.com/en/1.1.0/)).
2. Label a breaking change in the title (`feat!:` or `BREAKING CHANGE:` in the body) and list it under `Removed`
   or a `Breaking` heading. A breaking label means the next release is a major.
3. Run the full local suite: `python -I ci/gates.py`. `tests/test_contract.py` fails when something in
   `ci/contract.json` is gone. Paste the result in the pull request body.

Commit titles follow Conventional Commits, in English: `feat:`, `fix:`, `docs:`, `test:`, `chore:`; `!` after the
type marks a breaking change.

## Cutting a release

1. Pick the version: any breaking label since the last tag means major; otherwise any `feat` means minor;
   otherwise patch.
2. Check the snapshot is complete: `python -I ci/contract_snapshot.py --fresh` (it lists contract items that
   `ci/contract.json` and `docs/contract.md` do not yet cover; add them with `--write` and describe them).
3. Rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD`, open a new empty `## [Unreleased]`, update the
   comparison links at the bottom, and commit as `chore(release): vX.Y.Z`.
4. Run the full suite on that commit. It must be green.
5. Tag and push: `git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin vX.Y.Z`.

A major release also needs the removals to have been announced under `Deprecated` at least one minor release
earlier (the deprecation window).

## Consumers following main

Some installs track `main` instead of a tag. Because of that, `main` carries only non-breaking changes between
majors, and a major lands on `main` in the same pull request that tags it, after the window has run out. Anyone
who cannot absorb a change on the day pins a tag with `--superego-ref`.
