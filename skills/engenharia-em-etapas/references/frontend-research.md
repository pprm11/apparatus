# Front-end features for a long, ID-dense technical design page

Scope: one static HTML page, about 1 MB of text, six engineering documents, many IDs (R12, ADR-4, Q29), tables, mermaid diagrams. Existing: sticky TOC, stage cards, ID links with hover tooltip, glossary hover, abbr, light/dark.
Constraint: vanilla JS, no build step, single file. Access date for all sources: 28/10/2026.

## Method and honesty notes

- Sources were fetched with WebFetch/WebSearch on 28/10/2026. A claim marked "[not verified]" came from the fetch tool's own general knowledge and not from the page, or I could not fetch the source (Read the Docs search page and WCAG 2.2 target size returned 404; GitBook redirected and I did not follow; Stripe docs layout could not be confirmed, only third-party descriptions).
- Costs: small = under about 60 lines of JS/CSS, medium = 60 to 250 lines, large = needs new data structure or authoring workflow.
- No benchmark was run on the actual page. Performance statements for the 1 MB page are estimates from the cited sources.

## Ranked list

### 1. Scroll spy in the TOC (current section highlighted, TOC auto-scrolls to the active item)
- Does: the reader always knows which of the six documents and which section they are in; the TOC doubles as a progress map.
- Evidence: NN/g "Table of Contents" says that when the TOC is sticky, the current section should be highlighted to show progress. Material for MkDocs ships `navigation.tracking` (address bar follows the active anchor). Docusaurus right-rail TOC does the same pattern.
- Cost: small.
- Risks: touch (TOC rail is hidden on narrow screens, NN/g found collapsed sticky TOCs often missed, so keep a visible "Contents" button); a11y (set `aria-current="location"` on the active link, do not steal focus); performance (use IntersectionObserver, not scroll handlers; MDN says the browser optimizes it, callback still runs on main thread, keep it tiny).
- Note: one IntersectionObserver over all h2/h3 with `rootMargin: "0px 0px -70% 0px"`, keep the topmost intersecting heading, set `aria-current`, call `scrollIntoView({block:"nearest"})` on the TOC item.

### 2. Search with keyboard shortcut (`/` and Ctrl/Cmd+K), results grouped by document, ID-aware
- Does: the main way to find "where is Q29 or ADR-4 discussed" in 1 MB. Typing an exact ID jumps straight to its definition.
- Evidence: Material for MkDocs search (suggestions, highlighting, shareable query, works offline: `search.suggest`, `search.highlight`, `search.share`). Mintlify and GitBook have search as the main entry (not verified in this run). Browser Ctrl+F still works but cannot filter by document or ID type.
- Cost: medium. Build the index at load from section elements (title, ID list, text), no library needed; plain tokenized substring match with ID exact-match boost. Large only if you add fuzzy ranking (lunr/MiniSearch from cdnjs).
- Risks: a11y (WCAG 2.1.4 Character Key Shortcuts: a bare `/` must be turn-off-able, remappable, or only active on focus; safest is also offering a visible Search button and Ctrl/Cmd+K, and ignore `/` inside inputs, textareas, contenteditable); performance (index 1 MB once, lazily on first open, store as a Map; results capped at 50; do it in `requestIdleCallback`); do not trap native Ctrl+F.
- Note: `<dialog>` with an input, `showModal()`, results as a listbox with `aria-activedescendant`, Esc closes and returns focus, Enter navigates to `#id` and highlights hits with `<mark>`.

