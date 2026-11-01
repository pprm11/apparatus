#!/usr/bin/env python3
"""Self-learning loop: notice what the user repeats, corrects and decides, and turn it into proposals,
memories and inbox items. Claude Code and Codex sessions are read the same way. harvest.sh runs `run`
hourly (behind HARVEST_LEARN=1); weekly.sh runs `effects`.

  python -I tools/learn.py run [--dry-run] [--no-models] [--days 30]
  python -I tools/learn.py effects [--report reports/learning-DATE.md] [--dry-run]
  python -I tools/learn.py applied P-2026-10-27-L1 [--date 2026-10-28]   # start the before/after clock
  python -I tools/learn.py status | hint

Pipeline of `run`:
  1. extract (offline): new user turns of every session, live or archived, become signals in the ledger:
     correction ("no, do X"), decision (an answer to a question the agent asked), prompt (the rest).
  2. cluster (offline): prompts and corrections that say the same thing, not yet covered by any rule,
     memory or skill, become candidates when they repeat on 2+ days.
  3. classify (Haiku, one call): which candidates are real, which decisions are durable.
  4. write (Sonnet, one call): proposal text and memory text. Python writes the files, the model never does.
Schema files are never touched: proposals go to proposals.md and wait for the user's yes.

State and ledger live in ~/.claude/decisions/learning/ (synced by sync.sh with the rest of decisions/).
Everything stored or sent to a model goes through redact.redact first. Budget: a USD cap per run and per day.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent_sessions  # noqa: E402
import codex_sessions  # noqa: E402
import decisions  # noqa: E402
import layers  # noqa: E402
from extract_prompts import typed_text  # noqa: E402
from redact import redact  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.environ.get("SYNC_MANIFEST", os.path.expanduser("~/Codes/psique/manifest.json"))
LEVELS = ("superego", "ego", "id")
DEFAULT_LEVEL = "ego"
HOME = os.path.expanduser("~/.claude")
TEXT_MAX = 160           # stored text per signal
PROMPT_TOKENS = (3, 60)  # prompts outside this size are pastes or one-word replies, not repeated requests
JACCARD = 0.35
REPEAT_MIN, CORRECTION_MIN, DAYS_MIN = 3, 2, 2
COVERED = 0.8            # a cluster whose core words are 80% in rules/memory/skills counts as covered
MAX_CANDIDATES, MAX_PROPOSALS, MAX_DECISIONS, MAX_MEMORIES = 12, 3, 15, 3
DECISION_MAX_AGE_DAYS = 7
BUDGET_RUN = float(os.environ.get("LEARN_BUDGET_USD", "0.40"))
BUDGET_DAY = float(os.environ.get("LEARN_BUDGET_DAY_USD", "1.00"))
HAIKU_SHARE = 0.25       # of the run budget; Sonnet gets the rest
MODEL_MIN_HOURS = 20     # the model stages run at most once a day, unless new decisions arrived
EFFECT_WINDOW_DAYS = 14

# Stopwords and phrase lists below are matched against accent-stripped, lowercased text. The *_PT entries are
# Portuguese-only data the signal extractor needs for users who write in Portuguese; English comes first.
STOP_EN = "the and for you with this that are not from have will can use per".split()
STOP_PT = "que para com uma por mas nao isso esse essa dos das nos nas como mais sobre pode ser tem foi vai ele ela aqui ali voce agora depois entao".split()
STOP = set(STOP_EN + STOP_PT)
CORRECTION_EN = (r"not what i (asked|said)|that'?s wrong|i (said|told you)|no,? (do|use|make)|redo|again,? please|"
                 r"stop (doing|using)|you (forgot|missed|got it wrong)|never again")
CORRECTION_PT = (r"nao[, ]+(faz|era|quero|e isso|foi isso|precisa|e assim)|de novo|refaz|refazer|ja (falei|disse|pedi|mandei)|"
                 r"esta errado|ta errado|voce (esqueceu|nao fez|errou)|nao e isso|para de|nunca mais|eu pedi|eu disse")
CORRECTION = re.compile(r"\b(" + CORRECTION_EN + "|" + CORRECTION_PT + r")\b")
APPROVAL_EN = r"approved|go ahead|ship it|option [a-d1-3]|i decided|make it a rule|go with|the decision is"
APPROVAL_PT = r"aprovado|pode seguir|pode fazer|taca pau|faz o que achar|vamos com|fechado|opcao [a-d1-3]|decidi|a decisao|vira regra|pode ser a"
APPROVAL = re.compile(r"\b(" + APPROVAL_EN + "|" + APPROVAL_PT + r")\b"
                      r"|^\s*(?:[1-9][a-d][,\s]*)+\b")
QUESTION_PT = r"opcao|opcoes|menu|recomend"
QUESTION = re.compile(r"\?|\b(option|options|menu|recommend|" + QUESTION_PT + ")", re.I)


def norm(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]{3,}", text)


def keywords(text: str) -> list[str]:
    return sorted({w for w in norm(text) if w not in STOP})


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def learn_dir(home: str) -> str:
    return os.path.join(home, "decisions", "learning")


def read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def load_json(path: str, default: object) -> object:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def save_json(path: str, data: object) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load_state(home: str) -> dict:
    state = load_json(os.path.join(learn_dir(home), "state.json"), {})
    state.setdefault("sessions", {})
    state.setdefault("spend", {})
    state.setdefault("proposed", [])   # {id, core, date, proposal, kind, applied}
    state.setdefault("decided", [])    # signal ids already routed
    state.setdefault("history", [])
    state.setdefault("rejected", [])   # {core, date}: candidates the model judged not real, not asked again for a while
    return state


def save_state(home: str, state: dict) -> None:
    save_json(os.path.join(learn_dir(home), "state.json"), state)


def load_ledger(home: str) -> list[dict]:
    out = []
    try:
        with open(os.path.join(learn_dir(home), "signals.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def append_ledger(home: str, signals: list[dict]) -> None:
    if not signals:
        return
    path = os.path.join(learn_dir(home), "signals.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        for s in signals:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- extract

def read_turns(session: agent_sessions.Session) -> list[tuple[str, str, str]]:
    """(timestamp, role, text) of what was said in one session, no tool output."""
    turns: list[tuple[str, str, str]] = []
    if not session.transcript or not os.path.isfile(session.transcript):
        return turns
    if session.harness == "codex":
        for r in codex_sessions.iter_file(session.transcript):
            if r["role"] in ("user", "assistant"):
                turns.append((r["ts"], r["role"], r["text"]))
        return turns
    with open(session.transcript, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("isSidechain"):
                continue
            ts = e.get("timestamp", "")
            if e.get("type") == "user":
                text = typed_text(e)
                if text:
                    turns.append((ts, "user", text))
            elif e.get("type") == "assistant":
                blocks = e.get("message", {}).get("content")
                if isinstance(blocks, list):
                    text = "\n".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
                    if text.strip():
                        turns.append((ts, "assistant", text.strip()))
    return turns


def fold(text: str) -> str:
    """Lowercase, accent-stripped, whitespace-collapsed text with punctuation and short words kept (the phrase
    lists above contain 1-2 letter words such as "no, do" and "1a")."""
    text = unicodedata.normalize("NFKD", text.lower())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


def classify_turn(text: str, prev_assistant: str) -> str:
    n = fold(text)
    if CORRECTION.search(n):
        return "correction"
    if len(text) <= 400 and APPROVAL.search(n) and prev_assistant and QUESTION.search(prev_assistant[-600:]):
        return "decision"
    return "prompt"


def clip(text: str, limit: int = TEXT_MAX) -> str:
    text = redact(" ".join(text.split()))
    return text if len(text) <= limit else text[:limit] + "..."


def session_signals(session: agent_sessions.Session, start: int, since: float) -> tuple[list[dict], int]:
    """Signals for user turns number >= start; returns them and the new count of user turns."""
    signals, n_user, prev = [], 0, ""
    for ts, role, text in read_turns(session):
        if role == "assistant":
            prev = text
            continue
        idx, n_user = n_user, n_user + 1
        if idx < start:
            continue
        try:
            when = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() if ts else session.last_activity
        except ValueError:
            when = session.last_activity
        if when < since:
            continue
        kind = classify_turn(text, prev)
        toks = keywords(text)
        if kind == "prompt" and not PROMPT_TOKENS[0] <= len(norm(text)) <= PROMPT_TOKENS[1]:
            continue
        sig = {"id": hashlib.sha1(f"{session.harness}:{session.id}:{idx}".encode()).hexdigest()[:12],
               "ts": datetime.fromtimestamp(when, timezone.utc).strftime("%Y-%m-%dT%H:%M"),
               "harness": session.harness, "session": session.id[:12], "proj": codex_sessions.project_key(session.cwd),
               "kind": kind, "text": clip(text), "tokens": toks[:12]}
        if kind != "prompt" and prev:
            sig["ctx"] = clip(prev[-300:], 220)
        signals.append(sig)
    return signals, n_user


def layer_dirs(manifest: str = "") -> list[str]:
    """Folders of the layer repos named in the manifest, plus this repo. Sessions run there are about the
    context itself and would feed the loop with its own work."""
    dirs = [os.path.normcase(REPO)]
    try:
        for layer in layers.active_layers(layers.load_manifest(manifest or MANIFEST)):
            dirs.append(os.path.normcase(layers.expand(layer["path"])))
    except (OSError, ValueError, KeyError, SystemExit):
        pass
    return dirs


def ego_dir(manifest: str = "") -> str:
    """Where proposals.md, log.md and reports/ live: $LEARN_EGO, else the active ego layer, else this repo."""
    if os.environ.get("LEARN_EGO"):
        return os.environ["LEARN_EGO"]
    try:
        for layer in layers.active_layers(layers.load_manifest(manifest or MANIFEST)):
            if layer.get("level") == "ego":
                return layers.expand(layer["path"])
    except (OSError, ValueError, KeyError, SystemExit):
        pass
    return REPO


def extract(home: str, state: dict, days: int, sessions: list | None = None) -> list[dict]:
    since = time.time() - days * 86400
    fresh: list[dict] = []
    own = layer_dirs()
    for s in agent_sessions.all_sessions() if sessions is None else sessions:
        if any(os.path.normcase(s.cwd or "").startswith(d) for d in own):
            continue
        key = f"{s.harness}:{s.id}"
        seen = state["sessions"].get(key, {})
        if s.last_activity < since or s.last_activity <= seen.get("mtime", 0):
            continue
        sigs, n_user = session_signals(s, seen.get("n_user", 0), since)
        fresh += sigs
        state["sessions"][key] = {"mtime": s.last_activity, "n_user": n_user}
    return fresh


# ---------------------------------------------------------------- cluster

def corpus_tokens(home: str) -> set[str]:
    patterns = ["*.md", "rules/*.md", "skills/*/SKILL.md", "projects/*/memory/*.md"]
    words: set[str] = set()
    for pat in patterns:
        for path in glob.glob(os.path.join(home, pat)):
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    words.update(norm(fh.read()))
            except OSError:
                continue
    return words


def cluster(signals: list[dict], covered_words: set[str], since: str = "") -> list[dict]:
    """Group prompts and corrections that share their keywords; keep those that repeat and are uncovered."""
    groups: list[dict] = []
    for s in sorted(signals, key=lambda x: x["ts"]):
        if s["kind"] == "decision" or s["ts"] < since:
            continue
        toks = set(s["tokens"])
        if len(toks) < 3:
            continue
        for g in groups:
            if jaccard(toks, g["core"]) >= JACCARD:
                g["members"].append(s)
                if len(toks & g["core"]) >= 3:
                    g["core"] = g["core"] & toks
                break
        else:
            groups.append({"core": set(toks), "members": [s]})
    out = []
    for g in groups:
        m = g["members"]
        days = {x["ts"][:10] for x in m}
        corr = sum(x["kind"] == "correction" for x in m)
        kind = "correction" if corr * 2 >= len(m) else "repeat"
        if len(days) < DAYS_MIN or len(m) < (CORRECTION_MIN if kind == "correction" else REPEAT_MIN):
            continue
        core = sorted(g["core"])
        coverage = sum(w in covered_words for w in core) / len(core)
        if coverage >= COVERED:
            continue
        out.append({"id": hashlib.sha1(" ".join(core[:5]).encode()).hexdigest()[:10], "kind": kind, "core": core,
                    "n": len(m), "days": len(days), "first": min(days), "last": max(days),
                    "coverage": round(coverage, 2), "samples": [x["text"] for x in m[-4:]],
                    "ids": [x["id"] for x in m]})
    return sorted(out, key=lambda c: (-c["n"], c["id"]))


REJECT_DAYS = 14


def already_proposed(c: dict, state: dict) -> bool:
    limit = (date.today() - timedelta(days=REJECT_DAYS)).isoformat()
    return (any(jaccard(set(c["core"]), set(p["core"])) >= 0.5 for p in state["proposed"])
            or any(r["date"] >= limit and jaccard(set(c["core"]), set(r["core"])) >= 0.5 for r in state["rejected"]))


def decision_candidates(signals: list[dict], state: dict) -> list[dict]:
    limit = (date.today() - timedelta(days=DECISION_MAX_AGE_DAYS)).isoformat()
    todo = [s for s in signals if s["kind"] == "decision" and s["id"] not in state["decided"] and s["ts"][:10] >= limit]
    return sorted(todo, key=lambda s: s["ts"], reverse=True)[:MAX_DECISIONS]


# ---------------------------------------------------------------- models

Runner = Callable[[str, str, float, bool], tuple[str, float]]


def claude_runner(prompt: str, model: str, budget: float, read_tools: bool) -> tuple[str, float]:
    """One `claude -p` call on the user's login (never an API key). Returns (text, cost in USD)."""
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    cmd = ["claude", "-p", "--model", model, "--max-budget-usd", f"{budget:.2f}", "--output-format", "json",
           "--disallowedTools", "Bash", "Edit", "Write"]
    if read_tools:
        cmd += ["--add-dir", HOME, "--allowedTools", "Read", "Glob", "Grep"]
    else:
        cmd += ["--disallowedTools", "Read", "Glob", "Grep"]
    done = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", env=env, timeout=600)
    try:
        out = json.loads(done.stdout)
        return str(out.get("result", "")), float(out.get("total_cost_usd") or 0)
    except ValueError:
        return done.stdout, 0.0


