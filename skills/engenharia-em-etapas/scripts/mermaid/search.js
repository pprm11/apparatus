// Try layout variants per flowchart and keep the one with the best readable scale at a target width.
function variantSrc(src, top, sub, tight) {
  let s = src.replace(/^\s*%%\{init:.*\}%%\s*\n/m, "");
  s = s.replace(/^(\s*(?:flowchart|graph)\s+)(LR|TB|TD|RL|BT)/m, "$1" + top);
  s = s.replace(/^\s*direction\s+(LR|TB|TD|RL|BT)\s*$/gm, "");
  if (sub) s = s.replace(/^(\s*subgraph\b.*)$/gm, "$1\n    direction " + sub);
  if (tight) s = '%%{init: {"flowchart": {"nodeSpacing": 22, "rankSpacing": 30, "padding": 6, "diagramPadding": 4}}}%%\n' + s;
  return s;
}
async function best(W, H) {
  const ds = await (await fetch("diagrams.json")).json();
  const res = [];
  for (const d of ds) {
    if (!/^\s*(flowchart|graph)/.test(d.src)) { res.push({ id: d.f + d.i, skip: true }); continue; }
    let top = null;
    for (const t of ["LR", "TB"]) for (const sub of [null, "TB", "LR"]) {
      const src = variantSrc(d.src, t, sub, true);
      try {
        const out = await mermaid.render("m" + Math.random().toString(36).slice(2), src);
        const vb = out.svg.match(/viewBox="([^"]+)"/)[1].split(" ").map(Number);
        const scale = Math.min(1, W / vb[2]), shownH = vb[3] * scale;
        const score = scale * (shownH > H ? H / shownH : 1);
        if (!top || score > top.score) top = { t, sub, w: Math.round(vb[2]), h: Math.round(vb[3]), scale: +scale.toFixed(2), score: +score.toFixed(2) };
      } catch (e) { }
    }
    res.push({ id: d.f + d.i, ...top });
  }
  return res;
}
