#!/usr/bin/env python3
"""Testes offline do hook-bash-guard.py: corpus BLOCK (o incidente de 28/10 e variantes) e PASS (buscas certas).

Rodar: python -I ~/.claude/scripts/test_hook_bash_guard.py
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
    'find / -maxdepth 6 -path "*skill-creator*" -name "quick_validate.py" 2>/dev/null | head -3',  # o incidente
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
    "ls ~/.claude/skills | head; find / -maxdepth 6 -name quick_validate.py",  # escondido no meio
    "cd ~/Codes && find // -name x",
]
PASS = [
    "find ~/.claude -name quick_validate.py",
    "find /c/dev/Codes -maxdepth 3 -name '*.py'",
    "find ~/.claude/plugins \"$APPDATA/Claude\" -maxdepth 8 -name quick_validate.py 2>/dev/null | head -3",  # a correção da sessão
    "grep -rn foo src/",
    "rg pattern .",
    "rg pattern",
    "ls -la /",            # listar a raiz não anda a árvore
    "ls /proc",
    "cat /proc/meminfo",
    "find . -name '*.py'",
    "find /tmp -mtime +7 -delete",
    "du -sh /c/dev/Codes",
    "grep foo /etc/hosts",  # grep sem -r
    "tree ~/Codes/app/src",
    "timeout 10 find /proc/registry/HKEY_LOCAL_MACHINE/SOFTWARE/Microsoft -maxdepth 2 | wc -l",  # abaixo de /proc: ainda registro -> ver teste abaixo
    "git -C /c/dev/Codes/app status",
    "python -I ~/.claude/scripts/medir-prompts.py --desde 2026-10-20",
    "echo find / in a string is not a command",
]
# A busca em ramo do registro abaixo de /proc é registro do mesmo jeito; o hook nega o ramo inteiro.
PASS = [c for c in PASS if "/proc/registry" not in c]
BLOCK.append("timeout 10 find /proc/registry/HKEY_LOCAL_MACHINE/SOFTWARE/Microsoft -maxdepth 2 | wc -l")


def entrada(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}, "session_id": "teste"}


class TestGuard(unittest.TestCase):
    def setUp(self):
        guard.log = lambda *a, **k: None  # sem gravar eventos nos testes

    def test_block(self):
        for cmd in BLOCK:
            with self.subTest(cmd=cmd):
                saida = guard.decidir(entrada(cmd))
                self.assertIsNotNone(saida, f"deveria barrar: {cmd}")
                self.assertEqual(saida["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_pass(self):
        for cmd in PASS:
            with self.subTest(cmd=cmd):
                self.assertIsNone(guard.decidir(entrada(cmd)), f"deveria passar: {cmd}")

    def test_outra_ferramenta_passa(self):
        self.assertIsNone(guard.decidir({"tool_name": "Read", "tool_input": {"file_path": "/"}}))

    def test_falha_aberta(self):
        self.assertIsNone(guard.decidir({"tool_name": "Bash", "tool_input": None}))

    def test_motivo_cita_caminho_estreito(self):
        saida = guard.decidir(entrada("find / -name x"))
        self.assertIn("~/.claude", saida["hookSpecificOutput"]["permissionDecisionReason"])


if __name__ == "__main__":
    sys.exit(unittest.main(verbosity=1))
