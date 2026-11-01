# kits/

Files that a new repo receives when it is created from a kit.

- `collective/`: the CI gates, hooks, CODEOWNERS and contribution guide for a team (collective) repo.
  `tools/onboard.py init --new-collective NAME` copies it into the new repo.

A kit is not loaded into the agent context. Its own gates and tests live inside it.
