#!/usr/bin/env python3
"""Deterministic AI-tell scorer. Same input file -> same points, every run.

Usage: python3 ai_tells.py <text-file>
Prints JSON: per-check points, values, and rewrite advice for failed checks.
Score is out of 60 (the agent rubric contributes the other 40 of the combined 100).
"""
import json
import re
import statistics
import sys

TRANSITIONS = [
    "moreover", "furthermore", "additionally", "in addition", "in conclusion",
    "overall,", "notably", "importantly", "crucially", "that said",
    "in summary", "to summarize", "first and foremost", "on the other hand",
    "it is worth noting", "it's worth noting", "it is important to note",
]
HEDGES = [
    "it's worth noting", "it is worth noting", "it's important to remember",
    "it is important to remember", "it should be noted", "generally speaking",
    "in many cases", "to some extent", "arguably",
]
AI_LEXICON = [
    "delve", "delves", "delving", "leverage", "leverages", "leveraging",
    "seamless", "seamlessly", "pivotal", "tapestry", "underscores",
    "underscore", "boasts", "fosters", "foster", "streamline", "holistic",
    "myriad", "plethora", "game-changer", "elevate", "in today's",
    "crucially", "robustly",
]


def split_sentences(text):
    out = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý\"'(¿¡])", para)
        out.extend(p.strip() for p in parts if p.strip())
    return out


def per_1000(count, n_words):
    return count * 1000.0 / max(n_words, 1)


