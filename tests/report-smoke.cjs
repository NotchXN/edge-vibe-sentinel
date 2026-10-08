const fs = require('fs');
const vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
if (scripts.length !== 1) throw new Error('Expected one embedded script');
const script = scripts[0][1];
new vm.Script(script);
const match = script.match(/^const data = (.*);$/m);
const data = JSON.parse(match[1]);
if (data.summary.windows !== 28 || data.summary.events_raised !== 2 || data.summary.events_cleared !== 2) throw new Error('Unexpected demo counts');
if (data.queue.pending !== 22 || data.queue.acknowledged !== 10) throw new Error('Unexpected queue counts');
if (html.includes('/*MONITOR_DATA*/null')) throw new Error('Template data missing');
// A small DOM substitute checks execution and handler wiring, not browser layout.
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.style = {}; this.handlers = {}; this.value = ''; this.textContent = ''; }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { this.children.push(...children); }
  setAttribute(key, value) { this[key] = value; }
  replaceChildren(...children) { this.children = children; }
  addEventListener(event, fn) { this.handlers[event] = fn; }
  scrollIntoView() {}
  click() { if (this.handlers.click) this.handlers.click(); }
}
const nodes = new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(m => [m[1], new Element(m[1])]));
nodes.get('axis').value = 'x';
nodes.get('filter').value = 'all';
const context = {
  document: {
    getElementById(id) { if (!nodes.has(id)) throw new Error('Missing HTML element: ' + id); return nodes.get(id); },
    createElement: tag => new Element(tag),
    createElementNS: (_, tag) => new Element(tag),
  },
  URL: { createObjectURL() { return 'blob:smoke-check'; }, revokeObjectURL() {} },
  Blob,
  setTimeout: fn => fn(),
};
vm.runInNewContext(script, context);
if (nodes.get('rows').children.length !== 28) throw new Error('All-window table did not render');
nodes.get('filter').value = 'DATA_INVALID';
nodes.get('filter').handlers.change();
if (nodes.get('rows').children.length !== 2) throw new Error('Quality filter failed');
nodes.get('filter').value = 'all';
nodes.get('search').value = 'window-072';
nodes.get('search').handlers.input();
if (nodes.get('rows').children.length !== 1) throw new Error('Search failed');
nodes.get('rows').children[0].children[6].children[0].click();
if (!nodes.get('selected-status').textContent.startsWith('ALARM')) throw new Error('Inspect action failed');
nodes.get('axis').value = 'z';
nodes.get('axis').handlers.change();
if (nodes.get('axis-label').textContent !== 'Z AXIS') throw new Error('Axis selector failed');
nodes.get('selection').value = '27';
nodes.get('selection').handlers.change();
if (!nodes.get('selected-status').textContent.startsWith('NORMAL_WINDOW')) throw new Error('Window selector failed');
nodes.get('export').click();
console.log(JSON.stringify({script_syntax:'passed', embedded_windows:28, embedded_events:4, dom_smoke:'passed', browser_visual_test:'not performed'}));
