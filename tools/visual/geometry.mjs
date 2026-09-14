/**
 * Compare the rendered geometry of every module, element by element.
 *
 * Pixel diffing is too noisy to gate on: a single 1px shift near the top of a
 * page lights up the anti-aliasing of every line below it. Comparing each
 * element's box instead is precise, immune to font rendering noise, and names
 * the exact element that moved.
 *
 *   node visual/geometry.mjs <legacy.json> <ported.json> [tolerancePx]
 */
import { chromium } from 'playwright';
import fs from 'node:fs';

const [aFile, bFile, tolArg] = process.argv.slice(2);
const TOL = Number(tolArg ?? 1);
const A = JSON.parse(fs.readFileSync(aFile, 'utf8'));
const B = new Map(JSON.parse(fs.readFileSync(bFile, 'utf8')).map((r) => [r.slug, r.url]));

const DETERMINISM = () => {
  let seed = 0x2f6e2b1;
  Math.random = () => { seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5; return ((seed >>> 0) % 1e6) / 1e6; };
  const FIXED = new Date('2026-01-01T12:00:00Z').getTime();
  const R = Date;
  Date = class extends R {
    constructor(...a) { return a.length ? new R(...a) : new R(FIXED); }
    static now() { return FIXED; }
  };
  Date.UTC = R.UTC; Date.parse = R.parse;
};

const SNAPSHOT = () => {
  const wrap = document.querySelector('.page-wrap');
  if (!wrap) return null;
  const top = wrap.getBoundingClientRect().top + window.scrollY;
  const out = [];
  // script/style carry no layout; the port relocates them. They are filtered
  // out before indexing so their absence does not shift every sibling's path.
  const SKIP = new Set(['SCRIPT', 'STYLE', 'TEMPLATE', 'NOSCRIPT']);
  const kids = (el) => [...el.children].filter((c) => !SKIP.has(c.tagName));
  const walk = (el, path) => {
    const b = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const cls = (el.className && el.className.baseVal !== undefined
      ? el.className.baseVal : el.className || '').toString();
    out.push({
      path, tag: el.tagName.toLowerCase(), cls: cls.trim().slice(0, 40),
      w: Math.round(b.width), h: Math.round(b.height),
      y: Math.round(b.top + window.scrollY - top),
      fs: cs.fontSize, color: cs.color, bg: cs.backgroundColor,
      pad: cs.padding, mar: cs.margin, radius: cs.borderRadius, disp: cs.display,
    });
    kids(el).forEach((c, i) => walk(c, path + '/' + i));
  };
  kids(wrap).forEach((c, i) => walk(c, String(i)));
  return out;
};

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: 'light' });
await ctx.addInitScript(DETERMINISM);

const snap = async (url) => {
  const page = await ctx.newPage();
  await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 });
  await page.evaluate(() => document.fonts && document.fonts.ready);
  const r = await page.evaluate(SNAPSHOT);
  await page.close();
  return r;
};

const VISUAL = ['fs', 'color', 'bg', 'pad', 'mar', 'radius', 'disp'];
let clean = 0;
const report = [];

for (const { slug, url } of A) {
  const bUrl = B.get(slug);
  if (!bUrl) { report.push({ slug, note: 'missing in second set' }); continue; }
  const [a, b] = [await snap(url), await snap(bUrl)];
  if (!a || !b) { report.push({ slug, note: 'no .page-wrap' }); continue; }

  const mb = new Map(b.map((e) => [e.path, e]));
  const issues = [];
  for (const ea of a) {
    const eb = mb.get(ea.path);
    if (!eb) { issues.push({ ...ea, why: 'missing' }); continue; }
    const dw = eb.w - ea.w, dh = eb.h - ea.h;
    const styleDiff = VISUAL.filter((k) => ea[k] !== eb[k]);
    if (Math.abs(dw) > TOL || Math.abs(dh) > TOL || styleDiff.length) {
      issues.push({ ...ea, dw, dh, why: styleDiff.length ? styleDiff.map((k) => `${k}: ${ea[k]} -> ${eb[k]}`).join('; ') : 'size' });
    }
  }
  // report only the outermost element of each divergent subtree
  const roots = [];
  for (const i of issues) if (!roots.some((r) => i.path.startsWith(r.path + '/'))) roots.push(i);

  if (a.length !== b.length) {
    report.push({ slug, note: `element count ${a.length} -> ${b.length}`, roots });
  } else if (roots.length) {
    report.push({ slug, roots });
  } else clean++;
}
await browser.close();

console.log(`modules compared      : ${A.length}`);
console.log(`geometrically clean   : ${clean}`);
console.log(`with divergences      : ${report.length}   (tolerance ${TOL}px)\n`);
if (report.length) {
  console.log('divergent: ' + report.map((r) => r.slug).join(' '));
  console.log();
}
for (const r of report.slice(0, 60)) {
  console.log(`  ${r.slug}${r.note ? '  [' + r.note + ']' : ''}`);
  for (const x of (r.roots || []).slice(0, 200)) {
    console.log(`      y=${String(x.y).padStart(5)} ${x.tag}.${x.cls}  dw=${x.dw ?? '?'} dh=${x.dh ?? '?'}  ${x.why}`);
  }
}
process.exit(report.length ? 1 : 0);
