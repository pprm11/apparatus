#!/usr/bin/env python3
"""Incremental one-way directory mirror (replaces the hourly rm -rf + cp -r in sync.sh).

Usage: python -I tools/mirror.py SRC DST [--xd NAME ...] [--xp RELPATH ...] [--no-delete] [--allow-remove-dir]

Copies files that are new or changed (size differs, or mtime differs and the bytes differ) and deletes files
and folders in DST that are gone from SRC (unless --no-delete). Every copy goes to a temp file next to the
target and is moved into place with os.replace, so a failed copy never leaves a truncated file.
  --xd NAME           skip any folder with this name, at any depth (caches)
  --xp RELPATH        skip this path, relative to SRC (e.g. synced)
  --allow-remove-dir  a missing SRC empties DST; without it a missing SRC is an error and DST is untouched
A PermissionError is retried 3 times. Any file that could not be handled is reported on stderr and the exit
code is 1 (the mirror is incomplete). With --no-delete a file/folder type conflict is reported and skipped.
"""
import argparse
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ospaths import long_path as lp  # noqa: E402

DEFAULT_XD = ("__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache")


def retry(action, what: str, warnings: list, deleting: bool = False) -> bool:
    for attempt in range(3):
        try:
            action()
            return True
        except PermissionError as exc:
            if attempt == 2:
                warnings.append(f"mirror: skipped {what}: {exc}")
                return False
            time.sleep(0.5)
        except FileNotFoundError as exc:
            if deleting:
                return True  # already gone: nothing left to delete
            warnings.append(f"mirror: skipped {what}: {exc}")
            return False
        except OSError as exc:
            warnings.append(f"mirror: skipped {what}: {exc}")
            return False
    return False


def same_bytes(src: str, dst: str) -> bool:
    with open(lp(src), "rb") as a, open(lp(dst), "rb") as b:
        while True:
            x, y = a.read(1 << 20), b.read(1 << 20)
            if x != y:
                return False
            if not x:
                return True


def same(src: str, dst: str) -> bool:
    """Equal size and equal mtime, or equal size and identical bytes (then the mtime is aligned)."""
    try:
        a, b = os.stat(lp(src)), os.stat(lp(dst))
        if a.st_size != b.st_size:
            return False
        if a.st_mtime_ns == b.st_mtime_ns:
            return True
        if not same_bytes(src, dst):
            return False
        os.utime(lp(dst), ns=(b.st_atime_ns, a.st_mtime_ns))
        return True
    except OSError:
        return False


def atomic_copy(src: str, dst: str) -> None:
    tmp = os.path.join(os.path.dirname(dst), f".{os.path.basename(dst)}.mirror-tmp")
    try:
        shutil.copy2(lp(src), lp(tmp))
        os.replace(lp(tmp), lp(dst))
    except BaseException:
        try:
            os.remove(lp(tmp))
        except OSError:
            pass
        raise


def remove(path: str) -> None:
    if os.path.isdir(lp(path)) and not os.path.islink(lp(path)):
        shutil.rmtree(lp(path))
    else:
        os.remove(lp(path))


def mirror(src: str, dst: str, xd: set, xp: set, delete: bool, warnings: list, rel: str = "", notes: list = None) -> int:
    """Returns how many files were copied or removed."""
    changed = 0
    notes = [] if notes is None else notes
    os.makedirs(lp(dst), exist_ok=True)
    wanted = set()
    with os.scandir(lp(src)) as it:
        entries = sorted(it, key=lambda e: e.name)
    for e in entries:
        sub = f"{rel}/{e.name}" if rel else e.name
        if sub in xp:
            continue
        target = os.path.join(dst, e.name)
        if e.is_dir():
            if e.name in xd:
                continue
            wanted.add(e.name)
            if os.path.exists(lp(target)) and not os.path.isdir(lp(target)):
                if not delete:
                    notes.append(f"mirror: conflict, {target} is a file but the source is a folder; skipped")
                    continue
                retry(lambda t=target: remove(t), target, warnings, True)
            changed += mirror(os.path.join(src, e.name), target, xd, xp, delete, warnings, sub, notes)
        else:
            wanted.add(e.name)
            if os.path.isdir(lp(target)):
                if not delete:
                    notes.append(f"mirror: conflict, {target} is a folder but the source is a file; skipped")
                    continue
                retry(lambda t=target: remove(t), target, warnings, True)
            path = os.path.join(src, e.name)  # not e.path: scandir echoes the extended-length prefix
            if not same(path, target):
                if retry(lambda s=path, t=target: atomic_copy(s, t), path, warnings):
                    changed += 1
    if delete:
        for name in os.listdir(lp(dst)):
            sub = f"{rel}/{name}" if rel else name
            if name in wanted or sub in xp or name in xd:
                continue
            path = os.path.join(dst, name)
            if retry(lambda p=path: remove(p), path, warnings, True):
                changed += 1
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--xd", nargs="*", default=[])
    ap.add_argument("--xp", nargs="*", default=[])
    ap.add_argument("--no-delete", action="store_true")
    ap.add_argument("--allow-remove-dir", action="store_true")
    args = ap.parse_args()
    warnings: list = []
    notes: list = []
    xd = set(DEFAULT_XD) | set(args.xd)
    xp = {p.strip("/") for p in args.xp}
    if not os.path.isdir(args.src):
        if not os.path.isdir(args.dst) or args.no_delete:
            return 0
        if not args.allow_remove_dir:
            print(f"mirror: source {args.src} is missing; refusing to remove {args.dst} (use --allow-remove-dir)",
                  file=sys.stderr)
            return 2
        retry(lambda: shutil.rmtree(args.dst), args.dst, warnings, True)
    else:
        mirror(args.src, args.dst, xd, xp, not args.no_delete, warnings, notes=notes)
    for w in notes + warnings:
        print(w, file=sys.stderr)
    return 1 if warnings else 0


if __name__ == "__main__":
    sys.exit(main())
