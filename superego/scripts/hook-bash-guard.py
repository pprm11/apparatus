#!/usr/bin/env python3
r"""User's PreToolUse hook (Bash matcher): blocks recursive search from the root on Windows.

Origin: on 2026-10-28 a session ran `find / -maxdepth 6 -path "*skill-creator*" -name quick_validate.py`.
In Git Bash `/` is the MSYS root, which exposes the Windows registry at /proc/registry, /proc/registry32 and
/proc/registry64 (with HKEY_PERFORMANCE_DATA). The find stayed 3 h on one core in kernel mode, with 1.29 M
open handles (82% of the system) and 1.24 GB of nonpaged pool. Bash's 120 s timeout sent the command to the
background without killing it; the session ended and the process was left orphaned.

Narrow lexical rule (not a natural-language guardrail): a search command (find, fd, grep -r,
rg, ls -R, du, tree) whose starting point is the root (`/`, `/proc...`, `/c`, `C:\`, `/mnt/c`, `/cygdrive/c`)
is denied with the instruction to start from ~/.claude, ~/Codes or the repo. Any other path passes.

Fails open: an error in the hook lets the command through. Events in ~/.claude/scripts/medicoes/eventos.jsonl.
Offline tests: python -I ~/.claude/scripts/test_hook_bash_guard.py
"""
import json
import os
import re
import shlex
import sys
import time

EVENTOS = os.path.join(os.path.expanduser("~/.claude/scripts"), "medicoes", "eventos.jsonl")

# Tools that walk the whole tree by default, and tools that only do so with the flag next to them.
SEMPRE_RECURSIVO = {"find", "fd", "rg", "du", "tree"}
RECURSIVO_COM_FLAG = {"grep": re.compile(r"^-[a-zA-Z]*[rR]|^--(recursive|dereference-recursive)$"),
                      "ls": re.compile(r"^-[a-zA-Z]*R|^--recursive$")}
SEPARADORES = {"|", "||", "&&", ";", "&", "(", ")", "{", "}"}
PREFIXOS = {"timeout", "nice", "ionice", "time", "sudo", "env", "command", "exec", "nohup", "stdbuf"}
RAIZ = re.compile(r"""^(?:
    /+ |                       # / and //
    /proc(?:/.*)? |            # /proc and everything below it (registry, registry32, registry64)
    /c/? | /cygdrive/c/? | /mnt/c/? |   # the whole C: drive
    [A-Za-z]:[\\/]?            # C:\ C:/ C:
)$""", re.X)
# Narrow paths under /proc that do not walk the registry (/proc/<n>, /proc/meminfo, etc.) would pass only
# if they were not a recursive search; find /proc/meminfo would be useless, so the rule above denies the whole branch.


def log(sid, tipo, **extra):
    try:
        os.makedirs(os.path.dirname(EVENTOS), exist_ok=True)
        with open(EVENTOS, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "sid": sid, "tipo": tipo, **extra},
                               ensure_ascii=False) + "\n")
    except OSError:
        pass


def tokens_de(comando):
    """Command tokens. Non-POSIX mode so `C:\\` does not become an escape; punctuation_chars splits `;`, `|`,
    `&&` and `>` even when glued to a word. Quotes around a token are stripped."""
    try:
        lex = shlex.shlex(comando, posix=False, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        tokens = comando.replace("|", " | ").replace(";", " ; ").split()
    limpos = []
    for t in tokens:
        if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
            t = t[1:-1]
        limpos.append(t)
    return limpos


def segmentos(comando):
    """Split the command into pipeline segments; each segment is a list of tokens."""
    seg, atual = [], []
    for t in tokens_de(comando):
        if t in SEPARADORES or set(t) <= set("|&;<>()"):
            if atual:
                seg.append(atual)
            atual = []
        else:
            atual.append(t)
    if atual:
        seg.append(atual)
    return seg


def ferramenta_e_args(tokens):
    """Skip prefixes (timeout 10, env X=1, sudo) and return (tool, args) or (None, [])."""
    i = 0
    while i < len(tokens):
        t = tokens[i]
        base = os.path.basename(t.replace("\\", "/"))
        if base.endswith(".exe"):
            base = base[:-4]
        if base in PREFIXOS or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
            i += 1
            # timeout and nice take a value (10, 5m, -n 19) right after the name
            if base in {"timeout", "nice"} and i < len(tokens) and re.match(r"^-?[0-9]+[smhd]?$|^-n$", tokens[i]):
                i += 1
            continue
        return base, tokens[i + 1:]
    return None, []


def caminho_raiz(args):
    for a in args:
        if a.startswith("-") and a not in {"-"}:
            continue
        if RAIZ.match(a):
            return a
    return None


def busca_na_raiz(comando):
    """Return (tool, path) of the first segment that walks the root, or None."""
    for tokens in segmentos(comando):
        ferramenta, args = ferramenta_e_args(tokens)
        if ferramenta is None:
            continue
        if ferramenta in SEMPRE_RECURSIVO:
            alvo = caminho_raiz(args)
        elif ferramenta in RECURSIVO_COM_FLAG:
            flag = RECURSIVO_COM_FLAG[ferramenta]
            alvo = caminho_raiz(args) if any(flag.match(a) for a in args) else None
        else:
            alvo = None
        if alvo:
            return ferramenta, alvo
    return None


def decidir(entrada):
    if entrada.get("tool_name") != "Bash":
        return None
    comando = (entrada.get("tool_input") or {}).get("command", "") or ""
    achado = busca_na_raiz(comando)
    if not achado:
        return None
    ferramenta, alvo = achado
    sid = entrada.get("session_id", "no-session")
    log(sid, "busca_raiz_bloqueada", ferramenta=ferramenta, alvo=alvo, comando=comando[:200])
    motivo = (f"`{ferramenta} {alvo}` walks the whole disk. In Git Bash, `/` is the MSYS root and `/proc/registry` "
              "exposes the Windows registry: a `find /` once stayed 3 h in kernel mode with 1.29 M handles (2026-10-28). "
              "Start from a narrow path: ~/.claude, ~/Codes, the current repo or a folder you know. "
              "If you really need a whole-disk search, use `where`/`Get-ChildItem` in PowerShell with `-Filter` "
              "and a `timeout`, and tell the user why.")
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": motivo}}


def main():
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        saida = decidir(json.load(sys.stdin))
    except Exception:  # fail open: never block the tool because of a hook error
        return 0
    if saida:
        print(json.dumps(saida))
    return 0


if __name__ == "__main__":
    sys.exit(main())
