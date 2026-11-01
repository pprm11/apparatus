"""Per-OS locations of the agent harnesses and of this tool's own state.

Pure functions of (platform, environment, home): pathlib only, no shell, so every OS is testable from any OS.
The Claude Code and Codex config folders are the same on the three systems (`~/.claude`, `~/.codex`, with
`CLAUDE_CONFIG_DIR` and `CODEX_HOME` as overrides). What differs is where the desktop app keeps its session
files and where a per-user state folder belongs. The macOS and Linux app folders follow each OS's convention
and are unverified on a real machine; `doctor` reports a missing folder as a warning, not an error.
"""
from __future__ import annotations

import glob
import os
import shutil
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

WINDOWS, MACOS, LINUX = "windows", "macos", "linux"


def system(plat: str | None = None) -> str:
    """`windows`, `macos` or `linux` from a `sys.platform` value (default: this machine)."""
    p = plat or sys.platform
    if p.startswith(("win", "cygwin", "msys")):
        return WINDOWS
    if p in ("darwin", MACOS):
        return MACOS
    return LINUX


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def _home(home: Path | str | None) -> Path:
    return Path(home) if home else Path.home()


def claude_home(env: Mapping[str, str] | None = None, home: Path | str | None = None) -> Path:
    e = _env(env)
    return Path(e["CLAUDE_CONFIG_DIR"]) if e.get("CLAUDE_CONFIG_DIR") else _home(home) / ".claude"


def codex_home(env: Mapping[str, str] | None = None, home: Path | str | None = None) -> Path:
    e = _env(env)
    return Path(e["CODEX_HOME"]) if e.get("CODEX_HOME") else _home(home) / ".codex"


def claude_app_sessions(plat: str | None = None, env: Mapping[str, str] | None = None,
                        home: Path | str | None = None) -> Path:
    """Folder where the Claude desktop app keeps one JSON per Claude Code session."""
    e, h, s = _env(env), _home(home), system(plat)
    if s == WINDOWS:
        base = Path(e["APPDATA"]) if e.get("APPDATA") else h / "AppData" / "Roaming"
    elif s == MACOS:
        base = h / "Library" / "Application Support"
    else:
        base = Path(e["XDG_CONFIG_HOME"]) if e.get("XDG_CONFIG_HOME") else h / ".config"
    return base / "Claude" / "claude-code-sessions"


def state_dir(plat: str | None = None, env: Mapping[str, str] | None = None,
              home: Path | str | None = None) -> Path:
    """Per-user folder for bootstrap state, job logs and locks. `SUPEREGO_HOME` overrides it."""
    e, h, s = _env(env), _home(home), system(plat)
    if e.get("SUPEREGO_HOME"):
        return Path(e["SUPEREGO_HOME"])
    if s == WINDOWS:
        base = Path(e["LOCALAPPDATA"]) if e.get("LOCALAPPDATA") else h / "AppData" / "Local"
    elif s == MACOS:
        base = h / "Library" / "Application Support"
    else:
        base = Path(e["XDG_STATE_HOME"]) if e.get("XDG_STATE_HOME") else h / ".local" / "state"
    return base / "superego"


def age_dir(home: Path | str | None = None) -> Path:
    """Where the age identity lives when it has to touch the disk (same convention on every OS)."""
    return _home(home) / ".config" / "age"


def codex_exe(plat: str | None = None, env: Mapping[str, str] | None = None,
              which: Callable[[str], str | None] = shutil.which,
              globber: Callable[[str], list[str]] = glob.glob) -> str | None:
    """Path of the Codex CLI: PATH first, then the Windows desktop app's bin folder, else None."""
    found = which("codex")
    if found:
        return found
    if system(plat) == WINDOWS:
        local = _env(env).get("LOCALAPPDATA", "")
        if local:
            hits = sorted(globber(os.path.join(local, "OpenAI", "Codex", "bin", "*", "codex.exe")),
                          key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0)
            if hits:
                return hits[-1]
    return None


def gui_interpreter(plat: str | None = None, executable: str | None = None) -> str:
    """Interpreter for jobs that must not open a console window: `pythonw` next to python on Windows."""
    exe = executable or sys.executable
    if system(plat) == WINDOWS:
        p = Path(exe)
        w = p.with_name("pythonw.exe")
        if p.name.lower() == "python.exe" and w.exists():
            return str(w)
    return exe