def main(path):
    text = open(path, encoding="utf-8").read()
    words = text.split()
    n_words = len(words)
    sents = split_sentences(text)
    sent_lens = [len(s.split()) for s in sents] or [0]
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    para_lens = [len(p.split()) for p in paras] or [0]
    lower = text.lower()

    checks = []

    def add(name, points, maximum, value, advice):
        checks.append({
            "check": name, "points": points, "max": maximum,
            "value": value, "advice": advice if points < maximum else "ok",
        })

    # 1. Burstiness: coefficient of variation of sentence lengths (10)
    cv = (statistics.pstdev(sent_lens) / statistics.mean(sent_lens)) if statistics.mean(sent_lens) else 0
    pts = 10 if cv >= 0.55 else 6 if cv >= 0.40 else 3 if cv >= 0.25 else 0
    add("sentence_burstiness_cv", pts, 10, round(cv, 3),
        "Sentence lengths too uniform: mix very short sentences (<=8 words) with long ones.")

    # 2. Short-sentence presence (5)
    short_pct = sum(1 for L in sent_lens if L <= 8) / len(sent_lens)
    pts = 5 if short_pct >= 0.10 else 3 if short_pct >= 0.05 else 0
    add("short_sentence_share", pts, 5, round(short_pct, 3),
        "Add a few blunt short sentences; humans punch points occasionally.")

    # 3. Banned characters (5): the user-validated list of AI-tell punctuation.
    # Inline code spans (`...`) are exempt; hyphens in words/flags never match.
    scan = re.sub(r"`[^`]*`", "", text)
    BANNED = {
        "—": "em dash", "–": "en dash", "…": "ellipsis",
        "“": "curly double quote", "”": "curly double quote",
        "‘": "curly single quote", "’": "curly apostrophe",
        " ": "non-breaking space", "​": "zero-width space",
        "•": "bullet", "◦": "bullet", "▪": "bullet",
        ";": "semicolon",
    }
    banned_found = []
    for ch, name in BANNED.items():
        for m in re.finditer(re.escape(ch), scan):
            ctx = scan[max(0, m.start() - 25):m.start() + 25].replace("\n", " ")
            banned_found.append({"char": name, "context": ctx})
    for m in re.finditer(r"\S+ - \S+", scan):
        banned_found.append({"char": "spaced hyphen as dash", "context": m.group(0)})
    # Parentheses count as asides; bare call parens like run() and the (url)
    # part of markdown links are syntax, not asides.
    scan_np = re.sub(r"\w\(\)", "", re.sub(r"\]\([^)]*\)", "]", scan))
    for m in re.finditer(r"\(", scan_np):
        ctx = scan_np[max(0, m.start() - 25):m.start() + 40].replace("\n", " ")
        banned_found.append({"char": "parenthetical", "context": ctx})
    # Colons in prose. Exempt: URLs, digit:digit (times, ratios, chapter:verse);
    # code spans were already stripped above.
    scan_c = re.sub(r"https?://\S+", "", scan)
    for m in re.finditer(r":", scan_c):
        before = scan_c[m.start() - 1] if m.start() > 0 else ""
        after = scan_c[m.end()] if m.end() < len(scan_c) else ""
        if before.isdigit() and after.isdigit():
            continue
        ctx = scan_c[max(0, m.start() - 25):m.start() + 25].replace("\n", " ")
        banned_found.append({"char": "colon", "context": ctx})
    # Hyphenated compound words in prose ('in-memory', 'read-then-write').
    # Exempt: tokens with a dot or slash (file names, paths), flag tokens
    # starting with '-', and anything in backticks (already stripped) - wrap
    # hyphenated technical identifiers in backticks rather than respelling them.
    for m in re.finditer(r"[A-Za-z0-9./\\_-]+", scan_c):
        tok = m.group(0)
        if tok.startswith("-") or "." in tok or "/" in tok or "\\" in tok:
            continue
        if re.fullmatch(r"[A-Za-z]+(?:-[A-Za-z]+)+", tok):
            banned_found.append({"char": "hyphenated compound", "context": tok})
    pts = 5 if not banned_found else 2 if len(banned_found) <= 2 else 0
    add("banned_chars", pts, 5, len(banned_found),
        "Remove AI-tell punctuation: em/en dash, ' - ' as dash, semicolon, prose colon, "
        "hyphenated compounds (use the open form or backtick identifiers), ellipsis, "
        "curly quotes, bullets, parenthetical asides, invisible unicode.")

    # 4. Formulaic transitions per 1000 words (8)
    t_count = sum(lower.count(t) for t in TRANSITIONS)
    rate = per_1000(t_count, n_words)
    pts = 8 if t_count == 0 else 5 if rate <= 1 else 2 if rate <= 3 else 0
    add("formulaic_transitions", pts, 8, t_count,
        "Remove 'Moreover/Additionally/In conclusion'-style connectors; just start the sentence.")

    # 5. Hedging boilerplate (5)
    h_count = sum(lower.count(h) for h in HEDGES)
    pts = 5 if h_count == 0 else 2 if h_count == 1 else 0
    add("hedging_boilerplate", pts, 5, h_count,
        "Delete 'it's worth noting'-style hedges; state the thing directly.")

    # 6. AI-favored lexicon per 1000 words (8)
    lex = sum(len(re.findall(r"\b" + re.escape(w) + r"\b", lower)) for w in AI_LEXICON)
    rate = per_1000(lex, n_words)
    pts = 8 if lex == 0 else 4 if rate <= 2 else 0
    add("ai_lexicon", pts, 8, lex,
        "Swap AI-favored words (delve/leverage/seamless/pivotal/...) for plain ones.")

    # 7. Triads 'X, Y, and Z' per 1000 words (6). Mandatory comma before
    # and/or: without it the pattern matches ordinary compound sentences.
    triads = len(re.findall(r", [^,.;:]{2,45}, (?:and|or) ", text))
    rate = per_1000(triads, n_words)
    pts = 6 if rate <= 3 else 3 if rate <= 6 else 0
    add("triad_rate", pts, 6, triads,
        "Break up 'X, Y, and Z' lists: weight one item, fold others into prose, vary syntax.")

    # 8. Paragraph-length variance (5). Variance must come from real short and
    # long multi-sentence paragraphs - a standalone one-sentence paragraph
    # dropped in as a pivot ("My two trajectories split exactly there.") is
    # itself a tell and caps this check instead of earning it.
    pcv = (statistics.pstdev(para_lens) / statistics.mean(para_lens)) if statistics.mean(para_lens) and len(para_lens) > 1 else 0
    one_liners = [
        p.strip() for p in paras
        if len(paras) > 1
        and ((len(re.findall(r"[.!?](?:\s|$)", p.strip())) <= 1 and len(p.split()) <= 15)
             or (len(re.findall(r"[.!?](?:\s|$)", p.strip())) <= 2 and len(p.split()) <= 18))
    ]
    if one_liners:
        pts = min(2, 5 if pcv >= 0.5 else 3 if pcv >= 0.3 else 0)
        add("paragraph_variance_cv", pts, 5, round(pcv, 3),
            "Stub paragraph(s) found (e.g. '" + one_liners[0][:60] +
            "'): merge them into a neighboring paragraph; vary length with real multi-sentence paragraphs instead.")
    else:
        pts = 5 if pcv >= 0.5 else 3 if pcv >= 0.3 else 0
        add("paragraph_variance_cv", pts, 5, round(pcv, 3),
            "Paragraphs too even: shorten one to two or three sentences, let another sprawl - never via a standalone one-liner paragraph.")

    # 9. Self-answered rhetorical questions (4)
    qa = 0
    for i, s in enumerate(sents[:-1]):
        if s.endswith("?"):
            nxt = sents[i + 1]
            if len(nxt.split()) <= 6 or re.match(r"(It |Yes|No|That |The answer)", nxt):
                qa += 1
    pts = 4 if qa == 0 else 0
    add("self_answered_questions", pts, 4, qa,
        "Don't answer your own rhetorical question right after asking it; leave it open or make it a statement.")

    # 10. Bullet-list markers in prose (4)
    bullets = len(re.findall(r"^\s*[-*•]\s+", text, flags=re.M))
    pts = 4 if bullets == 0 else 1
    add("bullet_markers", pts, 4, bullets,
        "Prose answers shouldn't fall back to bullet lists.")

    total = sum(c["points"] for c in checks)
    print(json.dumps({
        "script_score": total, "script_max": 60,
        "words": n_words, "sentences": len(sents), "paragraphs": len(paras),
        "checks": checks,
        "banned_found": banned_found,
        "failed": [c["check"] for c in checks if c["points"] < c["max"]],
    }, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: ai_tells.py <text-file>")
    main(sys.argv[1])
