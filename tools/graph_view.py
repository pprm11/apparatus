#!/usr/bin/env python3
"""Render the vault's link graph as a standalone HTML page in the style of Obsidian's Graph view.

Usage:
  python -I tools/graph_view.py [--out .work/graph.html]
  python -I tools/graph_view.py --check      # unresolved links + orphans, exit 1 if any

Nodes are the Markdown notes of the vault (same filters as `.obsidian/app.json`); edges are
`[[wikilinks]]` and relative `[text](file.md)` links. Colors follow the groups in `.obsidian/graph.json`
order (first match wins). Node size grows with degree. The page loads d3 from jsDelivr.
"""
import argparse
import glob
import json
import os
import re

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
IGNORED = (".work/", "index/", "tests/", "evals/", ".git/", ".obsidian/", "runs/")
WIKILINK = re.compile(r"\[\[([^\]|#]+)")
MDLINK = re.compile(r"\]\(([^)#\s]+\.md)\)")
# Links inside code are examples, not edges (Obsidian ignores them too).
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)
GROUPS = [
    ("memory/", "memory", "#8e44df"),
    ("memory/", "memory (other)", "#cccccc"),
    ("skills/", "skills", "#7ccb22"),
    ("rules/", "rules", "#e95444"),
    ("global/", "rules", "#e95444"),
    ("harness/", "rules", "#e95444"),
    ("pdi/", "pdi", "#e8bf4f"),
    ("reports/", "reports/plans", "#c1c1e2"),
    ("plans/", "reports/plans", "#c1c1e2"),
    ("prompts/", "reports/plans", "#c1c1e2"),
]


UNRESOLVED: list[str] = []
# Notes that may stay without links: generated catalogs, logs and plan-mode drafts.
ORPHAN_OK = {"INDEX.md", "lint-report.md", "log.md", "plans/fa-a-o-plano-primeiro-fuzzy-sunbeam.md", "plans/scalable-crafting-parasol.md"}
# Double-bracket text that is not a link: TOML tables quoted in the ummon skill.
NOT_LINKS = {"artifacts", "verifier.collect"}


def group_of(rel: str) -> tuple[str, str]:
    for prefix, name, color in GROUPS:
        if rel.startswith(prefix):
            return name, color
    return "root", "#5b8def"


