import { JSDOM } from 'jsdom';
import fs from 'fs';
const dom = new JSDOM('<!doctype html><body></body>');
globalThis.window = dom.window; globalThis.document = dom.window.document;
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });
globalThis.DOMParser = dom.window.DOMParser; globalThis.Element = dom.window.Element;
const { default: mermaid } = await import('mermaid');
mermaid.initialize({ startOnLoad: false });
const text = fs.readFileSync(process.argv[2], 'utf8').split('\r\n').join('\n');
const blocks = [...text.matchAll(/```mermaid\n([\s\S]*?)```/g)].map(m => m[1]);
let ok = 0; const bad = [];
for (const [i, b] of blocks.entries()) { try { await mermaid.parse(b); ok++; } catch (e) { bad.push(i + 1); } }
console.log(`${ok}/${blocks.length} parse OK`, bad.length ? 'failed: ' + bad.join(',') : '');
