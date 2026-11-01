"""Build one HTML page from the four conversation-routing documents."""
import html
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pylib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import markdown  # noqa: E402
import refs  # noqa: E402

RFCS = Path(os.environ.get("RFCS_DIR", r"<home>\Codes\ariadne\docs\rfcs"))
HERE = Path(__file__).resolve().parent
# The as-is uses its own check ids (A1, P2, X...), which collide with the series ids: no auto-linking there.
NO_IDS = {"asis"}
TERMS = {}  # glossary of the problem domain, filled in main()

DOCS = [
    ("problem", "conversation-routing-1-problem-domain.md", "Problem domain RFC"),
    ("asis", "conversation-routing-1a-as-is.md", "As-is of v1 and v2"),
    ("market", "conversation-routing-1b-market-study.md", "Market study"),
    ("solution", "conversation-routing-2-solution-domain.md", "Solution domain RFC"),
    ("hla", "conversation-routing-3-hla.md", "High level architecture"),
    ("hld", "conversation-routing-4-hld.md", "High level design"),
]
ANCHOR_OF = {f: key for key, f, _ in DOCS}
ANCHOR_OF["conversation-routing-README.md"] = "series"
ADRS_FILE = "conversation-routing-adrs.md"  # second tab: decision records
ANCHOR_OF[ADRS_FILE] = "adrs"


def slugger(prefix):
    def slug(value, separator):
        s = re.sub(r"[^\w\s-]", "", value).strip().lower()
        return prefix + "-" + re.sub(r"[\s_-]+", "-", s)
    return slug


def redact(text):
    """Public page: drop internal conversation evidence (section, citations, Slack links)."""
    text = re.sub(r"(?ms)^### Evidence\n.*?(?=^#{2,3} )", "", text)
    text = re.sub(r"\s?\[S\d+(?:[, ]+S?\d+)*\]", "", text)
    text = re.sub(r"https://[a-z]+\.slack\.com/\S+", "", text)
    return text


def fix_links(body, key=None):
    def repl(m):
        href, text = m.group(1), m.group(2)
        if href.startswith(("http://", "https://")):
            return m.group(0)
        if href.startswith("#"):
            return f'<a href="#{key}-{href[1:]}">{text}</a>' if key else m.group(0)
        name, _, frag = href.partition("#")
        name = name.split("/")[-1]
        if name in ANCHOR_OF:
            tgt = ANCHOR_OF[name]
            return f'<a href="#{tgt}-{frag}">{text}</a>' if frag else f'<a href="#{tgt}">{text}</a>'
        return f"<code>{text}</code>" if "<code>" not in text else text
    return re.sub(r'<a href="([^"]+)">(.*?)</a>', repl, body)


def fix_mermaid(body):
    return re.sub(
        r'<pre><code class="language-mermaid">(.*?)</code></pre>',
        lambda m: f'<div class="diagram"><pre class="mermaid">{m.group(1)}</pre></div>',
        body,
        flags=re.S,
    )


def wrap_tables(body):
    return body.replace("<table>", '<div class="tablewrap"><table>').replace("</table>", "</table></div>")


def render(key, path, defs, used):
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "sane_lists"],
        extension_configs={"toc": {"slugify": slugger(key), "baselevel": 2, "toc_depth": "3"}},
    )
    text = redact((RFCS / path).read_text(encoding="utf-8"))
    text = refs.link_tags_md(text)
    body = md.convert(text)
    body = wrap_tables(fix_mermaid(fix_links(body, key)))
    if key == "problem":
        body = refs.anchor_terms(body, TERMS)
    if key not in NO_IDS:
        body = refs.link_ids(refs.anchor_defs(body, defs, key), defs, used)
    else:  # only its own AS# constraints are anchors; its check ids stay plain text
        body = re.sub(r"<strong>(AS\d+)\.</strong>", r'<strong><span class="defid" id="def-\1">\1</span>.</strong>', body)
    body = refs.link_terms(body, TERMS)
    toc = [(t["id"], t["name"]) for t in md.toc_tokens[0]["children"]] if md.toc_tokens else []
    return body, toc