### 3. Touch- and keyboard-safe popovers for ID and glossary tooltips (tap to open, Esc to close, hoverable, focusable)
- Does: the existing hover tooltips become usable on phones and with keyboard, and a long definition can be read and copied without it vanishing.
- Evidence: WCAG 1.4.13 (dismissible with Esc without moving pointer/focus, hoverable, persistent), W3C Understanding doc. NN/g "Tooltip Guidelines": hover tooltips are generally not available on touchscreens, popup tips open on tap and close on tap-outside, must work with keyboard, must not hold task-critical info. MDN Popover API (`popover="auto"`, Baseline 2025, top layer) gives light dismiss for free; MDN notes `interestfor` exists but I would not rely on it yet.
- Cost: medium.
- Risks: touch (a link that is both "go to definition" and "show tooltip": on touch, first tap opens the card with a visible "Go to definition" link inside; do not use `:hover` only); a11y (trigger gets `aria-expanded` and `aria-describedby`, focus shows the card too, Esc closes, card is hoverable so no gap between trigger and card); performance (build one shared card element and fill it on demand from the definition node, do not clone hundreds of tooltips up front); NN/g says do not put necessary info only in tooltips, so the definition must also exist at its anchor.
- Note: one shared `<div popover="auto" role="tooltip">`, delegated `pointerenter/focusin/click` on `a[data-id], abbr, .term`, `matchMedia("(hover: none)")` switches to tap mode, position with `getBoundingClientRect` and flip near edges.

### 4. Return-after-jump ("Back to where you were")
- Does: after clicking R12 in a paragraph and landing 40k words away, one control (and the browser Back button) returns to the exact previous spot. This is the biggest friction in an ID-linked document.
- Evidence: NN/g TOC article recommends back-to-top links on long pages; Material has `navigation.top` (back-to-top shown when scrolling up). MDN History API: `replaceState` updates the current entry, `pushState` adds one, `popstate` fires on traversal [scroll restoration details: not verified on MDN, from general knowledge].
- Cost: small.
- Risks: a11y (button must be a real `<button>`, announce via `aria-live="polite"` "Returned to previous position"); history pollution if every scroll-spy update pushes entries (use `replaceState` for spy, `pushState` only for explicit jumps); the browser already restores scroll on Back for hash links, so test that you do not double-handle.
- Note: on internal link click, save `scrollY` in a small stack, `history.pushState`, show a sticky pill "Back to <section title>" for about 10 s; Alt+Left also works for free.

### 5. Heading and ID permalinks with copy
- Does: every heading and every ID definition (R12, ADR-4) gets a hover/focus "link" control that copies the absolute URL with fragment, for pasting into Linear, Slack, PRs.
- Evidence: Material for MkDocs renders a "permanent link" on each heading; Docusaurus gives every heading an ID and warns IDs must be unique per page (duplicates make a heading unlinkable). Both fetched on 28/10/2026.
- Cost: small.
- Risks: touch (no hover, so keep the icon always visible at low contrast on touch, or show on tap; make target at least 24x24 CSS px, WCAG 2.2 SC 2.5.8 [could not fetch the page, number from memory]); clipboard needs secure context: MDN says `writeText` works only on HTTPS and can throw `NotAllowedError`, and file:// or an internal HTTP host may fail, so add a `document.execCommand("copy")` or select-text fallback and a visible "Copied" status; duplicate IDs across the six documents would break links, add a build-time or load-time check that logs duplicates.
- Note: append `<a class="permalink" href="#id" aria-label="Copy link to R12">` to each `h2-h4, [data-def]`; click copies `location.origin+path+"#id"` and writes "Copied" into a polite live region.

