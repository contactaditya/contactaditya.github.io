#!/usr/bin/env node
//
// prerender.js — keep index.html's static markup in step with its data arrays.
//
//   node prerender.js          rewrite index.html with freshly rendered markup
//   node prerender.js --check  verify only; exit 1 if anything is out of step
//
// Why this exists. Every table and grid in index.html is written into the HTML
// as static rows so the evidence is readable without JavaScript: by a crawler, a
// text extractor, a printer, or a reader with scripting off. The page's own
// script then repaints the same containers on load and takes over sorting and
// filtering. That means a data edit which is not followed by a re-render leaves
// the static copy stale — and the staleness is invisible in a browser, because
// the script overwrites it the moment the page loads.
//
// So: run `node prerender.js` after editing any array, and `node prerender.js
// --check` in CI or before publishing. The check compares what the renderers
// produce against what the file contains, and names every container that differs.
//
const fs = require('fs');
const path = require('path');

const FILE = path.join(__dirname, 'index.html');
const CHECK_ONLY = process.argv.includes('--check');

// ---------------------------------------------------------------- DOM stub
// Enough of a document for the page's renderers to run under Node. Each
// getElementById returns a recording node; nothing is laid out or displayed.
function makeStub() {
  const html = {}, text = {}, nodes = {};
  const node = id => ({
    set innerHTML(v) { html[id] = v; },
    get innerHTML() { return html[id] || ''; },
    set textContent(v) { text[id] = v; },
    get textContent() { return text[id] || ''; },
    style: {}, className: '',
    setAttribute() {}, getAttribute() { return null; }, appendChild() {},
    querySelector() { return null; }, querySelectorAll() { return []; },
    addEventListener() {},
    classList: { toggle() {}, add() {}, remove() {} },
    closest() { return null; }, offsetTop: 0,
    parentNode: { removeChild() {} }, children: []
  });
  const get = id => (nodes[id] = nodes[id] || node(id));
  return {
    html, text,
    document: {
      getElementById: get,
      querySelector: () => get('_q'),
      querySelectorAll: () => [],
      createElement: () => node('_new'),
      addEventListener() {},
      documentElement: get('_root'),
      body: get('_body'),
      readyState: 'complete'
    },
    window: {
      addEventListener() {}, scrollY: 0,
      matchMedia: () => ({ matches: false, addEventListener() {} })
    },
    localStorage: { getItem() { return null; }, setItem() {} }
  };
}

// Run the page's own script and collect what each container was filled with.
function render(source) {
  const script = source.match(/<script>([\s\S]*)<\/script>/);
  if (!script) throw new Error('no <script> block found in index.html');
  const stub = makeStub();
  const warnings = [];
  const realWarn = console.warn;
  global.document = stub.document;
  global.window = stub.window;
  global.localStorage = stub.localStorage;
  console.warn = (...a) => warnings.push(a.join(' '));
  try {
    new Function(script[1])();
  } finally {
    console.warn = realWarn;
  }
  return { html: stub.html, text: stub.text, warnings };
}

// ------------------------------------------------------------ tag matching
// Find a container's inner range by walking tags to the matching close, so
// nested elements of the same tag do not truncate the match.
function range(source, id) {
  const open = new RegExp('<(\\w+)[^>]*\\bid="' + id + '"[^>]*>').exec(source);
  if (!open) return null;
  const tag = open[1];
  const start = open.index + open[0].length;
  const scan = new RegExp('</?' + tag + '\\b[^>]*>', 'g');
  scan.lastIndex = start;
  let depth = 1, m;
  while ((m = scan.exec(source))) {
    depth += m[0][1] === '/' ? -1 : 1;
    if (!depth) return { start, end: m.index };
  }
  return null;
}

// Counters set via textContent that are derived from the data. `theme` and
// `count` are interaction state, not evidence, so they are left alone.
const SKIP_TEXT = new Set(['theme', 'count']);

// ---------------------------------------------------------------------- go
let source = fs.readFileSync(FILE, 'utf8');
const { html, text, warnings } = render(source);

const stale = [];
let written = 0;

const apply = (id, value) => {
  if (id.startsWith('_')) return;
  const at = range(source, id);
  if (!at) return;                       // container not in the markup
  if (source.slice(at.start, at.end) === value) return;
  stale.push(id);
  if (!CHECK_ONLY) {
    source = source.slice(0, at.start) + value + source.slice(at.end);
    written++;
  }
};

Object.keys(html).forEach(id => apply(id, html[id]));
Object.keys(text).forEach(id => { if (!SKIP_TEXT.has(id)) apply(id, text[id]); });

if (warnings.length) {
  console.error('\nThe page reported problems while rendering:');
  warnings.forEach(w => console.error('  ' + w));
}

if (CHECK_ONLY) {
  if (stale.length) {
    console.error('\nStatic markup is out of step in ' + stale.length +
                  ' container(s):\n  ' + stale.join('\n  ') +
                  '\n\nRun `node prerender.js` and commit the result.\n');
    process.exit(1);
  }
  console.log('Static markup is in step with the data arrays.');
  if (warnings.length) process.exit(1);
  process.exit(0);
}

if (written) {
  fs.writeFileSync(FILE, source);
  console.log('Re-rendered ' + written + ' container(s): ' + stale.join(', '));
} else {
  console.log('Nothing to do; static markup was already in step.');
}
if (warnings.length) process.exit(1);
