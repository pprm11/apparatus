#!/usr/bin/env python3
r"""Hook PreToolUse (matcher Bash) do usuário: barra busca recursiva a partir da raiz no Windows.

Origem: em 28/10/2026 uma sessão rodou `find / -maxdepth 6 -path "*skill-creator*" -name quick_validate.py`.
No Git Bash `/` é a raiz do MSYS, que expõe o registro do Windows em /proc/registry, /proc/registry32 e
/proc/registry64 (com HKEY_PERFORMANCE_DATA). O find ficou 3 h num núcleo em kernel, com 1,29 M handles
abertos (82% do sistema) e 1,24 GB de pool não paginado. O timeout de 120 s do Bash mandou o comando para o
background sem matar; a sessão acabou e o processo ficou órfão.

Regra lexical e estreita (não é guardrail de linguagem natural): um comando de busca (find, fd, grep -r,
rg, ls -R, du, tree) cujo ponto de partida é a raiz (`/`, `/proc...`, `/c`, `C:\`, `/mnt/c`, `/cygdrive/c`)
é negado com a instrução de partir de ~/.claude, ~/Codes ou do repo. Qualquer outro caminho passa.

Falha aberta: erro no hook deixa o comando passar. Eventos em ~/.claude/scripts/medicoes/eventos.jsonl.
Testes offline: python -I ~/.claude/scripts/test_hook_bash_guard.py
"""
import json
import os
import re
import shlex
import sys
import time

EVENTOS = os.path.join(os.path.expanduser("~/.claude/scripts"), "medicoes", "eventos.jsonl")

# Ferramentas que andam a árvore inteira por padrão, e as que só andam com a flag ao lado.
SEMPRE_RECURSIVO = {"find", "fd", "rg", "du", "tree"}
RECURSIVO_COM_FLAG = {"grep": re.compile(r"^-[a-zA-Z]*[rR]|^--(recursive|dereference-recursive)$"),
                      "ls": re.compile(r"^-[a-zA-Z]*R|^--recursive$")}
SEPARADORES = {"|", "||", "&&", ";", "&", "(", ")", "{", "}"}
PREFIXOS = {"timeout", "nice", "ionice", "time", "sudo", "env", "command", "exec", "nohup", "stdbuf"}
RAIZ = re.compile(r"""^(?:
    /+ |                       # / e //
    /proc(?:/.*)? |            # /proc e tudo abaixo (registry, registry32, registry64)
    /c/? | /cygdrive/c/? | /mnt/c/? |   # o disco C: inteiro
    [A-Za-z]:[\\/]?            # C:\ C:/ C:
)$""", re.X)
# Caminhos estreitos que vivem sob /proc mas não andam o registro: /proc/<n>, /proc/meminfo etc. passam só
# se não forem busca recursiva; find /proc/meminfo seria inútil, então a regra acima nega o ramo inteiro.


def log(sid, tipo, **extra):
    try:
        os.makedirs(os.path.dirname(EVENTOS), exist_ok=True)
        with open(EVENTOS, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "sid": sid, "tipo": tipo, **extra},
                               ensure_ascii=False) + "\n")
    except OSError:
        pass


def tokens_de(comando):
    """Tokens do comando. Modo não POSIX para `C:\\` não virar escape; punctuation_chars separa `;`, `|`,
    `&&` e `>` mesmo colados na palavra. Aspas em volta do token são tiradas."""
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
    """Quebra o comando em segmentos de pipeline; cada segmento é a lista de tokens."""
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
    """Pula prefixos (timeout 10, env X=1, sudo) e devolve (ferramenta, args) ou (None, [])."""
    i = 0
    while i < len(tokens):
        t = tokens[i]
        base = os.path.basename(t.replace("\\", "/"))
        if base.endswith(".exe"):
            base = base[:-4]
        if base in PREFIXOS or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
            i += 1
            # timeout e nice levam um valor (10, 5m, -n 19) logo depois do nome
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
    """Devolve (ferramenta, caminho) do primeiro segmento que anda a raiz, ou None."""
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
    sid = entrada.get("session_id", "sem-sessao")
    log(sid, "busca_raiz_bloqueada", ferramenta=ferramenta, alvo=alvo, comando=comando[:200])
    motivo = (f"`{ferramenta} {alvo}` anda o disco inteiro. No Git Bash, `/` é a raiz do MSYS e `/proc/registry` "
              "expõe o registro do Windows: um `find /` já ficou 3 h em kernel com 1,29 M handles (28/10/2026). "
              "Parta de um caminho estreito: ~/.claude, ~/Codes, o repo atual ou a pasta que você conhece. "
              "Se precisar mesmo de um disco inteiro, use `where`/`Get-ChildItem` no PowerShell com `-Filter` "
              "e um `timeout`, e diga ao usuário por quê.")
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": motivo}}


def main():
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        saida = decidir(json.load(sys.stdin))
    except Exception:  # falha aberta: nunca travar a ferramenta por erro do hook
        return 0
    if saida:
        print(json.dumps(saida))
    return 0


if __name__ == "__main__":
    sys.exit(main())
