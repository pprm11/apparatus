# Front-end research 2: API-doc viewer patterns and diagram UX for the design-series page

Access date for every source: 28/10/2026. Builds on frontend-research.md (not repeated: scroll spy, search, popovers, back-after-jump, permalinks, backlinks, print, copy, zoom basics).
Cost scale for vanilla JS on a static page: small = under about 60 lines, medium = 60 to 250, large = needs new markup contract or authoring step.
Claims tagged [unverified] come from my own knowledge of mermaid/library internals and were not on a fetched page. Check them against the mermaid version the page ships before coding.

## Method notes and gaps

- Fetched with WebFetch/WebSearch. The fetch tool summarizes pages; I quote option names only when they came back from the page.
- Not obtained: Scalar docs (domain redirected to a dashboard with no content), RapiDoc attribute reference (rapidocweb.com redirected to an unrelated domain, rapidocweb.github.io 404; I did not follow the redirect), Bump.sh layout (only header search, dark toggle, heading anchors, changelog and "On this page" confirmed), Structurizr base docs page (404; I used its viewer page and search snippets), nngroup diagrams article (404), IcePanel hover/legend (not in docs found).
- Evidence on diagram readability is thin. There is no fetched study that tests legends or font size. Where I recommend a number (for example minimum rendered text size) it is my heuristic and is marked so.

## Part 1 digest: what the API viewers do that transfers

| Pattern | Who | Source (fetched) | Transfer to a design doc |
|---|---|---|---|
| Three columns: nav, prose, sticky examples | Redoc CE ("three-panel layout"), Stoplight Elements (`sidebar` layout = three columns with resizable sidebar) | redocly.com/docs/redoc/ ; github.com/stoplightio/elements ; docs config page | Right context rail showing the definition, backlinks and diagram of whatever ID is selected |
| Stacked / responsive fallback | Redoc `stacked`; Elements `stacked` and `responsive` (sidebar becomes a drawer on small screens) | same | Below a width, rail drops under the paragraph and TOC becomes a drawer |
| Deep link to every operation, schema and field | Redoc; Mintlify (anchor on each parameter, nested params carry the parent path, click copies URL) | redocly.com/docs/redoc/ ; mintlify.com/docs/api-playground/overview | Permalink on every ID definition and table row, not only headings |
| Expansion defaults | Redoc `schemasExpansionLevel`, `jsonSamplesExpandLevel`; Swagger UI `docExpansion` (list/full/none), `defaultModelsExpandDepth`; Scalar `defaultOpenAllTags`, `defaultOpenFirstTag`, `expandAll*` | config pages | Three-state "Fold: key points / all / none" plus per-section remembered state |
| Filter | Swagger UI `filter` (box at top that filters tagged operations); Scalar search modal with `searchHotKey` (Ctrl/Cmd+K) | swagger.io config page ; Scalar configuration.md | Filter box inside the TOC that narrows headings and IDs |
| Order required first | Redoc `sortRequiredPropsFirst`; Scalar `orderRequiredPropertiesFirst` (default true) | config pages | In ID lists, show blocking/open items first |
| Show-more cap | Scalar `maxVisibleRequestBodyProperties` (12) with "show more" | Scalar configuration.md | Long lists (for example 40 backlinks) show 8 then "show all" |
| Dark mode, toggle, force state | Redoc (light and dark), Scalar `darkMode`, `hideDarkModeToggle`, `forceDarkModeState` | same | Already present; add a diagram theme that follows it (item 5) |
| URL sync | Scalar `urlRouting`; Elements `router` (history/hash/memory/static) | same | Hash routing is the right choice for a single static file (Redoc says hash routing works on any static host) |
| "Copy for LLM", "Open in Claude/ChatGPT" in header | Redoc CE header actions (need the spec URL) | redocly.com/docs/redoc/ | "Copy this section as Markdown" for pasting into Linear or an LLM |
| Method/status badges | Docusaurus OpenAPI docs: sidebar generated per tag with `x-position` order (badges not confirmed on the fetched page) | github.com/PaloAltoNetworks/docusaurus-openapi-docs | Status badges on ADR/Q/R (accepted, open, superseded) |
| Plugin/override system | Swagger UI plugins return `{statePlugins, components, wrapComponents, rootInjects, afterLoad, fn}`; `wrapComponents` wraps a component without replacing it; `filter`, `deepLinking` are plain config flags | swagger.io plugin-api page ; swagger.io config page | Architecture idea only: keep `jumpTo`, `showCard`, `renderDiagram` as small replaceable functions |
| Request/response side by side | RapiDoc (models and examples expanded by default, request/response side by side per the GitHub README); Redoc right panel | github.com/rapi-doc/RapiDoc | Weak transfer: only for "option A vs option B" comparisons, which tables already do |
| Collapsible schema tree | Docusaurus OpenAPI docs (schemas collapsed unless `schemaExpansion`); Redoc/Scalar expand-level options | Docusaurus repo ; config pages | Only where a document has nested definitions (glossary term with sub-terms). Low value here |

