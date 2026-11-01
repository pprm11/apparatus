#!/usr/bin/env python3
"""Hook UserPromptSubmit do usuário. Três comportamentos, todos silenciosos quando não se aplicam.

1. Segredo no prompt  -> bloqueia o envio e diz o que tirar (ou "#segredo-ok" no texto libera).
2. Segundo "como tá indo?" na mesma sessão -> injeta uma instrução UMA vez: responder com telinha de
   fração e oferecer acompanhamento automático.
3. Sessão com 2+ compacts -> injeta uma instrução UMA vez: oferecer handoff em uma linha.

Falha aberta: qualquer erro deixa o prompt passar. Eventos vão para
~/.claude/scripts/medicoes/eventos.jsonl (o medir-prompts.py não depende deles).
Ativar: ver o diff proposto para ~/.claude/settings.json no relatório. Não está ativo por padrão.
"""
import json, os, re, sys, time

BASE = os.path.expanduser("~/.claude/scripts")
EVENTOS = os.path.join(BASE, "medicoes", "eventos.jsonl")
ESTADO = os.path.join(BASE, "estado")

SEGREDOS = {
    "aws_key": re.compile(r"\bAKIA[0-9A-Z]{12,}\b"),
    "token_gh": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "sk_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "valor_de_chave": re.compile(
        r"(api[_-]?key|secret|signing[_-]?key|token)[\"']?\s*[:=]\s*[\"']?(?![$<{])[A-Za-z0-9_\-+/=]{20,}", re.I),
    "senha": re.compile(r"(senha|password)\s*[:=]\s*(?![$<{])\S{6,}", re.I),
    "pem": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
PING = re.compile(
    r"(como (ta|tá|esta|está) (indo|os |as |o plano|a lista)|como t ?aindo|previs[aã]o|terminou\?|acabou\?|"
    r"tem algo rodando|ta fazendo o q|q q vc ta fazendo|o que esta acontecendo|esta fazendo algo)", re.I)
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
    # Uma sessão nova apaga o estado de sessões paradas há mais de 7 dias.
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
    sid = entrada.get("session_id", "sem-sessao")
    if "#segredo-ok" not in prompt:
        achados = [k for k, rx in SEGREDOS.items() if rx.search(prompt)]
        if achados:
            log(sid, "segredo_bloqueado", tipos=achados)
            return {"decision": "block",
                    "reason": "Possível segredo no prompt (" + ", ".join(achados) + "). Troque o valor por <redigido> "
                              "ou use uma variável de ambiente e reenvie. Se for falso positivo, inclua #segredo-ok."}
    st = carregar_estado(sid)
    notas = []
    if len(prompt) <= 200 and PING.search(prompt):
        st["pings"] += 1
        log(sid, "ping_status", n=st["pings"])
        if st["pings"] >= 2 and not st["nudge_ping"]:
            st["nudge_ping"] = True
            notas.append("O usuário perguntou o status pela segunda vez nesta sessão. Responda com uma telinha de "
                         "status (fração do feito, o que roda agora, o que falta, sem datas) e ofereça UMA vez "
                         "acompanhamento sem ele precisar perguntar: aviso a cada etapa ou um artefato de status. "
                         "Não repita a oferta.")
    if not st["nudge_longa"] and compacts_na_sessao(entrada.get("transcript_path", "")) >= 2:
        st["nudge_longa"] = True
        log(sid, "sessao_longa")
        notas.append("Esta sessão já foi compactada 2 ou mais vezes. No fim desta resposta, em uma linha, ofereça "
                     "um handoff e uma sessão nova se o objetivo mudou desde a abertura. Faça isso uma vez.")
    salvar_estado(sid, st)
    if notas:
        return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": " ".join(notas)}}
    return None


def main():
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        saida = decidir(json.load(sys.stdin))
    except Exception:  # falha aberta: nunca travar o prompt do usuário
        return 0
    if saida:
        print(json.dumps(saida))  # ensure_ascii padrão: seguro no console do Windows
    return 0


if __name__ == "__main__":
    sys.exit(main())
