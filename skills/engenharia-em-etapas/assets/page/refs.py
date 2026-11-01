"""Clickable IDs with hover/focus definitions, acronym expansions, and a broken-reference report."""
import html as H
import re

ID = r"(?:ADR-\d{1,2}(?!\d)|BR\d+|QS\d+|AC\d+|AS\d+|[RPGNAQLICK]\d+)"
ID_RE = re.compile(r"(?<![\w\[#/.-])(" + ID + r")(?![\w-])(?! (?:context|container|model|deployment|style|n\b|\d))")
DEF_LI = re.compile(r"^- (" + ID + r")\.\s+(.*)$")
DEF_TR = re.compile(r"^\| (" + ID + r") \| ([^|]+)\|")

ACRONYMS = {
    "RFC": "Request for comments", "HLA": "High level architecture", "HLD": "High level design",
    "ADR": "Architecture decision record", "TTL": "Time to live", "EMF": "Embedded Metric Format (CloudWatch)",
    "PITR": "Point-in-time recovery", "IAM": "AWS Identity and Access Management", "OTLP": "OpenTelemetry protocol",
    "OIDC": "OpenID Connect", "SNS": "Amazon Simple Notification Service", "HML": "Homologation (staging) environment",
    "PRD": "Production environment", "LGPD": "Lei Geral de Proteção de Dados (Brazil's data protection law)",
    "EARS": "Easy Approach to Requirements Syntax", "BCP": "Best Current Practice (IETF)", "HMAC": "Hash-based message authentication code",
    "ALB": "Application Load Balancer", "LCU": "Load balancer capacity unit", "NAT": "Network address translation",
    "BRT": "Brasília time", "SSO": "Single sign-on", "CLI": "Command line interface", "IaC": "Infrastructure as code",
    "KMS": "AWS Key Management Service", "ACM": "AWS Certificate Manager", "DDD": "Domain-driven design",
    "WCU": "Write capacity unit", "RCU": "Read capacity unit", "CD": "Continuous delivery", "CI": "Continuous integration",
}
AC_RE = re.compile(r"(?<![\w-])(" + "|".join(sorted(ACRONYMS, key=len, reverse=True)) + r")(?![\w-])")


def short(text, n=110):
    t = re.sub(r"`|\*\*|\[|\]\([^)]*\)", "", text).strip()
    t = re.split(r"(?<=[a-z0-9)])\. ", t, maxsplit=1)[0] if len(t) > n else t
    return (t[: n - 1] + "…") if len(t) > n else t


def collect(docs):
    """docs: list of (key, markdown). Returns {id: (key, short)} with the first definition winning."""
    defs = {}
    for key, md in docs:
        for line in md.splitlines():
            m = DEF_LI.match(line) or DEF_TR.match(line)
            if m and m.group(1) not in defs:
                defs[m.group(1)] = (key, short(m.group(2)))
    return defs


def anchor_defs(body, defs, key):
    for i, (k, _) in defs.items():
        if k != key:
            continue
        pat = re.compile(r"(<li>(?:\s*<p>)?\s*)(" + re.escape(i) + r")(\.)|(<td>)(" + re.escape(i) + r")(</td>)")
        body = pat.sub(lambda m: (m.group(1) + f'<span class="defid" id="def-{i}">{i}</span>' + m.group(3)) if m.group(1) is not None
                       else (m.group(4) + f'<span class="defid" id="def-{i}">{i}</span>' + m.group(6)), body, count=1)
    return body


SKIP = {"code", "pre", "a", "h1", "h2", "h3", "h4", "abbr", "script", "style", "title"}