Not adopted: Try-it consoles, code-sample tabs, servers/auth panels (no HTTP to call), RapiDoc render styles (`read`, `view`, `focused`: the page I could fetch names them but does not explain them).

## Ranked list (15 improvements)

Ranking = reader value on this page divided by cost, with dependencies respected. Items 1 to 8 are diagram work, 9 to 15 are viewer-pattern work.

### 1. Figure wrapper: caption "what this shows", legend, accessible name and long description
- What: every mermaid diagram sits in `<figure class="dgm" id="F-xx">` with a `<figcaption>` that has three parts: one-sentence "What this shows", a legend (swatches plus text for each class used), and a collapsed "Text version" `<details>` that lists nodes and edges in prose or a small table. Mermaid also gets `accTitle` and `accDescr`.
- Precedent: c4model.com "Notation" (fetched): give each diagram a title that states type and scope, include a key explaining shapes, colours, borders, line types and arrowheads, name element type, label every line, put the protocol on container links, keep colour consistent and think of black-and-white printing and colour blindness. W3C WAI "Complex images" tutorial (fetched): short alt plus a long description available to everyone, in a `<figure>` with `<figcaption>`, `role="group"` for older browsers; `aria-describedby` only for plain-text descriptions because assistive tech reads it as one paragraph. Mermaid accessibility page (fetched): `accTitle:` and `accDescr:` / `accDescr { ... }` generate `<title>`, `<desc>`, `aria-labelledby`, `aria-describedby`, for all diagram types. WCAG SC 1.4.1 (fetched): colour must not be the only way to convey information; technique G111 colour plus pattern, G14 text equivalent.
- Cost: small to medium (authoring cost dominates: about 30 diagrams need a caption line and legend). A script can generate the legend from the `classDef` names if each class has a `%% legend: label` comment.
- Risk: legends drift from the `classDef` colours. Mitigate by building legend swatches from the same CSS variables used in `themeVariables` (item 5). Long descriptions go stale, so keep them in the same source block as the diagram.
- Implementation: in the diagram source start with `accTitle: ...` and `accDescr { ... }`. Wrapper markup: `<figure class="dgm" data-diagram="F-12"><div class="dgm-stage"></div><figcaption><p class="what">...</p><ul class="legend"><li><span class="sw sw-store"></span>Datastore</li></ul><details><summary>Text version</summary>...</details></figcaption></figure>`. Legend swatch also differs by border style or shape, not by colour alone (SC 1.4.1). Give the figure `role="group"` and `aria-labelledby` on the caption.

### 2. Hover/focus on a diagram node shows the same popover as in the text
- What: pointing at a node whose label contains R12, ADR-4 or a glossary term opens the existing popover (definition, "used N times", Go to definition). Works with keyboard focus and tap.
- Precedent: Structurizr viewer (fetched): tooltips toggled with `t`, Alt held makes a tooltip sticky; elements show symbols when they have links. D2 tooltips (fetched): shown on hover, objects with a tooltip carry an icon, static exports number the icons and add an appendix, i.e. a fallback when hover is unavailable. Page-internal precedent: your own ID popovers.
- Cost: medium.
- Risk: mermaid `strict` strips click and tooltip directives, so this must be done after render (below). Touch: tap opens the card, second tap on the card's link navigates. Do not make the popover the only place a node's meaning lives (NN/g, from the previous report).
- Implementation (post-process, independent of securityLevel):
  1. Render with `mermaid.render(id, src)` into `.dgm-stage` via `innerHTML = svg`. Do not call `bindFunctions` (it only binds click/tooltip directives, which strict ignores; the usage page says to call it only if defined).
  2. Collect label elements: flowchart nodes `svg g.node`, clusters `svg g.cluster`, edge labels `svg .edgeLabel`; sequence participants `svg g.actor, svg text.actor` and message text `svg text.messageText`; class names are [unverified] for the shipped version, so print `svg.innerHTML.slice(0,3000)` once and confirm.
  3. For each, `const text = el.textContent`. Run the same ID regex the page already uses (for example `/\b(R|ADR|Q|D|I|T)-?\d+\b/g`) plus the glossary term list sorted by length descending. Store `el.dataset.refs = "R12 ADR-4"`, add `tabindex="0"`, `role="button"`, `aria-label = labelText + ", references R12, ADR-4"`, and a CSS class `has-ref` (dashed underline via `svg .has-ref text{text-decoration:underline dotted}`).
  4. One delegated listener on the stage: `pointerover/focusin` on `closest('.has-ref')` calls the existing `showCard(anchorEl, firstId)`; if a node has several refs, show the first and list the others as chips in the card. Use `getBoundingClientRect()` of the `g` for positioning, which already accounts for SVG scaling.
  5. Do not wrap text in `<a>` inside `foreignObject` (HTML labels): set `htmlLabels:false` in `mermaid.initialize` (the config page says root-level `htmlLabels` wins) if you need reliable text positions; otherwise hover on the `foreignObject` parent `g` works too.

