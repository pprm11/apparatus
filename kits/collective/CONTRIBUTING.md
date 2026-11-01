# Contributing

Nothing reaches `main` without a pull request approved by the owner of each area it touches
(`CODEOWNERS`, with "Require review from Code Owners" turned on).

## Flow

1. Draft in your own context first (your `ego`). Write only what belongs to the {{team}} team. Do not copy conversations or memories as they are.
2. Remove everything personal or confidential: names of people, clients and customers, private URLs, ids,
   tokens, text taken from chats, and anything that comes from another company you work with. This repo is
   shared across a company boundary: CI blocks the terms of the other companies from a private list, and a
   human still reads the diff. Redaction tools help (`gitleaks`, a PII scan) but do not catch everything;
   a human reads the diff.
3. Put the draft in `proposed/<area>/<name>.md` and open a PR. Drafts are never loaded by any harness.
4. The area owner and one second reviewer approve. CI runs `python -I ci/gates.py --strict` (registry, injection, redaction, personal data, budget, glossary
   format and more) and a secret scan of the whole history.
5. On merge, the item moves out of `proposed/` into `global/`, `rules/` or `skills/`, with its entry in
   `registry.json`.

## Every item carries provenance

`registry.json` entry: `owner`, `source` (PR, session or thread), `created`, `review_by` (ISO date),
`status` (`draft`, `stable`, `deprecated`), `locked`, and `superseded_by` when deprecated. An item past its
`review_by` is revalidated by its owner or deprecated. Deprecated items stay for at least one release before
removal; nothing is deleted silently.

## Rules for content

- Engineering text in English; Portuguese terms stay only where the team uses them.
- Skills are named `collective-<name>`, with `level: collective` in the frontmatter. Same name in two layers
  is a collision (Codex does not merge them).
- Anything with a command, a script or a download needs the owner of `skills/` or `rules/` to read it line
  by line. Shared text is untrusted until reviewed: the lint rejects invisible Unicode, large base64 blobs,
  download-and-run lines and instructions to hide things from the user.
- Keep always-loaded files short (a few KiB). Put detail in skills.

## Versions

Tags `vMAJOR.MINOR.PATCH`. Consumers pin a tag in the `ref` field of the psique manifest. Channels: tags
without a suffix are stable, `-next.N` is the preview channel.