### 6. "Where is this ID used" backlinks (reverse index)
- Does: on each definition (R12, ADR-4, Q29) shows "Referenced in 9 places" with a list grouped by document and section; answers traceability questions ("which requirements does this ADR satisfy?") without Ctrl+F.
- Evidence: Docs-as-code traceability practice; no single doc-site precedent fetched. Closest: Notion "backlinks" (the Notion MCP exposes a list-page-backlinks tool) and MediaWiki "What links here" [not fetched]. I treat this one as a design inference from the nature of the document, not as a proven pattern.
- Cost: medium. At load, walk all `a[data-id]` (or run a regex over text nodes if IDs are not yet links), group by target id, store the nearest preceding heading as the label. Large only if IDs are not yet marked up consistently.
- Risks: performance (one pass over about 1 MB DOM is a few tens of ms in my estimate, run after first paint); a11y (render as a `<details>` list under the definition, closed by default, with count in the summary); correctness (regex on text finds false positives like "R12" in "VR12", mark IDs with word boundaries and a known ID set, which also makes the page lint itself: report "defined but never referenced" and "referenced but not defined").
- Note: `const refs = new Map(); document.querySelectorAll('a[data-ref]').forEach(a => push(refs, a.dataset.ref, nearestHeading(a)))`; then inject `<details class="backrefs">` after each definition.

### 7. Filtered views by ID type (only decisions, only open questions, only risks)
- Does: chips such as "ADR", "Q (open)", "R (requirements)", "Risks" that dim or hide everything except matching blocks, plus a count per chip; turns the document into a decision log or an open-questions checklist for a review meeting.
- Evidence: NN/g progressive disclosure: initial display signals priority; warns against hiding things users need and against more than two disclosure levels; the filter should be an obvious control with clear labels (information scent). Docs sites do not usually filter by item type, so this is an application of the principle, not a copied feature.
- Cost: medium. Needs each decision/question block to carry `data-kind` and `data-status` (e.g. `data-kind="Q" data-status="open"`).
- Risks: a11y (chips are toggle buttons with `aria-pressed`; announce "Showing 14 of 37 items" in a live region; never use `display:none` that cannot be reversed, always show an "active filter: X, clear" bar); mixing with search and collapsed sections (define one precedence: filter hides blocks, search ignores filter unless user chose "search within filter"); shareable state via `?kind=Q&status=open` using `replaceState`.
- Note: toggle `body[data-filter="Q-open"]` and let CSS do `[data-kind]:not([data-match]){display:none}`, set `data-match` in one JS pass; keep headings of matching blocks and show their breadcrumb.