### 3. Click a node to jump to its section, with back-after-jump
- What: click or Enter on a `has-ref` node calls the existing `jumpTo(id)` (opens ancestor `details`, scrolls, records the back stack). With several refs, the click opens the card instead.
- Precedent: Structurizr double-click zooms into a level or opens documentation, decisions or URLs, and shows a modal when an element has several targets; `b` returns to the last viewed diagram (viewer page, fetched). Mermaid `click nodeId href "url" "tooltip"` does the same but only when `securityLevel` is loose or antiscript; strict disables it (flowchart and usage pages, fetched).
- Cost: small once item 2 exists.
- Risk: conflicts with pan (item 4): a drag must not count as a click. Track `pointerdown` x/y and ignore the click if moved more than 4 px. Single click vs Structurizr's double click: single click is fine here because a node click does not change zoom.
- Implementation: in the same delegated handler, `stage.addEventListener('click', e => { if (moved) return; const n = e.target.closest('.has-ref'); if (!n) return; const ids = n.dataset.refs.split(' '); ids.length === 1 ? jumpTo(ids[0]) : showCard(n, ids[0]); })`. Give the "reverse" link too: every figure gets a stable id (`F-12`) and the ID backlinks list (existing "used N times") includes "Figure F-12" entries by scanning `.has-ref` data once.

