(function () {
  "use strict";
  var doc = document;
  var main = doc.querySelector("main") || doc.body;
  function el(tag, cls, text) { var e = doc.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function copy(text, btn, label) {
    var done = function () { btn.textContent = "Copied"; setTimeout(function () { btn.textContent = label; }, 1400); };
    try { navigator.clipboard.writeText(text).then(done, function () { window.prompt("Copy:", text); }); }
    catch (e) { window.prompt("Copy:", text); }
  }
  function sectionTitle(node) {
    var h = null, n = node;
    while (n && n !== main) {
      var p = n.previousElementSibling;
      while (p) { if (/^H[23]$/.test(p.tagName)) { h = p; break; } p = p.previousElementSibling; }
      if (h) break;
      n = n.parentElement;
    }
    var d = node.closest("section.doc");
    var docName = d ? (d.querySelector(".eyebrow") || {}).textContent || d.id : "Series";
    return { id: h ? h.id : (d ? d.id : ""), text: (h ? h.textContent.replace(/#$/, "").trim() : "") , doc: docName.replace(/^Stage \d+ of \d+ · /, "") };
  }

  // 1. Reading progress
  var bar = el("div"); bar.id = "progress"; doc.body.appendChild(bar);
  function progress() {
    var h = doc.documentElement, max = h.scrollHeight - h.clientHeight;
    bar.style.width = (max > 0 ? (h.scrollTop / max) * 100 : 0) + "%";
  }
  window.addEventListener("scroll", progress, { passive: true });

  // 2. Scroll spy in the contents
  var navLinks = {};
  doc.querySelectorAll("nav.index a[href^='#']").forEach(function (a) { navLinks[a.getAttribute("href").slice(1)] = a; });
  var current = null, heads = Object.keys(navLinks).map(function (id) { return doc.getElementById(id); }).filter(Boolean), ticking = false;
  function spy() {
    ticking = false;
    var line = window.innerHeight * 0.25, best = null;
    for (var k = 0; k < heads.length; k++) { if (heads[k].getBoundingClientRect().top <= line) best = heads[k]; else if (best) break; }
    var a = best ? navLinks[best.id] : null;
    if (a === current) return;
    if (current) { current.classList.remove("active"); current.removeAttribute("aria-current"); }
    current = a;
    if (a) { a.classList.add("active"); a.setAttribute("aria-current", "location"); if (a.scrollIntoView && a.closest("nav.index")) { var n = a.closest("nav.index"), r = a.getBoundingClientRect(), nr = n.getBoundingClientRect(); if (r.top < nr.top || r.bottom > nr.bottom) n.scrollTop += r.top - nr.top - nr.height / 3; } }
  }
  window.addEventListener("scroll", function () { if (!ticking) { ticking = true; requestAnimationFrame(spy); } }, { passive: true });
  spy();

  // 3. Heading permalinks with copy
  main.querySelectorAll("h2[id], h3[id]").forEach(function (h) {
    var b = el("button", "hlink", "#"); b.type = "button";
    b.setAttribute("aria-label", "Copy link to " + h.textContent.trim());
    b.addEventListener("click", function (ev) {
      ev.stopPropagation();
      var url = location.href.split("#")[0] + "#" + h.id;
      copy(url, b, "#");
    });
    h.appendChild(b);
  });

  // 4. Code copy buttons
  main.querySelectorAll("pre:not(.mermaid)").forEach(function (pre) {
    var wrap = el("div", "codewrap"); pre.parentNode.insertBefore(wrap, pre); wrap.appendChild(pre);
    var b = el("button", "codecopy", "Copy"); b.type = "button";
    b.addEventListener("click", function () { copy(pre.innerText, b, "Copy"); });
    wrap.appendChild(b);
  });

  // 5. Backlinks index: every place an ID is referenced
  var uses = {};
  main.querySelectorAll("a.ref[href^='#def-']").forEach(function (a, i) {
    var id = a.getAttribute("href").slice(5);
    if (!a.id) a.id = "use-" + i;
    (uses[id] = uses[id] || []).push(a);
  });

  // 6. Popovers: hover or focus opens, the popover itself is hoverable, Esc closes, tap opens on touch
  var pop = el("div", "pop"); pop.setAttribute("role", "tooltip"); pop.id = "pop"; pop.hidden = true; doc.body.appendChild(pop);
  var openFor = null, closeTimer = null;
  var lastPointer = "mouse";  // set per event: "touch" taps open the popover instead of jumping
  doc.addEventListener("pointerdown", function (ev) { lastPointer = ev.pointerType || "mouse"; }, true);
  function hide() { pop.hidden = true; if (openFor) openFor.removeAttribute("aria-describedby"); openFor = null; }
  function show(a) {
    clearTimeout(closeTimer);
    if (openFor === a) return;
    var tip = a.getAttribute("data-tip") || "";
    var cut = tip.indexOf(" · ");
    pop.innerHTML = "";
    pop.appendChild(el("div", "ph", cut > 0 ? tip.slice(0, cut) : tip));
    if (cut > 0) pop.appendChild(el("div", null, tip.slice(cut + 3)));
    var href = a.getAttribute("href") || a.getAttribute("data-href");
    if (a.classList.contains("ref") && href.indexOf("#def-") === 0) {
      var id = href.slice(5), list = uses[id] || [];
      var pu = el("div", "pu", "Used " + list.length + (list.length === 1 ? " time" : " times") + (list.length ? ": " : ""));
      var seen = {}, n = 0;
      list.forEach(function (u) {
        var s = sectionTitle(u), key = s.doc + "|" + s.text;
        if (seen[key] || n >= 6 || u === a) return; seen[key] = 1; n++;
        var l = el("a", null, s.doc + (s.text ? " › " + s.text : "")); l.href = "#" + u.id;
        if (n > 1) pu.appendChild(doc.createTextNode(" · "));
        pu.appendChild(l);
      });
      pop.appendChild(pu);
    }
    var pa = el("div", "pa");
    var external = a.classList.contains("src");
    var go = el("a", null, external ? (a.classList.contains("live") ? "Open the full as-is report ↗" : "Open the file at this commit ↗") : "Go to definition");
    go.href = href; if (external) { go.target = "_blank"; go.rel = "noopener"; }
    pa.appendChild(go);
    pop.appendChild(pa);
    pop.hidden = false;
    var r = a.getBoundingClientRect();
    var top = window.scrollY + r.bottom + 6, left = window.scrollX + r.left;
    pop.style.top = top + "px"; pop.style.left = "0px";
    var w = pop.offsetWidth, maxLeft = window.scrollX + doc.documentElement.clientWidth - w - 8;
    pop.style.left = Math.max(8, Math.min(left, maxLeft)) + "px";
    if (r.bottom + pop.offsetHeight + 12 > window.innerHeight) pop.style.top = (window.scrollY + r.top - pop.offsetHeight - 6) + "px";
    openFor = a; a.setAttribute("aria-describedby", "pop");
  }
  function laterHide() { clearTimeout(closeTimer); closeTimer = setTimeout(hide, 250); }
  main.addEventListener("pointerover", function (ev) { if (ev.pointerType === "touch") return; var a = ev.target.closest && ev.target.closest("a.ref[data-tip], a.term[data-tip], a.src[data-tip]"); if (a) show(a); });
  main.addEventListener("pointerout", function (ev) { if (ev.pointerType === "touch") return; var a = ev.target.closest && ev.target.closest("a.ref[data-tip], a.term[data-tip], a.src[data-tip]"); if (a) laterHide(); });
  main.addEventListener("focusin", function (ev) { var a = ev.target.closest && ev.target.closest("a.ref[data-tip], a.term[data-tip], a.src[data-tip]"); if (a) show(a); });
  main.addEventListener("focusout", function (ev) { if (!pop.contains(ev.relatedTarget)) laterHide(); });
  pop.addEventListener("mouseenter", function () { clearTimeout(closeTimer); });
  pop.addEventListener("mouseleave", laterHide);
  main.addEventListener("click", function (ev) {
    var a = ev.target.closest && ev.target.closest("a.ref[data-tip], a.term[data-tip], a.src[data-tip]");
    if (a && lastPointer === "touch" && openFor !== a) { ev.preventDefault(); show(a); }
  });
  doc.addEventListener("click", function (ev) { if (!pop.hidden && !pop.contains(ev.target) && !(openFor && openFor.contains(ev.target))) hide(); });

  // 7. Return after a jump
  var back = el("button", null, "↑ Back to where you were"); back.id = "back"; back.type = "button"; doc.body.appendChild(back);
  var returnY = null;
  doc.addEventListener("click", function (ev) {
    var a = ev.target.closest && ev.target.closest("a[href^='#']");
    if (!a || a.closest("nav.index") || a.closest("#search")) return;
    if (a.matches("a.ref, a.term") && lastPointer === "touch" && openFor !== a) return;
    returnY = window.scrollY; back.classList.add("show");
  }, true);
  back.addEventListener("click", function () { if (returnY != null) window.scrollTo(0, returnY); returnY = null; back.classList.remove("show"); hide(); });

  function jump(id) {
    var target = doc.getElementById(id);
    if (!target) return;
    returnY = window.scrollY; back.classList.add("show");
    target.scrollIntoView({ block: "start" });
    try { history.replaceState(null, "", "#" + id); } catch (e) {}
  }

  // 8. Search: / or Ctrl+K; headings, ID definitions and glossary terms
  var box = el("div"); box.id = "search"; box.setAttribute("role", "dialog"); box.setAttribute("aria-label", "Search the series");
  box.innerHTML = '<div class="box"><input type="search" placeholder="Search headings, IDs (R12, ADR-4) and glossary terms" aria-label="Search"><ol role="listbox"></ol><div class="hint">Enter opens the first result · arrows move · Esc closes</div></div>';
  doc.body.appendChild(box);
  var input = box.querySelector("input"), ol = box.querySelector("ol"), index = null, sel = 0, results = [];
  function build() {
    index = [];
    main.querySelectorAll("h2[id], h3[id]").forEach(function (h) {
      var s = sectionTitle(h); index.push({ id: h.id, label: h.textContent.replace(/#$/, "").trim(), where: s.doc, kind: 0 });
    });
    var seenIds = {};
    main.querySelectorAll(".defid[id], .defterm[id]").forEach(function (d) {
      if (seenIds[d.id]) return; seenIds[d.id] = 1;
      var row = d.closest("tr, li") || d.parentElement;
      var txt = (row ? row.textContent : d.textContent).replace(/\s+/g, " ").trim();
      index.push({ id: d.id, label: txt.slice(0, 140), where: sectionTitle(d).doc, kind: 1, key: d.textContent.trim().toLowerCase() });
    });
  }
  function render() {
    ol.innerHTML = "";
    results.slice(0, 40).forEach(function (r, i) {
      var li = el("li"), a = el("a", null, r.label); a.href = "#" + r.id;
      a.setAttribute("role", "option"); a.setAttribute("aria-selected", i === sel ? "true" : "false");
      a.appendChild(el("span", "w", r.where));
      a.addEventListener("click", function (ev) { ev.preventDefault(); closeSearch(); jump(r.id); });
      li.appendChild(a); ol.appendChild(li);
    });
  }
  function query() {
    var q = input.value.trim().toLowerCase(); sel = 0;
    if (!q) { results = []; render(); return; }
    var words = q.split(/\s+/);
    results = index.filter(function (r) { var l = r.label.toLowerCase(); return words.every(function (w) { return l.indexOf(w) >= 0; }); });
    results.sort(function (a, b) {
      var ea = a.key === q ? 0 : 1, eb = b.key === q ? 0 : 1;
      return ea - eb || a.kind - b.kind || a.label.length - b.label.length;
    });
    render();
  }
  function openSearch() { if (!index) build(); box.classList.add("open"); input.value = ""; results = []; render(); input.focus(); }
  function closeSearch() { box.classList.remove("open"); }
  input.addEventListener("input", query);
  input.addEventListener("keydown", function (ev) {
    if (ev.key === "ArrowDown") { sel = Math.min(sel + 1, Math.min(results.length, 40) - 1); render(); ev.preventDefault(); }
    else if (ev.key === "ArrowUp") { sel = Math.max(sel - 1, 0); render(); ev.preventDefault(); }
    else if (ev.key === "Enter" && results[sel]) { closeSearch(); jump(results[sel].id); }
  });
  box.addEventListener("click", function (ev) { if (ev.target === box) closeSearch(); });
  var sb = doc.getElementById("searchbtn"); if (sb) sb.addEventListener("click", openSearch);
  doc.addEventListener("keydown", function (ev) {
    var typing = /^(INPUT|TEXTAREA|SELECT)$/.test((ev.target || {}).tagName || "") || (ev.target && ev.target.isContentEditable);
    if (ev.key === "Escape") { hide(); closeSearch(); return; }
    if ((ev.key === "k" || ev.key === "K") && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); openSearch(); return; }
    if (ev.key === "/" && !typing && !ev.ctrlKey && !ev.metaKey && !ev.altKey) { ev.preventDefault(); openSearch(); }
  });

  // 9. Diagrams: figure bar, full screen with zoom and pan, definitions on nodes, connected edges on hover
  var tipOf = {};
  main.querySelectorAll("a.ref[data-tip][href^='#def-'], a.term[data-tip]").forEach(function (a) {
    var key = a.classList.contains("term") ? a.getAttribute("data-tip").split(" · ")[0] : a.getAttribute("href").slice(5);
    if (!tipOf[key]) tipOf[key] = { tip: a.getAttribute("data-tip"), href: a.getAttribute("href") };
  });
  var idWord = /(?:^|[^\w-])(ADR-\d{1,2}|BR\d+|QS\d+|AC\d+|AS\d+|[RPGNAQLICK]\d+)(?![\w-])/;
  var termNames = Object.keys(tipOf).filter(function (k) { return !/^(ADR-|BR|QS|AC|AS|[RPGNAQLICK])\d/.test(k); }).sort(function (a, b) { return b.length - a.length; });
  var termRx = termNames.map(function (k) { return new RegExp("(^|\\W)" + k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "s?(\\W|$)"); });
  var figN = 0, userMoved = false;
  ["wheel", "touchstart", "keydown", "mousedown"].forEach(function (e) { window.addEventListener(e, function () { userMoved = true; }, { passive: true, once: true }); });

  function nodeLabel(g) { return (g.textContent || "").replace(/\s+/g, " ").trim(); }
  function enhance(div) {
    var svg = div.querySelector("svg");
    if (!svg || div.getAttribute("data-enhanced")) return;
    div.setAttribute("data-enhanced", "1");
    figN++;
    var n = figN;
    if (!div.id) div.id = "figure-" + n;
    var bar = el("div", "figbar");
    var cap = el("a", "figno", "Figure " + n); cap.href = "#" + div.id;
    var exp = el("button", "figbtn", "⤢ Expand"); exp.type = "button"; exp.setAttribute("aria-label", "Open figure " + n + " full screen with zoom");
    var lnk = el("button", "figbtn", "Copy link"); lnk.type = "button";
    lnk.addEventListener("click", function () { copy(location.href.split("#")[0] + "#" + div.id, lnk, "Copy link"); });
    exp.addEventListener("click", function () { openViewer(svg, "Figure " + n); });
    svg.addEventListener("dblclick", function () { openViewer(svg, "Figure " + n); });
    bar.appendChild(cap); bar.appendChild(exp); bar.appendChild(lnk);
    div.insertBefore(bar, div.firstChild);
    svg.querySelectorAll("g.node, g.actor, g.stateGroup, g.statediagram-state").forEach(function (g) {
      var txt = nodeLabel(g), hit = null, m = txt.match(idWord);
      if (m && tipOf[m[1]]) hit = tipOf[m[1]];
      if (!hit) for (var k = 0; k < termRx.length; k++) { if (termRx[k].test(txt)) { hit = tipOf[termNames[k]]; break; } }
      var name = (g.id || "").match(/^flowchart-(.+)-\d+$/);
      if (hit) {
        g.setAttribute("data-tip", hit.tip); g.setAttribute("data-href", hit.href);
        g.setAttribute("tabindex", "0"); g.classList.add("hasdef");
        g.addEventListener("click", function () { hide(); jump(hit.href.slice(1)); });
        g.addEventListener("keydown", function (ev) { if (ev.key === "Enter") { hide(); jump(hit.href.slice(1)); } });
        g.addEventListener("focus", function () { show(g); });
      }
      g.addEventListener("pointerenter", function (ev) {
        if (hit && ev.pointerType !== "touch") show(g);
        if (name) {
          svg.classList.add("dim"); g.classList.add("hi");
          var esc = name[1].replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
          var rx = new RegExp("^L[-_]" + esc + "[-_]|[-_]" + esc + "[-_]\\d+$");
          svg.querySelectorAll("path").forEach(function (p) { var pid = p.id || p.getAttribute("data-id") || ""; if (pid.charAt(0) === "L" && rx.test(pid)) p.classList.add("hi"); });
        }
      });
      g.addEventListener("pointerleave", function () {
        if (hit) laterHide();
        svg.classList.remove("dim"); svg.querySelectorAll(".hi").forEach(function (h) { h.classList.remove("hi"); });
      });
    });
  }
  function enhanceAll() {
    main.querySelectorAll(".diagram").forEach(enhance);
    if (!userMoved && location.hash) { var t0 = doc.getElementById(decodeURIComponent(location.hash.slice(1))); if (t0) t0.scrollIntoView({ block: "start" }); }
  }
  var mo = new MutationObserver(function () { clearTimeout(mo.t); mo.t = setTimeout(enhanceAll, 300); });
  mo.observe(main, { childList: true, subtree: true });
  window.addEventListener("load", function () { setTimeout(enhanceAll, 600); });

  // Full screen viewer: wheel or buttons zoom, drag pans, Esc closes
  var viewer = el("div"); viewer.id = "viewer"; viewer.setAttribute("role", "dialog"); viewer.setAttribute("aria-modal", "true");
  viewer.innerHTML = '<div class="vbar"><span class="vt"></span><span class="vh">wheel zooms, drag pans</span><button type="button" data-z="1.25">Zoom in</button><button type="button" data-z="0.8">Zoom out</button><button type="button" data-z="0">Fit</button><button type="button" data-close="1">Close (Esc)</button></div><div class="vstage"></div>';
  doc.body.appendChild(viewer);
  var stage = viewer.querySelector(".vstage"), vs = { s: 1, x: 0, y: 0 }, inner = null, lastFocus = null;
  function apply() { if (inner) inner.style.transform = "translate(" + vs.x + "px," + vs.y + "px) scale(" + vs.s + ")"; }
  function fit() {
    if (!inner) return;
    var r = stage.getBoundingClientRect(), c = inner.firstChild, w = c.width.baseVal.value || 800, h = c.height.baseVal.value || 600;
    vs.s = Math.min(r.width / w, r.height / h) * 0.95; vs.x = (r.width - w * vs.s) / 2; vs.y = (r.height - h * vs.s) / 2; apply();
  }
  function openViewer(svg, title) {
    lastFocus = doc.activeElement;
    stage.innerHTML = ""; inner = el("div", "vinner");
    var c = svg.cloneNode(true); c.removeAttribute("style"); c.classList.remove("dim");
    var vb = (svg.getAttribute("viewBox") || "").split(/\s+/).map(Number), box = svg.getBoundingClientRect();
    c.setAttribute("width", vb.length === 4 ? vb[2] : box.width); c.setAttribute("height", vb.length === 4 ? vb[3] : box.height);
    inner.appendChild(c); stage.appendChild(inner);
    viewer.querySelector(".vt").textContent = title; viewer.classList.add("open"); doc.body.style.overflow = "hidden";
    requestAnimationFrame(fit); viewer.querySelector("[data-close]").focus();
  }
  function closeViewer() { viewer.classList.remove("open"); stage.innerHTML = ""; inner = null; doc.body.style.overflow = ""; if (lastFocus && lastFocus.focus) lastFocus.focus(); }
  viewer.addEventListener("click", function (ev) {
    var b = ev.target.closest("button"); if (!b) return;
    if (b.hasAttribute("data-close")) return closeViewer();
    var z = Number(b.getAttribute("data-z")); if (!z) return fit();
    var r = stage.getBoundingClientRect(), cx = r.width / 2, cy = r.height / 2;
    vs.x = cx - (cx - vs.x) * z; vs.y = cy - (cy - vs.y) * z; vs.s *= z; apply();
  });
  stage.addEventListener("wheel", function (ev) {
    ev.preventDefault();
    var r = stage.getBoundingClientRect(), cx = ev.clientX - r.left, cy = ev.clientY - r.top, z = ev.deltaY < 0 ? 1.15 : 1 / 1.15;
    vs.x = cx - (cx - vs.x) * z; vs.y = cy - (cy - vs.y) * z; vs.s *= z; apply();
  }, { passive: false });
  var drag = null;
  stage.addEventListener("pointerdown", function (ev) { drag = { x: ev.clientX - vs.x, y: ev.clientY - vs.y }; stage.setPointerCapture(ev.pointerId); stage.style.cursor = "grabbing"; });
  stage.addEventListener("pointermove", function (ev) { if (!drag) return; vs.x = ev.clientX - drag.x; vs.y = ev.clientY - drag.y; apply(); });
  stage.addEventListener("pointerup", function () { drag = null; stage.style.cursor = ""; });
  doc.addEventListener("keydown", function (ev) { if (ev.key === "Escape" && viewer.classList.contains("open")) closeViewer(); });

  // 10. Figure captions, small-text hint and a figure index in the contents
  function captionOf(div) {
    var p = div.previousElementSibling;
    var s = p && p.querySelector && p.querySelector("strong");
    return s && p.textContent.indexOf(s.textContent) === 0 ? s.textContent.replace(/[.:]\s*$/, "").replace(/^Figure:\s*/, "") : "";
  }
  var figList = null;
  function figureIndex() {
    var nav = doc.querySelector("nav.index > ul");
    if (!nav) return;
    if (!figList) {
      var li = el("li"), a = el("a", "navdoc", "Figures"); a.href = "#";
      a.addEventListener("click", function (ev) { ev.preventDefault(); figList.hidden = !figList.hidden; });
      figList = el("ul"); figList.hidden = true; li.appendChild(a); li.appendChild(figList); nav.appendChild(li);
    }
    figList.innerHTML = "";
    main.querySelectorAll(".diagram[data-enhanced]").forEach(function (div) {
      var no = div.querySelector(".figno"), it = el("li"), a = el("a", null, (no ? no.textContent : "Figure") + (div.getAttribute("data-caption") ? " · " + div.getAttribute("data-caption") : ""));
      a.href = "#" + div.id; it.appendChild(a); figList.appendChild(it);
    });
  }
  var baseEnhance = enhance;
  enhance = function (div) {
    var fresh = !div.getAttribute("data-enhanced");
    baseEnhance(div);
    if (!fresh || !div.getAttribute("data-enhanced")) return;
    var cap = captionOf(div), no = div.querySelector(".figno");
    if (cap) { div.setAttribute("data-caption", cap); if (no) no.textContent += " · " + cap; }
    var svg = div.querySelector("svg"), vb = (svg.getAttribute("viewBox") || "").split(/\s+/).map(Number);
    if (vb.length === 4 && svg.getBoundingClientRect().width / vb[2] < 0.65) {
      var hint = el("button", "figbtn small", "Text is small: expand to read"); hint.type = "button";
      hint.addEventListener("click", function () { openViewer(svg, no ? no.textContent : "Figure"); });
      div.querySelector(".figbar").insertBefore(hint, div.querySelector(".figbar .figbtn"));
    }
  };
  var baseAll = enhanceAll;
  enhanceAll = function () { baseAll(); figureIndex(); };

  // 11. Filter box inside the contents
  var navEl = doc.querySelector("nav.index");
  if (navEl) {
    var f = el("input", "navfilter"); f.type = "search"; f.placeholder = "Filter contents"; f.setAttribute("aria-label", "Filter contents");
    var sbtn = doc.getElementById("searchbtn");
    navEl.insertBefore(f, sbtn ? sbtn.nextSibling : navEl.firstChild);
    f.addEventListener("input", function () {
      var q = f.value.trim().toLowerCase();
      navEl.querySelectorAll("ul li").forEach(function (li) {
        var own = li.querySelector("a"), txt = own ? own.textContent.toLowerCase() : "";
        var childHit = Array.prototype.some.call(li.querySelectorAll("li a"), function (a) { return a.textContent.toLowerCase().indexOf(q) >= 0; });
        li.style.display = !q || txt.indexOf(q) >= 0 || childHit ? "" : "none";
      });
    });
  }

  // 12. Tabs: Series and Decisions (ADRs); any link or search result inside a hidden tab opens that tab first
  var tabs = Array.prototype.slice.call(doc.querySelectorAll('.tabs [role="tab"]'));
  function activate(tab) {
    tabs.forEach(function (t) {
      var on = t === tab, panel = doc.getElementById(t.getAttribute("aria-controls"));
      t.setAttribute("aria-selected", on ? "true" : "false"); t.tabIndex = on ? 0 : -1;
      if (panel) panel.hidden = !on;
    });
  }
  function reveal(id) {
    var target = id && doc.getElementById(id);
    if (!target) return null;
    var panel = target.closest('[role="tabpanel"]');
    if (panel && panel.hidden) { var t = doc.getElementById(panel.getAttribute("aria-labelledby")); if (t) activate(t); }
    else if (!panel && target.closest("nav.index") === null) { /* outside panels: nothing to do */ }
    return target;
  }
  tabs.forEach(function (t, i) {
    t.addEventListener("click", function () { activate(t); window.scrollTo(0, 0); });
    t.addEventListener("keydown", function (ev) {
      if (ev.key === "ArrowRight" || ev.key === "ArrowLeft") { var n = tabs[(i + (ev.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length]; activate(n); n.focus(); ev.preventDefault(); }
    });
  });
  var baseJump = jump;
  jump = function (id) { reveal(id); baseJump(id); };
  doc.addEventListener("click", function (ev) {
    var a = ev.target.closest && ev.target.closest("a[href^='#']");
    if (!a) return;
    var id = decodeURIComponent(a.getAttribute("href").slice(1));
    var target = doc.getElementById(id);
    if (target && target.closest('[role="tabpanel"]') && target.closest('[role="tabpanel"]').hidden) {
      ev.preventDefault(); reveal(id); target.scrollIntoView({ block: "start" });
      try { history.replaceState(null, "", "#" + id); } catch (e) {}
    }
  }, true);
  window.addEventListener("hashchange", function () { var t = reveal(decodeURIComponent(location.hash.slice(1))); if (t) t.scrollIntoView({ block: "start" }); });
  if (location.hash) reveal(decodeURIComponent(location.hash.slice(1)));
})();