def parse_json(text: str) -> dict:
    a, b = text.find("{"), text.rfind("}")
    try:
        data = json.loads(text[a:b + 1]) if 0 <= a < b else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def spent_today(state: dict) -> float:
    return float(state["spend"].get(date.today().isoformat(), 0))


def call_model(prompt_file: str, payload: dict, model: str, cap: float, state: dict, runner: Runner,
               read_tools: bool = False) -> dict:
    left = BUDGET_DAY - spent_today(state)
    budget = min(cap, left)
    if budget < 0.02:
        return {"_skipped": "daily budget used"}
    with open(os.path.join(REPO, "prompts", prompt_file), encoding="utf-8") as fh:
        template = fh.read()
    prompt = template.replace("{{PAYLOAD}}", json.dumps(payload, ensure_ascii=False, indent=1)).replace("{{HOME}}", HOME.replace("\\", "/"))
    text, cost = runner(prompt, model, budget, read_tools)
    today = date.today().isoformat()
    state["spend"][today] = round(spent_today(state) + cost, 4)
    state["spend"] = dict(sorted(state["spend"].items())[-30:])
    return parse_json(text)


# ---------------------------------------------------------------- write outputs

def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))).strip("-")[:60]


def next_proposal_id(proposals_text: str) -> str:
    day = date.today().isoformat()
    n = len(re.findall(rf"### P-{day}-L\d+", proposals_text)) + 1
    return f"P-{day}-L{n}"