def link_ids(html_text, defs, used):
    out, stack = [], []
    for part in re.split(r"(<[^>]+>)", html_text):
        if part.startswith("<"):
            m = re.match(r"<(/?)(\w+)", part)
            if m:
                tag = m.group(2).lower()
                if tag in SKIP:
                    if m.group(1):
                        if tag in stack:
                            stack.remove(tag)
                    elif not part.endswith("/>"):
                        stack.append(tag)
                if 'class="defid"' in part:
                    stack.append("span-def")
                elif m.group(1) and tag == "span" and "span-def" in stack:
                    stack.remove("span-def")
            out.append(part)
            continue
        if stack:
            out.append(part)
            continue

        def rid(m):
            i = m.group(1)
            used.add(i)
            if i not in defs:
                return f'<span class="ref missing" title="No definition found">{i}</span>'
            tip = H.escape(f"{i} · {defs[i][1]}", quote=True)
            return f'<a class="ref" href="#def-{i}" data-tip="{tip}" aria-label="{tip}">{i}</a>'

        part = AC_RE.sub(lambda m: f'<abbr title="{H.escape(ACRONYMS[m.group(1)])}">{m.group(1)}</abbr>', part)
        part = ID_RE.sub(rid, part)
        out.append(part)
    return "".join(out)


# Glossary terms: hover shows the definition, click goes to the glossary row.
def term_slug(term):
    return "term-" + re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")


def collect_terms(md):
    """Rows of the first table under '### Glossary': {term: short definition}."""
    m = re.search(r"(?ms)^### Glossary\n(.*?)(?=^#{2,3} )", md)
    terms = {}
    if not m:
        return terms
    for line in m.group(1).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and line.startswith("| ") and cells[0] not in ("Term", "") and not set(cells[0]) <= set("-: "):
            terms[cells[0]] = short(cells[1], 160)
    return terms


def anchor_terms(body, terms):
    for t in terms:
        body = body.replace(f"<td>{t}</td>", f'<td><span class="defterm" id="{term_slug(t)}">{t}</span></td>', 1)
    return body


def link_terms(html_text, terms):
    if not terms:
        return html_text
    names = sorted(terms, key=len, reverse=True)
    rx = re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in names) + r")(s|es)?(?![\w-])")
    out, stack, seen = [], [], set()
    for part in re.split(r"(<[^>]+>)", html_text):
        if part.startswith("<"):
            m = re.match(r"<(/?)(\w+)", part)
            if m:
                tag = m.group(2).lower()
                if not m.group(1) and tag in ("p", "li", "td", "th", "dd"):
                    seen = set()  # first occurrence per block gets the hover
                if tag in SKIP:
                    if m.group(1):
                        if tag in stack:
                            stack.remove(tag)
                    elif not part.endswith("/>"):
                        stack.append(tag)
                if 'class="defterm"' in part:
                    stack.append("span-term")
                elif m.group(1) and tag == "span" and "span-term" in stack:
                    stack.remove("span-term")
            out.append(part)
            continue
        if stack:
            out.append(part)
            continue

        def rterm(mm):
            t = mm.group(1)
            if t in seen:
                return mm.group(0)
            seen.add(t)
            tip = H.escape(f"{t} · {terms[t]}", quote=True)
            return f'<a class="term" href="#{term_slug(t)}" data-tip="{tip}" aria-label="{tip}">{mm.group(0)}</a>'

        out.append(rx.sub(rterm, part))
    return "".join(out)