### 8. Collapsible long sections, with Expand all / Collapse all and find-in-page that still works
- Does: lets the reader fold appendices, long evidence tables and per-option analyses so the main argument is scannable, while the document stays one page.
- Evidence: GOV.UK Design System "Details": use for information only some users need, do not hide what most users need. NN/g "Accordions on Desktop": helps scanning and overview, hurts when users need most content, auto-collapse hinders comparison, and provide Expand all/Collapse all and keep essential content outside; printing needs expansion. MDN `<details name>`: native exclusive groups; `toggle` event. Chrome `hidden=until-found`: find-in-page and fragment navigation can open collapsed content, `beforematch` event fires; supported from Chrome 102 (not Safari/Firefox at time of fetched doc: not stated, so test).
- Cost: medium (small for plain `<details>`, medium to add expand-all, URL-fragment auto-open, print auto-open).
- Risks: a11y (use native `<details>/<summary>`; GOV.UK notes some voice assist software handles it poorly, keep summary text short and descriptive); hidden matches (browser find does not search closed `<details>` in every browser, so your own search (#2) and the `#id` jump must open ancestors: on hashchange, `el.closest("details")` loop sets `open=true`); do NOT collapse requirement/decision text, only supporting evidence; default open for everything in print.
- Note: wrap only evidence/appendix blocks in `<details class="fold">`; add a toolbar button that sets `d.open` on all; in the jump handler open every ancestor `details` before `scrollIntoView`.

### 9. Reading progress indicator (page and per-document)
- Does: a thin bar at the top plus "Document 3 of 6, 42%" in the TOC header; answers "how long is this?" for a 1 MB page.
- Evidence: Material for MkDocs has a loading progress indicator and anchor tracking (different purpose); MDN documents CSS scroll-driven animations (`animation-timeline: scroll(root)`) for progress bars, with feature detection needed because support is still rolling out. NN/g TOC says highlighting current section "shows scroll progress".
- Cost: small.
- Risks: a11y (decorative, `aria-hidden="true"`, or `role="progressbar"` with `aria-valuenow` throttled; never animate under `prefers-reduced-motion`); performance (CSS `animation-timeline` costs zero JS where supported, fall back to `requestAnimationFrame`-throttled scroll listener with `passive:true`); misleading percentage when content-visibility placeholders change heights (see #16), compute progress by heading position, not pixels.
- Note: `@supports (animation-timeline: scroll())` use pure CSS, else a rAF-throttled listener updating `transform: scaleX()`.

### 10. Tables: sticky header, column filter, sort, and horizontal scroll with visible shadow
- Does: requirement/trade-off/ADR tables of 20 to 80 rows stay readable: header remains visible, rows can be filtered by text or status, sorted by ID or status.
- Evidence: Material for MkDocs data tables recommend tablesort (version 5.3.0) with numeric, date, file-size comparators; it applies to tables without a class. Fetched 28/10/2026.
- Cost: medium. Sticky header is CSS-only (`position: sticky; top: var(--header-h)` on `th`, needs the table wrapper not to set `overflow` on an ancestor between the table and the viewport, or sticky silently fails); sort is about 40 lines; filter box about 25 lines.
- Risks: a11y (sort button inside `th` with `aria-sort`; keep DOM order meaningful when reset; natural sort for IDs so R2 < R10, use `localeCompare(b,undefined,{numeric:true})`); touch (wide tables: wrapper `overflow-x:auto`, `tabindex="0"` and `role="region"` with label so keyboard users can scroll); performance (sort moves rows with a DocumentFragment, fine for under 500 rows); sorted state breaks "row N" references, show a "Reset order" button.
- Note: opt in with `table.sortable`; avoid third-party lib, a 40-line sorter is enough.

### 11. Diagram zoom and pan (mermaid), with "open full size" and text-size safety
- Does: wide mermaid diagrams (architecture, sequence) become readable on laptop and phone: click opens a full-viewport view with wheel/pinch zoom, drag pan, Esc to close, and a button to copy/download the SVG.
- Evidence: Material for MkDocs docs on diagrams say nothing about zoom and note that unsupported diagram types do not work well on mobile, so zoom is a gap you fill yourself. Mermaid usage docs: `mermaid.run`/`mermaid.render` return SVG you can post-process; render timing matters when web fonts load, or labels render out of bounds.
- Cost: medium (about 100 lines; small if you only open the SVG in a `<dialog>` and use CSS `transform`/`touch-action`; large if you vendor svg-pan-zoom, not needed).
- Risks: touch (pinch handling via Pointer Events with `touch-action: none` inside the dialog only, otherwise the page cannot scroll); a11y (every diagram needs a text alternative: `aria-labelledby` pointing at a caption or a collapsed text description; the dialog is focus-trapped by `showModal()`, Esc closes, zoom buttons `+ / - / reset` for people who cannot pinch); performance (render mermaid lazily when the diagram nears the viewport via IntersectionObserver, with `startOnLoad:false`; rendering all diagrams at load is the likely biggest JS cost on this page); dark mode (re-render or CSS-variable theme on theme switch).
- Note: `svg.addEventListener("click", () => dlg.showModal())` with `dlg` holding a cloned SVG; apply `viewBox` scaling instead of CSS scale to keep text crisp.

### 12. Print / PDF stylesheet
- Does: the reviewer can print or "Save as PDF" one document or the whole page and get a readable, linkable result: TOC rail removed, details opened, tooltips replaced by footnote-like text, page breaks before h1, tables not split mid-row, URLs of external links shown.
- Evidence: NN/g "Accordions on Desktop" lists printing as a problem for collapsed content unless expanded; MDN print media docs (my fetch of the specific print page returned 404, so the specifics below are from general CSS knowledge [not verified]): `@media print`, `break-inside: avoid`, `@page`.
- Cost: small to medium (CSS only plus one `beforeprint` handler).
- Risks: a11y none; performance: browsers must lay out the full 1 MB, printing takes seconds, warn; content-visibility:auto (see #16) can leave placeholders unpainted in print in some browsers, so force `content-visibility: visible` inside `@media print`; mermaid SVGs must fit page width (`max-width:100%`); dark theme must flip to light (force the light tokens in print).
- Note: `@media print { nav, .toc, .progress, .fab {display:none} details>*{display:block!important} a[href^="http"]::after{content:" (" attr(href) ")"} h1{break-before:page} table,figure,pre{break-inside:avoid} }` and `beforeprint` sets all `details.open=true`, `afterprint` restores.

### 13. Copy buttons on code and on ID/URL blocks
- Does: one click copies a schema, command, SQL, or JSON sample; also useful for copying "R12: text" as a quote.
- Evidence: Material for MkDocs `content.code.copy`, per-block `.copy` / `.no-copy` (fetched 28/10/2026).
- Cost: small.
- Risks: touch (button always visible, not hover-only; at least 24x24 px); a11y (real button with `aria-label="Copy code"`, status in live region "Copied"); clipboard API needs HTTPS (MDN), add the `execCommand` fallback; do not copy line numbers or prompt characters (`$`), use `data-copy` when needed.
- Note: loop `pre > code`, inject a `<button>` in a wrapper `position:relative`, `navigator.clipboard.writeText(code.innerText)` with try/catch fallback.

### 14. Keyboard navigation between sections, IDs and documents
- Does: `]` / `[` next/previous section, `Shift+]` next document, `g` then `t` to TOC, `?` shows the shortcut sheet; power readers move through 6 documents without the mouse.
- Evidence: Material for MkDocs: Previous/Next page links and search key handling are part of its navigation set (page reference). The specific shortcut set is my design; WCAG 2.1.4 constrains how to ship it.
- Cost: medium.
- Risks: a11y (WCAG 2.1.4 Character Key Shortcuts requires turn-off, remap, or focus-only activation for printable-character shortcuts; offer a "Keyboard shortcuts: on/off" toggle in the `?` sheet and store it in `localStorage` inside try/catch, or use only Alt/Ctrl combos); conflicts with screen reader quick-nav keys (single-letter shortcuts collide with NVDA/JAWS browse mode, which is why the off switch matters); ignore events from inputs, selects, textareas, and when modifier keys are held; visible focus ring on the landing heading (`tabindex="-1"` then `focus({preventScroll:true})`).
- Note: one `keydown` listener on `document`, a keymap object, skip when `e.target.closest("input,textarea,select,[contenteditable]")`.

### 15. What-changed highlighting between revisions
- Does: shows what moved since the revision the reader last saw (or since a chosen baseline): a "Changed since 2026-10-20" toggle that marks new/modified blocks in the margin and lists them at the top; essential in a living RFC chain where the source changes and the rest is rethought.
- Evidence: weakest precedent among the 15. Mintlify offers versions selectors (fetched, navigation page); Read the Docs versions/search not verified (page 404). No fetched source demonstrates in-page diffing for a single-file doc. Treat as a design choice for this team, not an industry-tested pattern.
- Cost: large (needs an authoring/build step even if the page has "no build step": e.g. the generator that makes the HTML emits `data-rev="r7"` per block, or a content hash; changes must be computed outside the browser against the previous version). A cheap variant is small to medium: each block carries `data-since="2026-10-26"` set by the author, and the page highlights blocks newer than the date saved in `localStorage` at last visit.
- Risks: privacy none (local only); a11y (do not rely on colour only: use a margin bar plus a visible "Changed" label and `<ins>`/`<del>` semantics if inline diffs are shown); false precision, if hash covers formatting-only edits it will flag noise; `localStorage` can throw or be empty in private windows, wrap in try/catch and treat as "everything unseen".
- Note: start with `data-since` on blocks plus a header toggle "Highlight changes since [date]"; defer real word-level diff until the generator can emit it.

### 16. content-visibility:auto on stage and section blocks (performance enabler, not a reader feature)
- Does: keeps the 1 MB page responsive; the browser skips layout and paint of off-screen sections.
- Evidence: web.dev "content-visibility": a travel-blog demo went from 232 ms to 30 ms initial render (about 7x), expect 50% or more reduction; needs `contain-intrinsic-size` to avoid scrollbar jumps, and off-screen content stays in the DOM and accessibility tree so it is findable and navigable.
- Cost: small.
- Risks: scrollbar jitter if placeholder sizes are wrong (use `contain-intrinsic-size: auto 800px`); forced-layout JS that reads sizes of skipped blocks (scroll spy, backlinks) will force rendering, so query headings only; print must disable it; anchored jumps to IDs in far sections can land slightly off until layout settles, so re-scroll once after `requestAnimationFrame`; mermaid inside skipped blocks renders at the wrong size if measured while skipped, render on intersection.
- Note: `section.doc-section{content-visibility:auto;contain-intrinsic-size:auto 1000px}`; measure with Performance panel before and after.

## Features I would NOT add

| Feature | Why not |
|---|---|
| Hover-only previews of whole sections (Wikipedia-style big cards) | WCAG 1.4.13 burden, hover unavailable on touch (NN/g tooltip guidelines), and a big card blocks reading; a short ID card plus tap-through (#3) is enough. |
| Auto-collapse accordions (open one, close others) for content | NN/g "Accordions on Desktop": auto-collapse makes comparison hard and increases clicks; use independent `<details>` plus Expand all. |
| Collapsing core content (requirements, decisions, risks) | GOV.UK: do not hide what most users need; NN/g: keep crucial information out of collapsed panels. |
| Instant loading / SPA routing (Material `navigation.instant`) | The page is one file; there is nothing to fetch. |
| Single-letter shortcuts without an off switch | WCAG 2.1.4 violation and clashes with screen-reader quick keys; if kept, ship the toggle (#14). |
| Scroll-jacking, parallax, animated scroll-linked effects on content | No reader benefit for a design doc; motion issues; MDN notes scroll-driven animation support is still uneven (use only for the progress bar). |
| Heavy search library or fuzzy/semantic search | 1 MB of text does not justify 30 to 100 KB of library; exact and prefix match plus ID boost covers the real queries. Revisit only if users report misses. |
| In-page comments, "was this helpful" widget | No backend in a static single file; those belong in the Linear/PR review flow. |
| Per-paragraph permalinks | Heading and ID permalinks (#5) cover citations; paragraph anchors add 10,000+ links and DOM weight. |
| Floating collapsed mobile TOC as the only navigation | NN/g TOC article: many users missed collapsed sticky TOCs on mobile; keep a labelled "Contents" button or in-body TOC at top. |
| Browser-native `title` tooltips as the only definitions | Not covered by WCAG 1.4.13 (author cannot control them), invisible on touch, not dismissible by Esc in a consistent way. |
| `interestfor` / interest invokers for tooltips now | Described on MDN as part of the Popover API surface but support was listed as varying; wait for Baseline. |
| Heavy reader preference panel (font family, width, density) | Real value is low versus cost; browser zoom and reader mode exist. A single "wide / narrow content" toggle is the maximum worth considering. |

## Suggested build order (dependency, no dates)

1. Group A, mostly CSS/small JS, no dependency: #1, #5, #9, #13, #16, #12.
2. Group B, needs consistent markup (`data-id`, `data-kind`, `data-status`) which is the real prerequisite: #3, #6, #7, then #2 (search can reuse the same index) and #8.
3. Group C, after Group B: #4 (hooks into jump handler), #10, #11, #14.
4. Group D, needs a generator change: #15.

Cross-cutting prerequisites: unique IDs across the six documents (load-time check), a single `jumpTo(id)` function used by TOC, tooltips, search, backlinks and keyboard (opens ancestor `details`, scrolls, focuses the heading, records history for #4), and `prefers-reduced-motion` respected everywhere.

## Sources (all accessed 28/10/2026)

1. W3C, "Understanding SC 1.4.13: Content on Hover or Focus (Level AA)" - https://www.w3.org/WAI/WCAG21/Understanding/content-on-hover-or-focus.html
2. W3C, "Understanding SC 2.1.4: Character Key Shortcuts" - https://www.w3.org/WAI/WCAG21/Understanding/character-key-shortcuts.html
3. Nielsen Norman Group, "Tooltip Guidelines" - https://www.nngroup.com/articles/tooltip-guidelines/
4. Nielsen Norman Group, "Progressive Disclosure" - https://www.nngroup.com/articles/progressive-disclosure/
5. Nielsen Norman Group, "How Users Read on the Web" - https://www.nngroup.com/articles/how-users-read-on-the-web/ (79% always skimmed, 16% read word by word)
6. Nielsen Norman Group, "Table of Contents" (sticky, current-section highlight, mobile pitfalls, back-to-top) - https://www.nngroup.com/articles/table-of-contents/
7. Nielsen Norman Group, "Accordions on Desktop" - https://www.nngroup.com/articles/accordions-on-desktop/
8. Material for MkDocs, "Setting up navigation" - https://squidfunk.github.io/mkdocs-material/setup/setting-up-navigation/
9. Material for MkDocs, "Reference" - https://squidfunk.github.io/mkdocs-material/reference/
10. Material for MkDocs, "Code blocks" - https://squidfunk.github.io/mkdocs-material/reference/code-blocks/
11. Material for MkDocs, "Tooltips" - https://squidfunk.github.io/mkdocs-material/reference/tooltips/
12. Material for MkDocs, "Data tables" - https://squidfunk.github.io/mkdocs-material/reference/data-tables/
13. Material for MkDocs, "Diagrams" - https://squidfunk.github.io/mkdocs-material/reference/diagrams/
14. Material for MkDocs, "Admonitions" - https://squidfunk.github.io/mkdocs-material/reference/admonitions/
15. Material for MkDocs, "Setting up site search" - https://squidfunk.github.io/mkdocs-material/setup/setting-up-site-search/
16. Docusaurus, "Markdown features: Table of contents" - https://docusaurus.io/docs/markdown-features/toc
17. GOV.UK Design System, "Details" - https://design-system.service.gov.uk/components/details/
18. MDN, "The Details disclosure element" - https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/details
19. MDN, "Popover API" - https://developer.mozilla.org/en-US/docs/Web/API/Popover_API
20. MDN, "CSS scroll-driven animations" - https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Scroll-driven_animations
21. MDN, "Intersection Observer API" - https://developer.mozilla.org/en-US/docs/Web/API/Intersection_Observer_API
22. MDN, "Clipboard.writeText()" - https://developer.mozilla.org/en-US/docs/Web/API/Clipboard/writeText
23. MDN, "History API" - https://developer.mozilla.org/en-US/docs/Web/API/History_API
24. Chrome for Developers, "hidden=until-found" - https://developer.chrome.com/docs/css-ui/hidden-until-found
25. web.dev, "content-visibility: the new CSS property that boosts your rendering performance" - https://web.dev/articles/content-visibility
26. Mermaid, "Usage" - https://mermaid.js.org/config/usage.html
27. Mintlify, "Navigation" - https://www.mintlify.com/docs/organize/navigation (versions/languages/breadcrumbs only; search shortcut and copy-page not confirmed there)

Not obtained: Stripe docs (search returned only third-party descriptions), GitBook expandable block (redirect not followed), Read the Docs search reference (404), W3C target size page (404), MDN @media print page (404). Claims depending on them are marked [not verified] above.