def level_of(item: dict) -> str:
    return item.get("level") if item.get("level") in LEVELS else DEFAULT_LEVEL


def format_proposal(pid: str, c: dict, item: dict) -> str:
    quotes = "; ".join('"' + " ".join(t.split()[:12]) + '"' for t in c["samples"][:3])
    return (f"\n### {pid} · {item['title']}\n"
            f"Kind: {item.get('kind', 'rule')} ({'repeated correction' if c['kind'] == 'correction' else 'repeated request'})\n"
            f"Level: {level_of(item)}\n"
            f"From: learn.py, {c['n']} signals on {c['days']} days ({c['first']} to {c['last']}), coverage {c['coverage']}; {quotes}\n"
            f"To: {item['to']}\n"
            f"Why: {item['why']}\n"
            f"Status: open\n"
            f"Source: learn (cluster {c['id']}; effect measured {EFFECT_WINDOW_DAYS} days after approval)\n")


DUPLICATE = 0.5


def memory_projects(home: str) -> list[str]:
    return sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(home, "projects", "*", "memory")))


def find_duplicate(home: str, item: dict) -> str:
    """Name of an existing memory (any project) that says about the same as `item`, or ''."""
    new = set(keywords(" ".join(str(item.get(k, "")) for k in ("slug", "title", "description", "keywords", "body"))))
    for path in glob.glob(os.path.join(home, "projects", "*", "memory", "*.md")):
        if os.path.basename(path) == "MEMORY.md":
            continue
        old = set(keywords(read_text(path)[:1500]))
        if jaccard(new, old) >= DUPLICATE:
            return os.path.basename(path)
    return ""


