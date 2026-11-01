#!/usr/bin/env python3
"""Offline tests for hook-bash-guard.py: BLOCK corpus (the 10/28 incident and variants) and PASS corpus (correct searches).

Run: python -I ~/.claude/scripts/test_hook_bash_guard.py
"""
import importlib.util
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("guard", os.path.join(AQUI, "hook-bash-guard.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

BLOCK = [
    'find / -maxdepth 6 -path "*skill-creator*" -name "quick_validate.py" 2>/dev/null | head -3',  # the incident
    "find /proc/registry -name quick_validate.py",
    "find /proc -maxdepth 3 -name x",
    'grep -r "quick_validate" /',
    "grep -rn foo / --include=*.py",
    "rg quick_validate /",
    "find /c -name quick_validate.py",
    "find /c/ -maxdepth 8 -name x",
    "ls -R / | head",
    "timeout 10 find / -name x",
    "du -sh /",
    'find "C:\\" -name x',
    "find C:/ -name x",
    "find /mnt/c -name x",
    "fd quick_validate /",
    "tree /c",
    "ls ~/.claude/skills | head; find / -maxdepth 6 -name quick_validate.py",  # hidden in the middle
    "cd ~/Codes && find // -name x",
]
PASS = [
    "find ~/.claude -name quick_validate.py",
    "find /srv/work/code -maxdepth 3 -name '*.py'",
    "find ~/.claude/plugins \"$APPDATA/Claude\" -maxdepth 8 -name quick_validate.py 2>/dev/null | head -3",  # the fix from that session
    "grep -rn foo src/",
    "rg pattern .",
    "rg pattern",
    "ls -la /",            # listing the root does not walk the tree
    "ls /proc",
    "cat /proc/meminfo",
    "find . -name '*.py'",
    "find /tmp -mtime +7 -delete",
    "du -sh /srv/work/code",
    "grep foo /etc/hosts",  # grep without -r
    "tree ~/Codes/app/src",
    "timeout 10 find /proc/registry/HKEY_LOCAL_MACHINE/SOFTWARE/Microsoft -maxdepth 2 | wc -l",  # below /proc: still registry -> see the filter below
    "git -C /srv/work/code/app status",
    "python -I ~/.claude/scripts/medir-prompts.py --desde 2026-10-20",
    "echo find / in a string is not a command",
]
# A search in a registry branch below /proc is still the registry; the hook denies the whole branch.
PASS = [c for c in PASS if "/proc/registry" not in c]
BLOCK.append("timeout 10 find /proc/registry/HKEY_LOCAL_MACHINE/SOFTWARE/Microsoft -maxdepth 2 | wc -l")


def entrada(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}, "session_id": "teste"}


class TestGuard(unittest.TestCase):
    def setUp(self):
        guard.log = lambda *a, **k: None  # do not write events during tests

    def test_block(self):
        for cmd in BLOCK:
            with self.subTest(cmd=cmd):
                saida = guard.decidir(entrada(cmd))
                self.assertIsNotNone(saida, f"should block: {cmd}")
                self.assertEqual(saida["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_pass(self):
        for cmd in PASS:
            with self.subTest(cmd=cmd):
                self.assertIsNone(guard.decidir(entrada(cmd)), f"should pass: {cmd}")

    def test_other_tool_passes(self):
        self.assertIsNone(guard.decidir({"tool_name": "Read", "tool_input": {"file_path": "/"}}))

    def test_fails_open(self):
        self.assertIsNone(guard.decidir({"tool_name": "Bash", "tool_input": None}))

    def test_reason_cites_narrow_path(self):
        saida = guard.decidir(entrada("find / -name x"))
        self.assertIn("~/.claude", saida["hookSpecificOutput"]["permissionDecisionReason"])


if __name__ == "__main__":
    sys.exit(unittest.main(verbosity=1))
