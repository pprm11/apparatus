#!/usr/bin/env bash
# Bitwarden sync for secrets-manifest.txt. Thin wrapper: the logic and the storage format are in vault_sync.py.
#   vault-sync.sh status | push | pull [--force]
# Session: export BW_SESSION="$(bw unlock --raw)"  (or a live key in ~/.bw-session, chmod 600; your call)
exec python -I "$(cd "$(dirname "$0")" && pwd)/vault_sync.py" "$@"