def write_memory(home: str, item: dict, state: dict) -> str | None:
    folder = os.path.join(home, "projects", item.get("project", ""), "memory")
    name = slug(item.get("slug") or item.get("name", ""))
    if not name or not os.path.isdir(folder):
        return None
    path = os.path.join(folder, name + ".md")
    if os.path.exists(path) or find_duplicate(home, item):
        return None
    desc = redact(" ".join(str(item.get("description", "")).split()))
    kws = redact(str(item.get("keywords", "")))
    body = redact(str(item.get("body", "")).strip())
    if not desc or not body:
        return None
    mtype = item.get("type") if item.get("type") in ("user", "feedback", "project", "reference") else "project"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"---\nname: {name}\ndescription: {desc}\nmetadata:\n  keywords: {kws}\n  type: {mtype}\nlevel: {level_of(item)}\n---\n{body}\n")
    index = os.path.join(folder, "MEMORY.md")
    line = f"- [{item.get('title') or name}]({name}.md) — {desc[:100]}"
    try:
        with open(index, encoding="utf-8") as fh:
            has = name + ".md" in fh.read()
    except OSError:
        has = False
    if not has:
        with open(index, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")
    return path


def route_inbox(home: str, item: dict, sig: dict) -> str:
    data = decisions.load(home)
    if any(i.get("key") == "learn:" + sig["id"] for i in data["items"]):
        return ""
    new = decisions.new_item(data, "manual", redact(str(item.get("title", sig["text"])))[:140], level=level_of(item),
                             detail=redact(str(item.get("fact", sig["text"]))), options=["A record it in memory", "B ignore"],
                             source=f"learn: {sig['harness']} {sig['session']}", key="learn:" + sig["id"])
    decisions.save(data, home)
    return new["id"]


# ---------------------------------------------------------------- run

def run(home: str, days: int, dry_run: bool, use_models: bool, runner: Runner = claude_runner,
        sessions: list | None = None, ego: str = "") -> dict:
    ego = ego or ego_dir()
    state = load_state(home)
    report = {"signals": 0, "candidates": 0, "decisions": 0, "proposals": [], "memories": [], "inbox": [],
              "model": "skipped", "spend": 0.0}
    fresh = extract(home, state, days, sessions)
    report["signals"] = len(fresh)
    ledger = load_ledger(home) + fresh
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    cands = [c for c in cluster(ledger, corpus_tokens(home), cutoff) if not already_proposed(c, state)][:MAX_CANDIDATES]
    decs = decision_candidates(ledger, state)
    report["candidates"], report["decisions"] = len(cands), len(decs)
    payload = {"repeats": [{k: c[k] for k in ("id", "kind", "n", "days", "coverage", "samples")} for c in cands],
               "decisions": [{"id": d["id"], "ts": d["ts"], "proj": d["proj"], "answer": d["text"], "question": d.get("ctx", "")} for d in decs]}
    last = state.get("last_model_run", 0)
    due = (time.time() - last) / 3600 >= MODEL_MIN_HOURS or any(d["id"] not in state["decided"] for d in decs)
    if dry_run or not use_models or not due or not (cands or decs):
        report["model"] = "dry-run" if dry_run else "no-models" if not use_models else "not due" if not due else "nothing to ask"
        report["payload"] = payload
        if not dry_run:
            append_ledger(home, fresh)
            save_state(home, state)
        return report

    before = spent_today(state)
    haiku_cap = round(BUDGET_RUN * HAIKU_SHARE, 2)
    verdict = call_model("learn-classify.md", payload, "haiku", haiku_cap, state, runner)
    real_ids = {r.get("id") for r in verdict.get("repeats", []) if isinstance(r, dict) and r.get("real")}
    if verdict and "_skipped" not in verdict:
        state["rejected"] = [r for r in state["rejected"] if r["date"] >= (date.today() - timedelta(days=REJECT_DAYS)).isoformat()]
        state["rejected"] += [{"core": c["core"], "date": date.today().isoformat()} for c in cands if c["id"] not in real_ids]
    durable = {r.get("id"): r for r in verdict.get("decisions", []) if isinstance(r, dict) and r.get("route") in ("memory", "inbox")}
    by_id = {c["id"]: c for c in cands}
    by_sig = {d["id"]: d for d in decs}
    write_in = {"repeats": [r for r in payload["repeats"] if r["id"] in real_ids][:MAX_PROPOSALS],
                "decisions": [dict(d, route=durable[d["id"]]["route"], level=durable[d["id"]].get("level", "")) for d in payload["decisions"] if d["id"] in durable],
                "memory_projects": memory_projects(home)}
    written = {}
    if write_in["repeats"] or write_in["decisions"]:
        written = call_model("learn-propose.md", write_in, "sonnet", round(BUDGET_RUN - haiku_cap, 2), state, runner, read_tools=True)
    proposals_path = os.path.join(ego, "proposals.md")
    ptext = read_text(proposals_path)
    for item in written.get("proposals", [])[:MAX_PROPOSALS]:
        c = by_id.get(item.get("id"))
        if not c or not item.get("title") or not item.get("to") or not item.get("why"):
            continue
        item = {k: redact(str(v)) for k, v in item.items()}
        pid = next_proposal_id(ptext)
        block = format_proposal(pid, c, item)
        ptext += block
        with open(proposals_path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(block)
        state["proposed"].append({"id": c["id"], "core": c["core"], "date": date.today().isoformat(), "proposal": pid,
                                  "kind": c["kind"], "applied": ""})
        report["proposals"].append(pid)
    for item in written.get("memories", [])[:MAX_MEMORIES]:
        sig = by_sig.get(item.get("decision_id"))
        if sig and durable.get(sig["id"], {}).get("route") == "memory":
            item.setdefault("level", durable[sig["id"]].get("level", ""))
            # the model may file it under another existing project; otherwise it stays with the session's project
            if item.get("project") not in write_in["memory_projects"]:
                item["project"] = sig["proj"]
            if write_memory(home, item, state):
                report["memories"].append(slug(item.get("slug") or item.get("name", "")))
            state["decided"].append(sig["id"])
    for sid, v in durable.items():
        sig = by_sig.get(sid)
        if sig and v.get("route") == "inbox" and sid not in state["decided"]:
            if route_inbox(home, v, sig):
                report["inbox"].append(sid)
            state["decided"].append(sig["id"])
    state["decided"] = (state["decided"] + [d["id"] for d in decs if d["id"] not in durable])[-2000:]
    state["last_model_run"] = time.time()
    report["model"] = "ran"
    report["spend"] = round(spent_today(state) - before, 4)
    state["last_run"] = {"date": date.today().isoformat(), "proposals": len(report["proposals"]), "memories": len(report["memories"])}
    append_ledger(home, fresh)
    save_state(home, state)
    if report["proposals"] or report["memories"] or report["inbox"]:
        log = os.path.join(ego, "log.md")
        with open(log, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(f"\n## [{date.today().isoformat()}] learn | {len(report['proposals'])} proposals · "
                     f"{len(report['memories'])} memories · {len(report['inbox'])} inbox · US$ {report['spend']}\n"
                     + "".join(f"- proposal {p}\n" for p in report["proposals"])
                     + "".join(f"- memory {m}\n" for m in report["memories"]))
    return report


# ---------------------------------------------------------------- effects

STATUS = re.compile(r"^Status: (approved|partially approved)[^\n]*", re.M)


def proposal_status(text: str, pid: str) -> str:
    m = re.search(rf"### {re.escape(pid)} .*?(?=\n### P-|\Z)", text, re.S)
    if not m:
        return ""
    s = STATUS.search(m.group(0))
    return s.group(0) if s else ""


def count_matching(ledger: list[dict], core: set, start: str, end: str) -> int:
    return sum(1 for s in ledger if start <= s["ts"][:10] < end and s["kind"] != "decision"
               and jaccard(set(s["tokens"]), core) >= JACCARD)


def effects(home: str, ego: str = "", today: date | None = None) -> list[dict]:
    ego = ego or ego_dir()
    """Before/after count of matching signals for every learn proposal the user approved."""
    today = today or date.today()
    state = load_state(home)
    ledger = load_ledger(home)
    ptext = read_text(os.path.join(ego, "proposals.md"))
    out = []
    for p in state["proposed"]:
        status = proposal_status(ptext, p["proposal"])
        if not status:
            out.append({"proposal": p["proposal"], "verdict": "waiting for yes"})
            continue
        if not p.get("applied"):
            p["applied"] = today.isoformat()   # first time seen approved; `applied --date` corrects it
        start = date.fromisoformat(p["applied"])
        core = set(p["core"])
        before = count_matching(ledger, core, (start - timedelta(days=EFFECT_WINDOW_DAYS)).isoformat(), start.isoformat())
        after = count_matching(ledger, core, start.isoformat(), (start + timedelta(days=EFFECT_WINDOW_DAYS)).isoformat())
        if today < start + timedelta(days=EFFECT_WINDOW_DAYS):
            verdict = f"measuring until {(start + timedelta(days=EFFECT_WINDOW_DAYS)).isoformat()}"
        elif after == 0 or after * 2 <= before:
            verdict = "worked"
        else:
            verdict = "did not work: revise or drop"
        p["verdict"] = verdict
        out.append({"proposal": p["proposal"], "applied": p["applied"], "before": before, "after": after, "verdict": verdict})
    kinds = {}
    for s in ledger:
        if s["ts"][:10] >= (today - timedelta(days=7)).isoformat():
            kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
    state["history"].append({"date": today.isoformat(), "week_signals": kinds, "proposed": len(state["proposed"]),
                             "worked": sum(e.get("verdict") == "worked" for e in out)})
    state["history"] = state["history"][-52:]
    save_state(home, state)
    return out


def render_report(rows: list[dict], state: dict) -> str:
    lines = [f"# Learning, {date.today().isoformat()}", ""]
    lines.append(f"Loop proposals: {len(state['proposed'])}; spent today: US$ {spent_today(state):.2f}.")
    lines.append("")
    if rows:
        lines += ["| Proposal | Before | After | Verdict |", "|---|---|---|---|"]
        lines += [f"| {r['proposal']} | {r.get('before', '-')} | {r.get('after', '-')} | {r['verdict']} |" for r in rows]
    else:
        lines.append("No loop proposals yet.")
    return "\n".join(lines) + "\n"


def mark_applied(home: str, pid: str, when: str) -> bool:
    state = load_state(home)
    for p in state["proposed"]:
        if p["proposal"] == pid:
            p["applied"] = when
            save_state(home, state)
            return True
    return False


def hint(home: str) -> str:
    last = load_state(home).get("last_run", {})
    parts = []
    if last.get("proposals"):
        parts.append(f"docs(proposal): add {last['proposals']} learning proposal(s)")
    if last.get("memories"):
        parts.append(f"chore(memory): {last['memories']} memory from learning loop")
    return "\n".join(parts) or "feat(learning): update signal ledger"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default=HOME)
    ap.add_argument("--ego", default="", help="folder with proposals.md, log.md and reports/ (default: $LEARN_EGO or the manifest ego layer)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--no-models", action="store_true")
    p_run.add_argument("--days", type=int, default=30)
    p_eff = sub.add_parser("effects")
    p_eff.add_argument("--report", default="")
    p_eff.add_argument("--dry-run", action="store_true")
    p_app = sub.add_parser("applied")
    p_app.add_argument("proposal")
    p_app.add_argument("--date", default=date.today().isoformat())
    sub.add_parser("status")
    sub.add_parser("hint")
    args = ap.parse_args()

    if args.cmd == "run":
        rep = run(args.home, args.days, args.dry_run, not args.no_models, ego=args.ego)
        payload = rep.pop("payload", None)
        print(json.dumps(rep, ensure_ascii=False))
        if args.dry_run and payload:
            print(json.dumps(payload, ensure_ascii=False, indent=1))
    elif args.cmd == "effects":
        if args.dry_run:
            import copy
            state = copy.deepcopy(load_state(args.home))
            rows = effects(args.home, args.ego)
            save_state(args.home, state)   # leave the state as it was
        else:
            rows = effects(args.home, args.ego)
            state = load_state(args.home)
        text = render_report(rows, state)
        if args.report and not args.dry_run:
            with open(args.report, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        print(text)
    elif args.cmd == "applied":
        print("ok" if mark_applied(args.home, args.proposal, args.date) else "unknown proposal")
    elif args.cmd == "status":
        s = load_state(args.home)
        print(json.dumps({"sessions": len(s["sessions"]), "signals": len(load_ledger(args.home)), "proposed": len(s["proposed"]),
                          "spend_today": spent_today(s)}, indent=1))
    elif args.cmd == "hint":
        print(hint(args.home))
    return 0


if __name__ == "__main__":
    sys.exit(main())
