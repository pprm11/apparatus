# superego/scripts/

The scripts live in `superego/scripts/`. They are copied to `~/.claude/scripts` on restore (they are listed under `files` in `superego/layer.json`).

- `hook-prompt-guard.py` and `hook-bash-guard.py`: harness hooks that stop a secret in a prompt and a
  disk-wide search command.
- `hook-context-budget.py`: PreToolUse hook (Edit|Write) that refuses the edit taking an always-loaded file over
  the 90% band of its layer's byte budget (`tools/context_budget.py`, `check_write`).
- `vault-sync.sh` and `vault_sync.py`: save and restore secret files in a password manager vault.
- `test_*.py`: offline tests for the scripts above.

Run a test with `python -I superego/scripts/test_vault_sync.py`.
