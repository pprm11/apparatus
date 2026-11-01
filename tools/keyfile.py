"""Owner-only files for secret material (the age identity, a vault session) on every OS.

POSIX: mode 0600 on creation, folder 0700. Windows: `os.chmod` only toggles the read-only flag, so the ACL is
rewritten with `icacls` (inheritance off, full control for the current user only). No shell is involved.
"""
from __future__ import annotations

import contextlib
import getpass
import os
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

import ospaths

Runner = Callable[..., "subprocess.CompletedProcess[str]"]
# Principals that make an ACL non-private; icacls prints the account names.
BROAD = ("everyone", "builtin\\users", "authenticated users", "nt authority\\authenticated users")


def _user() -> str:
    """The current user as icacls wants it: DOMAIN-backslash-user. A bare name can resolve to another account, which then
    owns a key file the current process can no longer read (seen on a machine with a Microsoft account)."""
    name = os.environ.get("USERNAME") or getpass.getuser()
    domain = os.environ.get("USERDOMAIN")
    return f"{domain}{chr(92)}{name}" if domain else name


def restrict(path: Path | str, plat: str | None = None, runner: Runner = subprocess.run) -> None:
    p = str(path)
    if ospaths.system(plat) == ospaths.WINDOWS:
        runner(["icacls", p, "/inheritance:r", "/grant:r", f"{_user()}:F"],
               check=True, capture_output=True, text=True)
    else:
        os.chmod(p, 0o700 if os.path.isdir(p) else 0o600)


def write_private(path: Path | str, data: bytes | str, plat: str | None = None, runner: Runner = subprocess.run) -> Path:
    """Create `path` with owner-only access from the first byte (no window where it is world-readable)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    raw = data.encode("utf-8") if isinstance(data, str) else data
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(raw)
    restrict(p, plat, runner)
    return p


def is_private(path: Path | str, plat: str | None = None, runner: Runner = subprocess.run) -> tuple[bool, str]:
    p = str(path)
    if not os.path.exists(p):
        return False, "missing"
    if ospaths.system(plat) == ospaths.WINDOWS:
        res = runner(["icacls", p], capture_output=True, text=True)
        if res.returncode != 0:
            return False, f"icacls failed: {res.stderr.strip()[:120]}"
        shown = res.stdout.lower()
        bad = [b for b in BROAD if b in shown]
        return (not bad), ("owner only" if not bad else "readable by " + ", ".join(bad))
    mode = os.stat(p).st_mode & 0o777
    return (mode & 0o077) == 0, oct(mode)


def wipe(path: Path | str) -> None:
    """Best-effort overwrite and delete (an SSD or a journaling filesystem may still keep old blocks)."""
    p = Path(path)
    with contextlib.suppress(OSError):
        size = p.stat().st_size
        with open(p, "r+b") as fh:
            fh.write(b"\0" * size)
            fh.flush()
            os.fsync(fh.fileno())
    with contextlib.suppress(FileNotFoundError):
        p.unlink()


@contextlib.contextmanager
def temp_secret(data: bytes | str, directory: Path | str | None = None, name: str = "secret",
                plat: str | None = None, runner: Runner = subprocess.run) -> Iterator[Path]:
    """A private file that exists only inside the `with` block."""
    base = Path(directory) if directory else ospaths.state_dir(plat) / "tmp"
    path = base / f"{name}-{os.getpid()}"
    write_private(path, data, plat, runner)
    try:
        yield path
    finally:
        wipe(path)