### 4. Full-screen view with pan and zoom (buttons, wheel, drag, pinch)
- What: an "Expand" button on each figure opens a `<dialog>` with the SVG at full viewport, `+ / - / Fit / 100%` buttons, wheel zoom, drag pan, pinch, Esc to close. Node hover/click keep working inside.
- Precedent: Structurizr viewer: floating zoom buttons, `+ - w h c` keys (fit width, fit height, fit content), `f` full screen (viewer page, fetched). svg-pan-zoom (fetched): wheel, double-click zoom, drag pan, `controlIconsEnabled`, `fit`, `center`, `minZoom/maxZoom`, `resize()`, `destroy()`, CDN `https://cdn.jsdelivr.net/npm/svg-pan-zoom@3.5.0/dist/svg-pan-zoom.min.js`, BSD-2-Clause; touch and pinch are not built in (needs `customEventsHandler`/Hammer), hidden SVGs unsupported, large SVGs pan slowly. panzoom by anvaka (fetched): "mobile friendly", `minZoom/maxZoom`, `bounds`, `filterKey`, `beforeWheel`, `zoomDoubleClickSpeed`, events, `dispose()`, unpkg `panzoom@9.4.0/dist/panzoom.min.js`, MIT, SVG usage by passing a `<g>` with an id.
- Cost: medium. Choice: panzoom@9.4.0 from unpkg (touch and pinch included, MIT) or a hand-written 80-line Pointer Events version with no dependency. I would hand-write it: the page is a single file and the library choice adds a CDN failure mode; the prior report already recommended a hand-rolled version. If you do load a library, take panzoom, not svg-pan-zoom, because of pinch.
- Risk: SVG ids duplicated if you clone (markers `url(#...)` resolve to the first match, usually identical, so mostly harmless but ids in `aria-labelledby` collide). Prefer moving the same `<svg>` node into the dialog on open and back on close. `useMaxWidth` leaves `style="max-width:...px"` on the svg: clear `svg.style.maxWidth` and set `width/height 100%` in the dialog. `touch-action:none` only on the stage inside the dialog. Zoom buttons give a non-gesture path (WCAG; prior report).
- Implementation: `const vb = svg.viewBox.baseVal; state={k:1,x:0,y:0}`; apply `g.setAttribute('transform', 'translate(x y) scale(k)')` to a wrapper `<g>` you create around the SVG's children (do not change `viewBox`). Wheel: `k' = clamp(k*exp(-deltaY*0.0015), 0.3, 8)`, keep the cursor point fixed: `x' = px - (px - x) * k'/k`. Pinch: track two pointers in a Map, scale by distance ratio. Fit: `k = min(stageW/vb.width, stageH/vb.height)` and centre. Keys: `+ - 0 f`, arrows pan, Esc native. On close call `dialog.close()` and move the SVG back.

### 5. One theme for light and dark: mermaid `base` theme driven by the page's CSS variables, re-render on toggle
- What: all diagrams use the page palette (nodes, edges, notes, actors) and flip with the light/dark switch, with no white boxes in dark mode.
- Precedent: Mermaid theming page (fetched): only the `base` theme can be customized; `themeVariables` include `primaryColor`, `primaryTextColor`, `lineColor`, `background`, `secondaryColor`, `tertiaryColor`, `noteBkgColor`, `noteTextColor`, `mainBkg`, `fontFamily`, `fontSize` (default 16px); only hex colours are recognized; `darkMode: true` changes how derived colours are computed. D2 (fetched): separate light and dark theme catalogs, `theme-overrides` / `dark-theme-overrides`, a flag to follow the system dark setting, default does not adapt.
- Cost: medium.
- Risk: re-render cost (30 diagrams) on each toggle: re-render only visible figures, mark others `data-stale` and render when they enter the viewport (IntersectionObserver). Also re-attach item 2/3 listeners (delegated listeners on the stage survive; the post-process step must re-run). `deterministicIds: true` (config page, fetched) keeps ids stable across re-renders and in git. Mermaid reads colours as hex, not `var(--x)`: resolve with `getComputedStyle(document.documentElement).getPropertyValue('--surface').trim()` and convert `rgb()` to hex if needed. Check text contrast against the 3:1 non-text rule for lines and borders (WCAG non-text contrast, fetched; text needs 4.5:1 under SC 1.4.3 [number from memory]).
- Implementation: keep the source in `figure.dataset.src` (or a `<script type="text/plain">`). `function cfg(){ const css=getComputedStyle(root); const v=n=>hex(css.getPropertyValue(n)); return {startOnLoad:false, securityLevel:'strict', theme:'base', darkMode: isDark(), deterministicIds:true, themeVariables:{ primaryColor:v('--node-bg'), primaryTextColor:v('--fg'), primaryBorderColor:v('--node-border'), lineColor:v('--edge'), background:v('--bg'), noteBkgColor:v('--note-bg'), noteTextColor:v('--fg'), fontFamily:'inherit', fontSize:'14px' }}}`. On toggle: `mermaid.initialize(cfg())`, then re-render figures. For semantic classes use `classDef` with fixed hexes per theme: emit two `classDef` blocks and choose by theme when building the source string. Per-diagram override can also be done through frontmatter config.

### 6. Hover on a node highlights its edges and neighbours, dims the rest
- What: hovering or focusing a node raises its incoming and outgoing edges and connected nodes, dims everything else; Esc or leaving resets. Optional: click-lock (Alt+click, like Structurizr's sticky tooltip).
- Precedent: Structurizr viewer: moving the cursor over a relationship highlights that link; filtering by tag or perspective highlights matching elements and relationships (search results, with the caveat that the docs I fetched list tag/perspective filtering at keys `g` and `p` and do not describe a hover-highlight feature on nodes). IcePanel flows highlight the relevant objects and connections in order (search results from docs.icepanel.io). Hover-highlight of neighbours on node hover is therefore partly my extension.
- Cost: medium.
- Risk: edge-to-node mapping is version dependent [unverified]. In flowcharts mermaid v10/v11 edges are `path.flowchart-link` with classes `LS-<fromId>` and `LE-<toId>` and node group ids like `flowchart-<id>-<n>`. Verify on the shipped version. If absent, fall back to geometry: compare the first and last points of `path.getPointAtLength(0)` and `getPointAtLength(getTotalLength())` against each node's `getBBox` transformed into svg coordinates. Sequence diagrams: highlight by participant instead (all messages from or to that actor, using `text.messageText` y and the arrow `line` x1/x2; plain scan by x-range). Dimming uses a class on the `<svg>` (`.dgm-focus .node:not(.on){opacity:.25}`), not inline styles, so print and theme still work. Reduced motion: no transition.
- Implementation: after render build `adj = Map(nodeKey -> {edges:Set, nodes:Set})` once from edge classes; `pointerover` on node sets `.on` on node, neighbour nodes, edges and their label elements; add `aria-live="polite"` text only if keyboard focus is used ("3 connections: ...").

### 7. Sequence diagrams: numbered steps tied to a step list
- What: every sequence diagram has `autonumber`, and under it an ordered list "1. Router calls X..." whose items highlight the arrow on hover and vice versa. Prose can say "step 4 of F-07".
- Precedent: Mermaid sequence page (fetched): `autonumber` plus config `showSequenceNumbers`, `box` grouping with colour, `rect` background highlight, `Note over`, `loop/alt/opt`. IcePanel flows (docs.icepanel.io, search result): ordered steps, each pointing to an object or connection, default view shows only previous and next step descriptions with a toggle for all; IcePanel's own blog compares flows with UML sequence diagrams. Structurizr viewer: animation steps forward `.` and backward `,`. C4 notation page: label every line. Note: autonumber is stated in the fetched page as v11.15.0+ for the start/increment syntax; plain `autonumber` is older [unverified exact version]; check the shipped version.
- Cost: medium (the list needs authoring; the link between list and arrow is automatic if you use the order of `text.messageText`).
- Risk: message numbering restarts or skips in `alt/loop` blocks [unverified]; match by index of `.messageText` and sequence-number circles (class `sequenceNumber` [unverified]); verify per diagram. Colour `box` groups need rgb()/rgba(), hex is read as a comment (page, fetched).
- Implementation: `const msgs=[...svg.querySelectorAll('text.messageText')]`; build `<ol class="steps">` from author-supplied text, else fall back to message text. `li.dataset.i`; `li` hover and `msgs[i]` hover toggle `.on`, and click on a message scrolls its `li` into view. Provide a "Show steps" `<details>` open by default on wide screens.

### 8. Diagrams join the ID index: "also shown in F-12" in backlinks, and an index of figures
- What: the existing "used N times" counts diagram nodes, and each definition lists "In diagrams: F-03, F-12" with links that scroll to the figure and pulse the node. A "Figures" list in the TOC (title + caption line) lets the reader jump to any of the ~30 diagrams.
- Precedent: Structurizr diagram navigator lists diagrams above/beside/below the current one (`n`, `l`, `Space` quick navigation) (viewer page, fetched); Redoc/Scalar list schemas as their own sidebar section (`schema-definitions-tag-name`, `modelsSectionLabel`). Backlinks themselves are in the previous report.
- Cost: small once item 2 has built `data-refs`.
- Risk: counts must be consistent: say "N in text, M in diagrams" so the old number does not silently change meaning. Lazy rendering (item 5) means unrendered figures have no `data-refs`; parse refs from the mermaid source text with the same regex at load, not from the SVG.
- Implementation: at load, `figures.forEach(f => regexAll(f.dataset.src).forEach(id => refs.get(id).figs.add(f.id)))`. On jump from a backlink: `jumpTo(figureId)` then add `.pulse` to nodes whose `data-refs` includes the ID once the figure is rendered (await a promise stored on the figure).

### 9. Status badges on IDs, in the text, the TOC filter and the popover
- What: small pill after each ID reference: ADR accepted/proposed/superseded, Q open/answered, R must/should, D decided. The popover and search results show the same pill.
- Precedent: Docusaurus OpenAPI docs generate per-tag sidebar slices ordered by `x-position` (Docusaurus repo, fetched; method badges not confirmed on that page). Swagger UI colours operations by HTTP method (general knowledge, not on a fetched page). Redoc `sortRequiredPropsFirst` and Scalar `orderRequiredPropertiesFirst` show that required/optional is a first-class flag in the reading order. The mapping to design documents is my inference.
- Cost: small, if each definition already has `data-kind` and `data-status` (prerequisite in the first report).
- Risk: colour-only meaning (use text plus icon); badges inflate line height in dense tables (use `font-size:.75em`, no extra padding in table cells); stale status if the badge text is copied instead of read from the definition (derive it from the definition node at load).
- Implementation: `document.querySelectorAll('a[data-ref]').forEach(a => { const d = defs.get(a.dataset.ref); if (d?.dataset.status) a.insertAdjacentHTML('afterend', '<span class="pill pill-'+d.dataset.status+'">'+label+'</span>') })`. Add a legend in the page header showing every pill (same reasoning as item 1).

### 10. Right context rail (three-pane on wide screens)
- What: at 1280 px and wider, a third sticky column shows the "current ID": definition, status, "used N times" list grouped by document, related figures, copy-link button. Selecting an ID (click, focus, or hover with a small delay) fills it; with nothing selected it shows the current section's outline. Below 1280 px it falls back to the popover.
- Precedent: Redoc CE three-panel layout and stacked fallback; Stoplight Elements `sidebar` (three columns, resizable sidebar), `responsive` (sidebar becomes a drawer on small screens) and `stacked` (single column) (docs pages, fetched). Docs Redoc/Elements keep request/response samples in the right column while the prose scrolls; the equivalent here is the definition and backlinks.
- Cost: large (layout change plus a second renderer for card content; reuse the popover renderer so only the container differs; medium if you build it as "pin the popover into the rail").
- Risk: horizontal space on a 1 MB document with wide tables and diagrams: the rail must collapse and the main column must not shrink below about 70 characters; sticky inside a flex/grid parent needs `align-self:start`; two sources of truth for the card (rail and popover) must not both show at once. Keyboard: rail is a landmark `<aside aria-label="Selected item">` and not a live region that speaks on every hover (update only on click/Enter).
- Implementation: CSS grid `grid-template-columns: var(--toc) minmax(0,1fr) 20rem` at `@media (min-width:1280px)`; `aside.rail{position:sticky; top:var(--header-h); max-height:calc(100vh - var(--header-h)); overflow:auto}`; `showCard(el,id)` becomes `renderCard(container,id)`; pin button inside the popover moves it to the rail. Option "Pin diagram": a button on any figure copies the rendered SVG into the rail so it stays visible while reading the text that explains it (the same trick as Redoc's sticky samples).

### 11. Row-level and ID-level permalinks with "Copy link"
- What: the ID definition and each table row that defines an ID gets a copy-link control; the URL fragment survives because ids are unique. In diagrams, a node link is `#F-12~nodeKey` which jumps to the figure and pulses that node.
- Precedent: Redoc "deep links to every operation, schema, and field"; Mintlify clickable anchor on each parameter that copies the URL, nested parameters include the parent path (`endpoint-path#parameter-name`) (both fetched). The earlier report covers heading permalinks; this extends to rows, IDs and diagram nodes.
- Cost: small to medium.
- Risk: duplicate ids across the six documents; add a load-time `console.warn` listing duplicates and a visible "Link check" counter. Clipboard fallback and secure-context caveat from the previous report apply. Fragment with `~` must be parsed in your `hashchange` handler (`location.hash.slice(1).split('~')`), because the browser tries to scroll to the whole string.
- Implementation: `row.id = id`; add a `<button class="permalink" aria-label="Copy link to R12">` in the first cell; `copy(location.origin+location.pathname+'#'+id)`; announce via the existing live region. Node link: node `dataset.key` is the mermaid node id taken from the `g.node` id by regex `^flowchart-(.+)-\d+$` [unverified for the shipped version].

