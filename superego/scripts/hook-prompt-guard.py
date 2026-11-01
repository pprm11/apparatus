#!/usr/bin/env python3
"""User's UserPromptSubmit hook. Three behaviors, all silent when they do not apply.

1. Secret in the prompt -> blocks the submission and says what to remove ("#secret-ok" in the text releases it).
2. Second "how is it going?" in the same session -> injects an instruction ONCE: answer with a progress
   widget (fraction done) and offer automatic follow-up.
3. Session with 2+ compacts -> injects an instruction ONCE: offer a handoff in one line.

Fails open: any error lets the prompt through. Events go to
~/.claude/scripts/medicoes/eventos.jsonl (medir-prompts.py does not depend on them).
To enable: see the proposed diff for ~/.claude/settings.json in the report. Not active by default.
"""
import json, os, re, sys, time

BASE = os.path.expanduser("~/.claude/scripts")
EVENTOS = os.path.join(BASE, "medicoes", "eventos.jsonl")
ESTADO = os.path.join(BASE, "estado")

SEGREDOS = {
    "aws_key": re.compile(r"\bAKIA[0-9A-Z]{12,}\b"),
    "gh_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "sk_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "key_value": re.compile(
        r"(api[_-]?key|secret|signing[_-]?key|token)[\"']?\s*[:=]\s*[\"']?(?![$<{])[A-Za-z0-9_\-+/=]{20,}", re.I),
    "password": re.compile(r"(senha|password)\s*[:=]\s*(?![$<{])\S{6,}", re.I),
    "pem": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
# Status-ping phrases. The Portuguese list is data the matcher needs (the author's own phrasing).
PING_PHRASES_EN = (r"how('s| is) it going|how are (we|things) doing|any (progress|update)|status\??$|"
                   r"are you (done|finished)|is it done\?|what are you (doing|working on)|anything running")
PING_PHRASES_PT = (r"como (ta|tá|esta|está) (indo|os |as |o plano|a lista)|como t ?aindo|previs[aã]o|terminou\?|"
                   r"acabou\?|tem algo rodando|ta fazendo o q|q q vc ta fazendo|o que esta acontecendo|"
                   r"esta fazendo algo")
PING = re.compile("(" + PING_PHRASES_EN + "|" + PING_PHRASES_PT + ")", re.I)
COMPACT = re.compile(r"This session is being continued|The summarized conversation")


def log(sid, tipo, **extra):
    try:
        os.makedirs(os.path.dirname(EVENTOS), exist_ok=True)
        with open(EVENTOS, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "sid": sid, "tipo": tipo, **extra}) + "\n")
    except OSError:
        pass


def carregar_estado(sid):
    try:
        return json.load(open(os.path.join(ESTADO, sid + ".json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {"pings": 0, "nudge_ping": False, "nudge_longa": False}


def salvar_estado(sid, st):
    try:
        os.makedirs(ESTADO, exist_ok=True)
        caminho = os.path.join(ESTADO, sid + ".json")
        if not os.path.exists(caminho):
            podar_estado()
        json.dump(st, open(caminho, "w", encoding="utf-8"))
    except OSError:
        pass


def podar_estado(dias=7):
    # A new session deletes the state of sessions idle for more than 7 days.
    limite = time.time() - dias * 86400
    for nome in os.listdir(ESTADO):
        p = os.path.join(ESTADO, nome)
        try:
            if os.path.getmtime(p) < limite:
                os.remove(p)
        except OSError:
            pass


def compacts_na_sessao(caminho):
    try:
        return len(COMPACT.findall(open(caminho, encoding="utf-8", errors="replace").read()))
    except OSError:
        return 0


def decidir(entrada):
    prompt = entrada.get("prompt", "") or ""
    sid = entrada.get("session_id", "no-session")
    if "#secret-ok" not in prompt and "#segredo-ok" not in prompt:  # the old tag works until the next major
        achados = [k for k, rx in SEGREDOS.items() if rx.search(prompt)]
        if achados:
            log(sid, "segredo_bloqueado", tipos=achados)
            return {"decision": "block",
                    "reason": "Possible secret in the prompt (" + ", ".join(achados) + "). Replace the value with <redacted> "
                              "or use an environment variable and resend. If it is a false positive, include #secret-ok."}
    st = carregar_estado(sid)
    notas = []
    if len(prompt) <= 200 and PING.search(prompt):
        st["pings"] += 1
        log(sid, "ping_status", n=st["pings"])
        if st["pings"] >= 2 and not st["nudge_ping"]:
            st["nudge_ping"] = True
            notas.append("The user asked for status for the second time in this session. Answer with a status "
                         "widget (fraction done, what is running now, what is left, no dates) and offer ONCE "
                         "follow-up without the user having to ask: a notice at each step or a status artifact. "
                         "Do not repeat the offer.")
    if not st["nudge_longa"] and compacts_na_sessao(entrada.get("transcript_path", "")) >= 2:
        st["nudge_longa"] = True
        log(sid, "sessao_longa")
        notas.append("This session has already been compacted 2 or more times. At the end of this answer, in one line, "
                     "offer a handoff and a new session if the goal changed since the start. Do this once.")
    salvar_estado(sid, st)
    if notas:
        return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": " ".join(notas)}}
    return None


def main():
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        saida = decidir(json.load(sys.stdin))
    except Exception:  # fail open: never block the user prompt
        return 0
    if saida:
        print(json.dumps(saida))  # default ensure_ascii: safe on the Windows console
    return 0


if __name__ == "__main__":
    sys.exit(main())