def collect() -> tuple[list[dict], list[dict]]:
    files = sorted(
        os.path.relpath(p, REPO).replace(os.sep, "/")
        for p in glob.glob(os.path.join(REPO, "**", "*.md"), recursive=True)
    )
    files = [f for f in files if not f.startswith(IGNORED)]
    by_stem: dict[str, str] = {}
    for f in files:
        by_stem.setdefault(os.path.splitext(os.path.basename(f))[0].lower(), f)

    def resolve(target: str) -> str | None:
        # Obsidian resolves "folder/note" by path suffix, so [[executar-ondas/SKILL]] finds the skill.
        target = target.strip().lower().removesuffix(".md")
        if "/" not in target:
            return by_stem.get(target)
        return next((f for f in files if f.lower().removesuffix(".md").endswith(target)), None)

    edges: set[tuple[str, str]] = set()
    for f in files:
        if f == "lint-report.md":  # quotes the broken links it reports; scanning it would count them twice
            continue
        text = CODE.sub("", open(os.path.join(REPO, f), encoding="utf-8", errors="replace").read())
        for target in WIKILINK.findall(text):
            dst = resolve(target)
            if not dst and target.strip() not in NOT_LINKS:
                UNRESOLVED.append(f"{f} -> [[{target.strip()}]]")
            if dst and dst != f:
                edges.add(tuple(sorted((f, dst))))
        for target in MDLINK.findall(text):
            dst = os.path.normpath(os.path.join(os.path.dirname(f), target)).replace(os.sep, "/")
            dst = dst if dst in files else by_stem.get(os.path.splitext(os.path.basename(target))[0].lower())
            if dst and dst != f:
                edges.add(tuple(sorted((f, dst))))
    degree = {f: 0 for f in files}
    for a, b in edges:
        degree[a] += 1
        degree[b] += 1
    nodes = []
    for f in files:
        name, color = group_of(f)
        stem = os.path.splitext(os.path.basename(f))[0]
        label = os.path.basename(os.path.dirname(f)) if stem == "SKILL" else stem
        nodes.append({"id": f, "label": label, "group": name,
                      "color": color, "degree": degree[f]})
    return nodes, [{"source": a, "target": b} for a, b in sorted(edges)]


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Context Graph</title>
<style>html,body{margin:0;height:100%;background:#1e1e1e;color:#ddd;font:12px system-ui}
#legend{position:fixed;top:12px;left:12px;background:#262626cc;padding:8px 10px;border-radius:6px}
#legend div{margin:2px 0}#legend span{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}
#stats{position:fixed;bottom:12px;left:12px;opacity:.7}text{fill:#bbb;pointer-events:none}</style></head>
<body><div id="legend"></div><div id="stats"></div><svg id="g" width="100%" height="100%"></svg>
<script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"></script><script>
const data = __DATA__;
const svg = d3.select("#g"), root = svg.append("g");
// Lay out around (0,0) and fit to the viewport when it settles: the window can report 0x0 at load.
const zoom = d3.zoom().scaleExtent([.1, 6]).on("zoom", e => root.attr("transform", e.transform));
svg.call(zoom);
function fit() {
  const b = root.node().getBBox(), w = svg.node().clientWidth, h = svg.node().clientHeight;
  if (!b.width || !w) return;
  const k = Math.min(w / b.width, h / b.height) * .92;
  svg.call(zoom.transform, d3.zoomIdentity.translate(w / 2 - k * (b.x + b.width / 2), h / 2 - k * (b.y + b.height / 2)).scale(k));
}
const r = d => 3 + Math.sqrt(d.degree) * 2.2;
const sim = d3.forceSimulation(data.nodes)
  .force("link", d3.forceLink(data.links).id(d => d.id).distance(40).strength(.7))
  .force("charge", d3.forceManyBody().strength(-60))
  .force("center", d3.forceCenter(0, 0))
  .force("x", d3.forceX(0).strength(.04)).force("y", d3.forceY(0).strength(.04))
  .force("collide", d3.forceCollide(d => r(d) + 1.5));
const link = root.append("g").attr("stroke", "#555").attr("stroke-opacity", .6)
  .selectAll("line").data(data.links).join("line").attr("stroke-width", .7);
const node = root.append("g").selectAll("circle").data(data.nodes).join("circle")
  .attr("r", r).attr("fill", d => d.color)
  .call(d3.drag().on("start", (e, d) => { if (!e.active) sim.alphaTarget(.3).restart(); d.fx = d.x; d.fy = d.y; })
    .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
    .on("end", (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = d.fy = null; }));
node.append("title").text(d => d.id + " (" + d.degree + " links)");
const label = root.append("g").selectAll("text").data(data.nodes.filter(d => d.degree >= 10)).join("text")
  .text(d => d.label).attr("font-size", 9).attr("dy", d => -r(d) - 3).attr("text-anchor", "middle");
sim.on("tick", () => {
  link.attr("x1", d => d.source.x).attr("y1", d => d.source.y).attr("x2", d => d.target.x).attr("y2", d => d.target.y);
  node.attr("cx", d => d.x).attr("cy", d => d.y); label.attr("x", d => d.x).attr("y", d => d.y);
});
// Settle the layout up front (rAF stalls in background tabs), draw once, then fit.
sim.stop();
for (let i = 0; i < 400; i++) sim.tick();
sim.on("tick")();
fit();
addEventListener("resize", fit);
const groups = [...new Map(data.nodes.map(n => [n.group, n.color])).entries()];
d3.select("#legend").selectAll("div").data(groups).join("div")
  .html(([g, c]) => `<span style="background:${c}"></span>${g} (${data.nodes.filter(n => n.group === g).length})`);
const orphans = data.nodes.filter(n => !n.degree).length;
d3.select("#stats").text(`${data.nodes.length} notes · ${data.links.length} links · ${orphans} orphans`);
</script></body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(REPO, ".work", "graph.html"))
    ap.add_argument("--check", action="store_true",
                    help="list unresolved links and orphan notes; exit 1 if there are any")
    args = ap.parse_args()
    nodes, links = collect()
    if args.check:
        orphan_ids = [n["id"] for n in nodes if not n["degree"] and n["id"] not in ORPHAN_OK]
        print("\n".join([f"unresolved: {u}" for u in UNRESOLVED] + [f"orphan: {o}" for o in orphan_ids]))
        print(f"{len(UNRESOLVED)} unresolved, {len(orphan_ids)} orphans")
        raise SystemExit(1 if UNRESOLVED or orphan_ids else 0)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(PAGE.replace("__DATA__", json.dumps({"nodes": nodes, "links": links})))
    orphans = sum(1 for n in nodes if not n["degree"])
    print(f"{len(nodes)} notes, {len(links)} links, {orphans} orphans -> {args.out}")


if __name__ == "__main__":
    main()