### 12. Filter inside the contents (TOC) with count and "clear"
- What: a small input at the top of the TOC: typing "ADR", "open", or a word narrows the TOC to headings and IDs whose text matches, shows "7 of 212", and highlights matching headings in the body. Separate from the global search modal: it is a view filter, not a navigator.
- Precedent: Swagger UI `filter` ("box at top to filter the displayed tagged operations", `filter` can be boolean or a string); Scalar sidebar search plus `searchHotKey`; Bump.sh header search labelled Cmd+K (Bump docs page, fetched, shortcut inferred from label).
- Cost: small.
- Risk: duplicates function with search (#2 in the previous report); keep it TOC-only so there is no second index. Collapsed TOC nodes must expand on match; scroll spy must keep working when hidden items are filtered (spy on all headings, display filter only). Do not use `display:none` on the active item.
- Implementation: `input.addEventListener('input', debounce(() => { for (const li of tocItems) li.hidden = !li.textContent.toLowerCase().includes(q) ... ancestors visible }, 80))`; `aria-live` count "7 of 212"; `Esc` clears; ID kinds as quick buttons ("ADR", "Q", "R") that set the query.

### 13. Expansion level control: "Key points / Everything / Titles only", remembered per section
- What: one segmented control sets how much supporting material is open (evidence, options analysis, tables folded), with per-`details` memory and URL fragment auto-open. Shows "12 folded".
- Precedent: Swagger UI `docExpansion` = list/full/none and `defaultModelsExpandDepth` / `defaultModelExpandDepth`; Redoc `schemasExpansionLevel`, `jsonSamplesExpandLevel`; Scalar `defaultOpenAllTags`, `defaultOpenFirstTag`, `expandAllResponses`, `expandAllParameters` (default true), `expandAllModelSections`, with a note that expanding all schema properties may hurt performance on large documents (all config pages, fetched). The previous report already covers Expand all/Collapse all and the NN/g warning; this adds the three-state default and the per-section memory.
- Cost: small.
- Risk: same NN/g and GOV.UK cautions (do not fold requirements, decisions, risks). localStorage in try/catch. Print opens everything. Hash jumps must open ancestors.
- Implementation: `details.fold` get `data-level="1|2"`. Level control sets `d.open = Number(d.dataset.level) <= current`. Persist `{level, overrides:{id:boolean}}`; `toggle` event updates overrides.

### 14. "Copy section as Markdown" (and "copy link + title") for Linear/Slack/LLM
- What: a button next to every h2/h3 and in the popover copies the section as clean Markdown with IDs resolved ("R12 (must): text") plus the permalink at the top, so a reviewer can paste a decision into a Linear ticket or give a section to an LLM.
- Precedent: Redoc CE header actions: "Copy for LLM", "Open in Claude", "Open in ChatGPT" (they need the description file URL) (redocly.com/docs/redoc/, fetched). Mintlify "simple" display copies an endpoint (api-playground page, fetched). Material code-copy buttons are in the previous report.
- Cost: medium (a small HTML-to-Markdown converter for headings, paragraphs, lists, tables, code, links; skip diagrams, replace with `[Figure F-12: caption]` and the text version from item 1).
- Risk: copying a section that is mid-way through `content-visibility:auto` is fine because the DOM is present; clipboard permissions need user gesture; large sections (50 KB) may be too large to paste: show the character count and a "Copy first N" fallback; do not copy hidden tooltip text.
- Implementation: walk `section.children` and map tags: `h2→'## '`, `p→text`, `li→'- '`, `table→gfm`, `pre→fenced`, `a[data-ref]→'R12'`; join with blank lines; prepend `Source: <permalink> (copied 28/10/2026)`. The date comes from `new Date()` at copy time.

### 15. Text-size guard for diagrams: auto "Open full size" when text would render too small
- What: after render, compute the effective font size (`svgWidthOnScreen / viewBox.width * baseFontPx`). If it falls under a threshold, show a banner chip "Small text, open full size" on the figure and prefer horizontal scroll over shrinking.
- Precedent: Mermaid `useMaxWidth` (config page, fetched): true sets 100% width and scales the diagram, false uses absolute size; `themeVariables.fontSize` default 16px (theming page, fetched); `maxTextSize` limits source size (default 50000). WCAG 1.4.4 resize text (fetched): resize to 200% without loss, images of text excluded; SVG is not discussed there. No fetched study gives a minimum size; the 11 to 12 px floor I propose is my heuristic and should be tested on the real page at 1280 and 375 px. Secondary literature seen only in a search snippet: a review reports negative correlation between UML diagram size and performance and a guideline of 20 to 60 elements per diagram (not verified in a full text).
- Cost: small.
- Risk: the threshold is a guess; a phone-width page would flag nearly every wide diagram, which is the correct behaviour but may annoy. Only show the chip, never block.
- Implementation: `const scale = svg.getBoundingClientRect().width / svg.viewBox.baseVal.width; const px = scale * 14; chip.hidden = px >= 11;` run on `ResizeObserver`. Also count `g.node` at load and log diagrams over 40 nodes to a dev console list "split candidates".

## Cross-cutting implementation notes for mermaid under `securityLevel: 'strict'`

1. Do not use `click`, `href`, `callback` or tooltip directives (mermaid disables them in strict; they work in loose/antiscript only; flowchart and usage pages, fetched). Do not raise the level: loose also allows HTML in labels, and the usage page says deciding whether diagram sources are trustworthy is the site owner's responsibility. Your source is trusted, but there is no benefit worth the exposure when post-processing gives the same result.
2. The render contract: `const {svg, bindFunctions} = await mermaid.render(id, src); stage.innerHTML = svg; // skip bindFunctions`. Do all enhancement in one function `enhance(figure)` that is idempotent and re-run after every render (theme change, lazy render).
3. Keep a registry `figures[id] = {src, rendered:false, ready:Promise}` so that jumps and backlinks can `await` the render.
4. Use `deterministicIds:true` so node keys do not change between renders.
5. Verify class names and id patterns once (`flowchart-<id>-<n>`, `LS-`/`LE-` edge classes, `g.cluster`, `g.actor`, `text.messageText`, sequence number elements) by dumping the SVG of one flowchart and one sequence diagram; these are internal names that may change between mermaid versions, so wrap each selector lookup with a fallback and a `console.warn('mermaid selector miss')`.
6. Accessibility: mermaid gives the SVG `aria-roledescription` automatically and `accTitle/accDescr` produce `<title>`, `<desc>` and ids (accessibility page, fetched). When you move the SVG into the dialog keep its element id.
7. Print: force light theme variables, `svg{max-width:100%;height:auto}`, hide expand buttons, show the legend and the text version expanded.

## Sources (accessed 28/10/2026)

API viewers
1. Redocly, "Redoc CE" overview - https://redocly.com/docs/redoc/
2. Redocly, "Redoc configuration options" - https://redocly.com/docs/redoc/config
3. Scalar, "Configuration" (GitHub documentation/configuration.md) - https://github.com/scalar/scalar/blob/main/documentation/configuration.md
4. Stoplight Elements README - https://github.com/stoplightio/elements
5. Stoplight Elements configuration options (GitHub copy) - https://github.com/stoplightio/elements/blob/main/docs/getting-started/elements/elements-options.md
6. RapiDoc README - https://github.com/rapi-doc/RapiDoc (attribute reference page not retrievable)
7. Swagger UI, "Configuration" - https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/
8. Swagger UI plugin API (GitHub docs) - https://github.com/swagger-api/swagger-ui/blob/master/docs/customization/plugin-api.md ; and https://swagger.io/docs/open-source-tools/swagger-ui/customization/plugin-api/
9. PaloAltoNetworks docusaurus-openapi-docs - https://github.com/PaloAltoNetworks/docusaurus-openapi-docs
10. Mintlify, "API playground overview" - https://www.mintlify.com/docs/api-playground/overview
11. Bump.sh help - https://docs.bump.sh/help/

Diagrams
12. Mermaid, "Usage" (securityLevel, render, bindFunctions) - https://mermaid.js.org/config/usage.html
13. Mermaid, "Flowchart" (interaction, linkStyle, classDef) - https://mermaid.js.org/syntax/flowchart.html
14. Mermaid, "Theming" - https://mermaid.js.org/config/theming.html
15. Mermaid, "Accessibility" - https://mermaid.js.org/config/accessibility.html
16. Mermaid, "Configuration schema" (securityLevel, htmlLabels, maxTextSize, deterministicIds, useMaxWidth) - https://mermaid.js.org/config/schema-docs/config.html
17. Mermaid, "Sequence diagrams" - https://mermaid.js.org/syntax/sequenceDiagram.html
18. svg-pan-zoom - https://github.com/bumbu/svg-pan-zoom
19. panzoom (anvaka) - https://github.com/anvaka/panzoom
20. Structurizr, "Diagram viewer" - https://docs.structurizr.com/server/diagrams/viewer ; keyboard shortcuts (search snippet) https://docs.structurizr.com/ui/diagrams/keyboard-shortcuts
21. IcePanel, docs welcome - https://docs.icepanel.io/ ; flows (search snippets) https://docs.icepanel.io/features/flows , https://icepanel.io/blog/2024-10-22-comparison-icepanel-flows-vs-uml-sequence-diagrams
22. D2, "Interactive" (tooltips, links) - https://d2lang.com/tour/interactive/ ; "Themes" - https://d2lang.com/tour/themes/
23. C4 model, "Notation" - https://c4model.com/diagrams/notation
24. W3C WAI, "Complex images" - https://www.w3.org/WAI/tutorials/images/complex/
25. W3C, "Understanding SC 1.4.1 Use of Color" - https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html
26. W3C, "Understanding SC 1.4.11 Non-text Contrast" - https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html
27. W3C, "Understanding SC 1.4.4 Resize Text" - https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html
28. Moody, "The Physics of Notations" (via search summaries, not the paper) - e.g. https://homepages.uc.edu/~niunn/courses/RE-refs/PoN-RE09.pdf
29. Yusuf, Kagdi, Maletic, eye-tracking study of UML class diagrams, ICPC 2007 (search snippet only) - https://www.cs.kent.edu/~jmaletic/cs69995-PC/papers/yusuf-eye-tracking07.pdf
