---
level: superego
name: vault
description: Save and recover the user's secret files (.env, .pem, SSH keys, cloud configs) in their Bitwarden vault with scripts/vault-sync.sh, so a new or formatted machine loses nothing. Use on "save my envs", "back up my secrets", "vault", "bitwarden", "restore my secrets".
level: superego
---

# vault: secrets in Bitwarden

Works the same in Claude Code and Codex. Script: `~/.claude/scripts/vault-sync.sh`. List of files: `~/.claude/scripts/secrets-manifest.txt` (paths only, no values).

## Rules
- Never print, quote or summarize a secret value. Report only names, paths and statuses.
- Never ask the user to paste a secret. If a value is missing, ask them to put it in the vault or the file themselves.
- The master password is the user's. You cannot unlock the vault. If `BW_SESSION` is empty, tell them to run in their terminal: `export BW_SESSION="$(bw unlock --raw)"` (or save that key to `~/.bw-session`, chmod 600, their call), then retry.
- Client conversation data (sample `*.jsonl` exports, transcripts) never goes in the vault or in GitHub.

## How it stores
Logic in `~/.claude/scripts/vault_sync.py` (`vault-sync.sh` is a wrapper). Free Bitwarden has no attachments and a 10000 encrypted-char limit per note, so: small clean text is a plain note; CRLF, binary or big files are base64(gzip) split in notes `claude-context/<path>#k`. Each head item carries a `sha256` of the exact bytes; status/push compare that, and pull verifies it before writing. A failing file never stops the others; exit code 1 if any failed. Offline test with a fake `bw`: `python -I ~/.claude/scripts/test_vault_sync.py`.

## Save (auto-save)
1. Run `~/.claude/scripts/vault-sync.sh status`. If anything is `changed` or `only-disk`, say which paths.
2. Run `vault-sync.sh push` (writes only changed files). Report `created`/`updated`/`unchanged` per path.
3. New secret file in a repo (a `.env` not in the manifest): list it and ask the user before adding a line to `secrets-manifest.txt`.

## Recover (auto-recover)
- Fresh machine: after `bw login` and unlock, run `vault-sync.sh pull`. It skips files that already exist; `--force` overwrites, so ask first and say which paths.
- After a pull, run `status`; every path should read `ok`.
- `LITELLM_API_KEY` is an env var, not a file: remind the user to set it from the item `claude-context/env/LITELLM_API_KEY` (`setx`), without echoing it.

## When to offer it
- Start of a session in a repo whose `.env` is not `ok` in `status`: one line, once.
- Before a format, reinstall or machine change: run `status`, then `push`.
