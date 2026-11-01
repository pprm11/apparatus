#!/usr/bin/env sh
# Thin wrapper: find a real Python 3.10+ (installing it with brew or apt when missing), then hand over to
# tools/bootstrap.py. Everything else lives in Python. Usage: ./bootstrap.sh --psique OWNER/REPO [--dry-run]
set -eu
here=$(cd "$(dirname "$0")" && pwd)

find_python() {
  for cand in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
      command -v "$cand"
      return 0
    fi
  done
  return 1
}

py=$(find_python || true)
if [ -z "$py" ]; then
  case "$(uname -s)" in
    Darwin)
      command -v brew >/dev/null 2>&1 || { echo "Install Homebrew first (https://brew.sh), then run this again." >&2; exit 1; }
      brew install python@3.12 ;;
    *)
      command -v apt-get >/dev/null 2>&1 || { echo "Install Python 3.10+ with your package manager, then run this again." >&2; exit 1; }
      sudo apt-get update && sudo apt-get install -y python3 ;;
  esac
  py=$(find_python) || { echo "Python 3.10+ is still not on PATH; open a new shell and run this again." >&2; exit 1; }
fi
exec "$py" -I "$here/tools/bootstrap.py" "$@"