def section_readme(defs, used):
    text = (RFCS / "conversation-routing-README.md").read_text(encoding="utf-8")
    keep = []
    for part in re.split(r"(?m)^## ", text)[1:]:
        title = part.splitlines()[0].strip()
        if title in ("Decided on 27/10/2026", "Open questions", "Accepted limits", "MECE check (27/10/2026)", "Review history"):
            keep.append("## " + part)
    md = markdown.Markdown(
        extensions=["tables", "sane_lists", "toc"],
        extension_configs={"toc": {"slugify": slugger("series"), "baselevel": 3}},
    )
    body = wrap_tables(fix_links(md.convert(redact("\n".join(keep)))))
    return refs.link_terms(refs.link_ids(refs.anchor_defs(body, defs, "series"), defs, used), TERMS)


def main():
    shell = (HERE / "shell.html").read_text(encoding="utf-8")
    nav, docs, used = [], [], set()
    sources = [(k, redact((RFCS / f).read_text(encoding="utf-8"))) for k, f, _ in DOCS if k not in NO_IDS]
    sources.append(("series", (RFCS / "conversation-routing-README.md").read_text(encoding="utf-8")))
    defs = refs.collect(sources)
    TERMS.update(refs.collect_terms((RFCS / DOCS[0][1]).read_text(encoding="utf-8")))
    for k, f, _ in DOCS:  # AS# constraints defined in a NO_IDS stage: "1. **AS1.** text"
        if k in NO_IDS:
            for m in re.finditer(r"(?m)^\d+\. \*\*(AS\d+)\.\*\* (.*)$", (RFCS / f).read_text(encoding="utf-8")):
                defs[m.group(1)] = (k, refs.short(m.group(2)))  # the as-is definition wins
    has_adrs = (RFCS / ADRS_FILE).exists()
    if has_adrs:  # ADR-N now resolves to its record in the decisions tab
        for m in re.finditer(r"(?m)^## (ADR-\d+)\b[ .:]*(.*)$", (RFCS / ADRS_FILE).read_text(encoding="utf-8")):
            defs[m.group(1)] = ("adrs", refs.short(m.group(2) or m.group(1)))
    for i, (key, path, label) in enumerate(DOCS, 1):
        body, toc = render(key, path, defs, used)
        sub = "".join(f'<li><a href="#{a}">{html.escape(re.sub("<[^>]+>", "", n))}</a></li>' for a, n in toc)
        nav.append(f'<li><a class="navdoc" href="#{key}">{i}. {label}</a><ul>{sub}</ul></li>')
        docs.append(
            f'<section class="doc" id="{key}"><p class="eyebrow">Stage {i} of {len(DOCS)} · {label}</p>{body}</section>'
        )
    adrs_body, adrs_nav = '<section class="doc" id="adrs"><p>No decision records yet.</p></section>', ""
    if has_adrs:
        adrs_body, adrs_toc = render("adrs", ADRS_FILE, defs, used)
        adrs_body = re.sub(r'<h2 id="([^"]+)">(ADR-\d+)\b', lambda m: f'<h2 id="{m.group(1)}"><span class="defid" id="def-{m.group(2)}">{m.group(2)}</span>', adrs_body)
        adrs_body = re.sub(r"<p>Status:\s*([A-Za-z]+)", r'<p><span class="adr-status">\1</span> Status: \1', adrs_body)
        adrs_body = f'<section class="doc" id="adrs">{adrs_body}</section>'
        adrs_nav = "".join(f'<li><a href="#{a}">{html.escape(re.sub("<[^>]+>", "", n))}</a></li>' for a, n in adrs_toc)
    out = (
        shell.replace("{{ADRS}}", adrs_body).replace("{{ADRNAV}}", adrs_nav)
        .replace("{{NAV}}", "".join(nav))
        .replace("{{DOCS}}", "".join(docs))
        .replace("{{SERIES}}", section_readme(defs, used))
    )
    (HERE / "conversation-routing.html").write_text(out, encoding="utf-8")
    missing = sorted(used - set(defs))
    ids = set(re.findall(r'id="([^"]+)"', out))
    broken = sorted({h for h in re.findall(r'href="#([^"]+)"', out)} - ids)
    print("broken anchors:", broken)
    print(len(out), "defined", len(defs), "referenced", len(used), "missing", missing)


main()
