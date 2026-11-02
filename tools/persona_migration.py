#!/usr/bin/env python3
"""Review and apply a hash-guarded skill transition with a separate backup."""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compose import tree_hash


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--skills', required=True, type=Path)
    parser.add_argument('--backup', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    entries = plan.get('skills')
    if not isinstance(entries, dict) or not entries:
        raise SystemExit('plan must list skills and expected tree hashes')
    root = args.skills.resolve()
    backup = args.backup.resolve()
    if backup == root or root in backup.parents or backup in root.parents or backup.exists():
        raise SystemExit('backup must be a new directory outside the skills tree')
    for name, expected in entries.items():
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name) or not isinstance(expected, str):
            raise SystemExit('invalid plan entry')
        folder = root / name
        if folder.is_symlink() or not folder.is_dir() or tree_hash(str(folder)) != expected:
            raise SystemExit(f'hash mismatch or missing skill: {name}')
    marker = root / '.persona-skills.json'
    receipt = None
    if marker.exists():
        raw = marker.read_bytes()
        if hashlib.sha256(raw).hexdigest() != plan.get('marker_sha256'):
            raise SystemExit('marker hash mismatch or missing from plan')
        receipt = json.loads(raw)
    if not args.apply:
        for name in sorted(entries):
            print(f'would back up and remove {name}')
        return 0
    backup.mkdir(parents=True)
    for name in sorted(entries):
        shutil.copytree(root / name, backup / name, symlinks=False)
        if tree_hash(str(backup / name)) != entries[name]:
            raise SystemExit(f'backup verification failed: {name}')
    if receipt is not None:
        shutil.copy2(marker, backup / marker.name)
    # Recheck all sources after backup before touching any of them.
    if receipt is not None and hashlib.sha256(marker.read_bytes()).hexdigest() != plan['marker_sha256']:
        raise SystemExit('marker changed during backup')
    for name, expected in entries.items():
        if tree_hash(str(root / name)) != expected:
            raise SystemExit(f'source changed during backup: {name}')
    for name in sorted(entries):
        shutil.rmtree(root / name)
    if receipt is not None:
        receipt['skills'] = [name for name in receipt.get('skills', []) if name not in entries]
        for key in ('hashes', 'aliases'):
            receipt[key] = {name: value for name, value in receipt.get(key, {}).items() if name not in entries}
        marker.write_text(json.dumps(receipt, indent=1) + '\n', encoding='utf-8')
    print(f'backup: {backup}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
