"""Helpers shared by the tools (kept tiny on purpose)."""
import glob
import os
import shutil


def codex_exe() -> str | None:
    """Path of the Codex CLI (PATH first, then the desktop app's bin folder), or None."""
    found = shutil.which("codex")
    if found:
        return found
    hits = sorted(glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "OpenAI", "Codex", "bin", "*", "codex.exe")),
                  key=os.path.getmtime)
    return hits[-1] if hits else None


def require_codex() -> str:
    exe = codex_exe()
    if not exe:
        raise SystemExit("codex CLI not found (PATH or %LOCALAPPDATA%/OpenAI/Codex/bin)")
    return exe
