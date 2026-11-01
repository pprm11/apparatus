# Governance

superego is the generic layer of a layered agent context. People and teams build on it, so it has to stay
stable: few changes, and no change that breaks someone else's setup. This file is the policy. The surface it
protects is defined in [docs/contract.md](docs/contract.md) and pinned by `tests/test_contract.py`.

## What belongs here

Only what is valid for anyone, with no edit:

- tooling (`tools/`), installer and sync scripts, generic skills (`skills/`), agent rules (`global/`, `rules/`),
  harness adapters (`harness/`), templates (`templates/`);
- rules whose text would read the same for a stranger on another team and another company.

What does not belong here: a person's preferences, names, accounts or e-mail; a company, client, product or
colleague name; machine paths. Those go to the layer that owns them:

| Content | Layer |
|---|---|
| Valid for anyone | superego (this repo) |
| Shared by one team, not by everyone | collective |
| One company's glossary, rules and projects | ego |
| One person's habits, plan and private notes | id |

Three gates enforce it: the CI deny list (`ci/config.json`), `tests/test_generic.py` and the identifier test in
`tests/test_contract.py`, which reads `ci/privacy-terms.json`. A new hit fails the build. Known debt is
listed in `ci/deny-baseline.txt` and in `DEBT` of the identifier test, and only shrinks.

## Versioning

Semantic Versioning 2.0.0 over the public contract. The tag is `vMAJOR.MINOR.PATCH`.

| Change | Bump |
|---|---|
| Removing or renaming anything in the contract, or changing its meaning | major |
| Adding a command, flag, key, template file, skill or rule without changing existing behavior | minor |
| Fix, doc, test, or a change inside the contract that no consumer can observe | patch |

Before `1.0.0` the contract is not yet promised. From `1.0.0` on, every rule below is binding.

## Deprecation window

1. The old behavior keeps working and prints a warning that names the replacement and the release that removes it.
2. It stays for at least one full minor release after the one that announced it.
3. It is removed only in a major release. The CHANGELOG lists it under `Deprecated` when announced and
   `Removed` when gone.

A fix for a security problem or a data leak may skip the window, but it still ships as a major release with
the reason in the CHANGELOG.

## Change bar

Low churn is the default. A pull request that touches the contract or adds a rule needs:

- **Evidence that it applies to everyone**: a problem seen in more than one team or company, or a defect that a
  stranger would hit. "It works for me" is not enough; it goes to the layer above.
- **No breaking change**, or a major-release plan with the deprecation window already running.
- **A CHANGELOG entry** under `[Unreleased]` and, for the contract, a matching update of `ci/contract.json`
  (`python -I ci/contract_snapshot.py --write`) and `docs/contract.md`.
- **A green local suite** (`python -I ci/gates.py`, which includes `tests/test_contract.py`). The result goes in
  the pull request body.
- Always-loaded text (`global/`, `rules/`, `harness/`) stays inside the budgets of `tools/context_budget.py`.

Maintainers decline, or redirect to a higher layer, a change that fails the first point.

## Branches and consumers

`main` must never hold a breaking change outside a release PR. Some consumers install from `main`, so a merge to
`main` is a release in practice: it passes the same contract tests as a tagged release. Consumers who need a
fixed point pin a tag (`--superego-ref vX.Y.Z`).

See [docs/release.md](docs/release.md) for the release steps.
