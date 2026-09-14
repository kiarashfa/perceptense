/**
 * Prepare stylesheets for the build.
 *
 * 1. Publishes the shared stylesheet as a static file. It is linked explicitly
 *    from <head> rather than imported, because bundled CSS is emitted in chunk
 *    order and the shared sheet must come first: module rules are written to
 *    win ties against it, exactly as they did when they were inline <style>
 *    blocks after a <link> to shared.css.
 * 2. Namespaces each module stylesheet under an ancestor class so rules cannot
 *    collide between modules and still reach elements built at runtime.
 *
 *   node tools/build-styles.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import postcss from 'postcss';
import selectorParser from 'postcss-selector-parser';

const ROOT = path.resolve(import.meta.dirname, '..');
// Concatenated in this order into one linked stylesheet: the design system
// first, then the site chrome that builds on its tokens.
const SHARED_PARTS = [
  path.join(ROOT, 'src/styles/fonts.css'),
  path.join(ROOT, 'src/styles/shared.css'),
  path.join(ROOT, 'src/styles/components.css'),
  path.join(ROOT, 'src/styles/icons-base.css'),
  path.join(ROOT, 'src/styles/chrome.css'),
];
const SHARED_OUT = path.join(ROOT, 'public/styles/shared.css');
const IN_DIR = path.join(ROOT, 'src/styles/modules-src');
const OUT_DIR = path.join(ROOT, 'src/styles/modules');

const RAW_AT = new Set(['keyframes', 'font-face', 'property', 'counter-style']);
const DOC_TAGS = new Set(['html', 'body']);
const SELF_CLASSES = new Set(['page-wrap']);

function compounds(sel) {
  const groups = [[]];
  for (const n of sel.nodes) {
    if (n.type === 'combinator') groups.push([]);
    else groups[groups.length - 1].push(n);
  }
  return groups;
}

function transform(selText, ns) {
  return selectorParser((root) => {
    root.each((sel) => {
      const first = (compounds(sel)[0] || []).filter((n) => n.type !== 'comment');
      if (!first.length) return;

      const isRoot = first.length === 1 && first[0].type === 'pseudo'
        && first[0].value.toLowerCase() === ':root';
      const isDocTag = first[0].type === 'tag' && DOC_TAGS.has(first[0].value.toLowerCase());
      const isSelf = first.some((n) => n.type === 'class' && SELF_CLASSES.has(n.value));

      // :where() adds no specificity, so namespacing never changes which rule
      // wins. A bare class prefix would outrank shared.css and silently flip
      // the cascade.
      const nsNode = () => selectorParser.pseudo({
        value: ':where',
        nodes: [selectorParser.selector({
          nodes: [selectorParser.className({ value: ns })],
        })],
      });

      if (isRoot) {
        // Left alone. Each page loads only its own module stylesheet, so these
        // custom properties cannot leak, and retargeting them would move
        // --accent closer to the content than the shared html[data-module] rule.
        return;
      }
      if (isSelf) {
        sel.insertBefore(first[0], nsNode());
        return;
      }
      if (isDocTag) {
        const anchor = sel.nodes[first.length + 1];
        if (!anchor) {
          sel.removeAll();
          sel.append(selectorParser.className({ value: ns }));
          return;
        }
        sel.insertBefore(anchor, nsNode());
        sel.insertBefore(anchor, selectorParser.combinator({ value: ' ' }));
        return;
      }
      sel.insertBefore(sel.nodes[0], selectorParser.combinator({ value: ' ' }));
      sel.insertBefore(sel.nodes[0], nsNode());
    });
  }).processSync(selText);
}

const plugin = (ns) => ({
  postcssPlugin: 'namespace',
  Once(root) {
    root.walkRules((rule) => {
      const at = rule.parent?.type === 'atrule'
        ? rule.parent.name.toLowerCase().replace(/^-[a-z]+-/, '') : null;
      if (at && RAW_AT.has(at)) return;
      rule.selector = rule.selectors.map((s) => transform(s, ns)).join(',\n');
    });
  },
});

// --- 1. publish the shared stylesheet ---
const shared = SHARED_PARTS.map((f) => fs.readFileSync(f, 'utf8')).join('\n\n');
fs.mkdirSync(path.dirname(SHARED_OUT), { recursive: true });
fs.writeFileSync(SHARED_OUT, shared, 'utf8');
const sharedHash = crypto.createHash('sha256').update(shared).digest('hex').slice(0, 8);

// --- 2. namespace the module stylesheets ---
fs.mkdirSync(OUT_DIR, { recursive: true });
const files = fs.existsSync(IN_DIR)
  ? fs.readdirSync(IN_DIR).filter((f) => f.endsWith('.css')).sort() : [];
let rules = 0;
for (const f of files) {
  const ns = `m-${f.replace(/\.css$/, '')}`;
  const out = postcss([plugin(ns)])
    .process(fs.readFileSync(path.join(IN_DIR, f), 'utf8'), { from: undefined });
  fs.writeFileSync(path.join(OUT_DIR, f), out.css, 'utf8');
  out.root.walkRules(() => rules++);
}

console.log(`shared stylesheet published (${(shared.length / 1024).toFixed(1)} KB, hash ${sharedHash})`);
console.log(`namespaced ${files.length} module stylesheets (${rules} rules)`);
