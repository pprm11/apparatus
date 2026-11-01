# templates/

Starting points for the other layers. Copy one to a new repo and follow the README inside it.

- `psique/`: the meta repo with `manifest.json` that lists the layers (called `self` after the rename).
- `persona/`: opt-in public practices of one person.
- `collective/`: what a team shares, read-only for its members.
- `ego/`: one company or project, private to a person.
- `id/`: the person, private and partly encrypted.

`tools/onboard.py init` creates the repos from these folders. The file list is part of the contract
(`docs/contract.md`, section 3): add files freely, but do not move or delete one.