# As-is evidence tags: [FILES prefix:path:lines ...] become links to the line at the prefix's commit;
# [LIVE ids] become chips that explain the check and open the full as-is report.
PREFIXES = {
    "v2": ("https://github.com/acme-org/ariadne/blob/9518005ad722d37784bbf8ff63d22f7ed50e421b/", "github", "ariadne hml 9518005"),
    "v2main": ("https://github.com/acme-org/ariadne/blob/8021f20ee8ce01e596cec60fe081f1d5f6fff17a/", "github", "ariadne main 8021f20"),
    "v1": ("https://git.example.com/acme/ariadne-legacy/src/commit/7171e496f958fe4bec9d0e700769cafc2d4f6b1c/", "gitea", "ariadne-legacy homolog 7171e49"),
    "v1main": ("https://git.example.com/acme/ariadne-legacy/src/commit/3dd8c6d6bf5ddfc1af03526c2b24631d1befcaf1/", "gitea", "ariadne-legacy main 3dd8c6d"),
    "deploy": ("https://git.example.com/acme/deploy/src/commit/8f85553e711433daa42b1bc19a9c47d9e0cd23df/", "gitea", "acme/deploy dev 8f85553"),
    "deploymain": ("https://git.example.com/acme/deploy/src/commit/fd6a443513635a416925e1ece48126b3ea1ad916/", "gitea", "acme/deploy main fd6a443"),
}
ASIS_REPORT = "https://claude.ai/artifact/KLsNmJ5ZKLcBy446ZVBdSE"
TOKEN = re.compile(r"([a-z0-9]+):([A-Za-z0-9_.\-/]+)(?::([\d][\d,\-]*))?")


def _file_link(prefix, path, lines):
    base, host, label = PREFIXES[prefix]
    url = base + path
    if path.endswith((".md", ".mdx")) and host == "github":
        url += "?plain=1"
    first = (lines or "").rstrip(",").split(",")[0]
    if first:
        lo, _, hi = first.partition("-")
        url += f"#L{lo}" + (f"-L{hi}" if hi and host == "github" else (f"-L{hi}" if hi else ""))
    text = f"{prefix}:{path}" + (f":{lines.rstrip(',')}" if lines else "")
    tip = H.escape(f"{text} · file at {label}; opens the cited lines", quote=True)
    return f'<a class="src" href="{H.escape(url, quote=True)}" target="_blank" rel="noopener" data-tip="{tip}">{H.escape(text)}</a>'


def _files_tag(m):
    inner = m.group(1)
    out, pos = [], 0
    for t in TOKEN.finditer(inner):
        if t.group(1) not in PREFIXES:
            continue
        out.append(H.escape(inner[pos:t.start()]))
        out.append(_file_link(t.group(1), t.group(2), t.group(3)))
        pos = t.end()
    if not out:
        return m.group(0)
    out.append(H.escape(inner[pos:]))
    return '<span class="evtag">[FILES ' + "".join(out) + "]</span>"


def _live_tag(m):
    ids = m.group(1)
    tip = H.escape(f"LIVE {ids} · read-only check run on 26/10/2026 (RCn on 27/10); command and output are in the full as-is report, tab Full detail, check index", quote=True)
    return f'<a class="src live" href="{ASIS_REPORT}" target="_blank" rel="noopener" data-tip="{tip}">[LIVE {H.escape(ids)}]</a>'


FILES_RE = re.compile(r"\[FILES ([^\]]+)\]")
LIVE_RE = re.compile(r"\[LIVE ([^\]]+)\]")


def link_tags(html_text):
    out, stack = [], []
    for part in re.split(r"(<[^>]+>)", html_text):
        if part.startswith("<"):
            m = re.match(r"<(/?)(\w+)", part)
            if m and m.group(2).lower() in ("code", "pre", "a", "script", "style"):
                if m.group(1):
                    if m.group(2).lower() in stack:
                        stack.remove(m.group(2).lower())
                elif not part.endswith("/>"):
                    stack.append(m.group(2).lower())
            out.append(part)
            continue
        if stack:
            out.append(part)
            continue
        part = FILES_RE.sub(lambda mm: _files_tag(mm) if "prefix:path" not in mm.group(1) else mm.group(0), part)
        part = LIVE_RE.sub(lambda mm: _live_tag(mm) if mm.group(1).strip() != "id" else mm.group(0), part)
        out.append(part)
    return "".join(out)


def link_tags_md(md):
    """Same as link_tags, applied to Markdown before rendering, so paths like __init__.py survive."""
    parts = re.split(r"(```.*?```|`[^`\n]+`)", md, flags=re.S)
    return "".join(p if p.startswith("`") else link_tags(p) for p in parts)
