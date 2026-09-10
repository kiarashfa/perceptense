/**
 * Compare two screenshot sets and report per-page pixel differences.
 *
 *   node visual/compare.mjs <labelA> <labelB> [maxPercent]
 *
 * Images of differing height are compared over their shared region and the
 * height delta is reported separately, so a page that merely grew taller is not
 * mistaken for one that changed everywhere.
 */
import fs from 'node:fs';
import path from 'node:path';
import { PNG } from 'pngjs';
import pixelmatch from 'pixelmatch';

const [a, b, maxPctArg] = process.argv.slice(2);
const maxPct = Number(maxPctArg ?? 0.1);
const dirA = path.join('visual', 'shots', a);
const dirB = path.join('visual', 'shots', b);
const diffDir = path.join('visual', 'diff', `${a}__vs__${b}`);
fs.mkdirSync(diffDir, { recursive: true });

const filesA = new Set(fs.readdirSync(dirA).filter((f) => f.endsWith('.png')));
const filesB = new Set(fs.readdirSync(dirB).filter((f) => f.endsWith('.png')));
const onlyA = [...filesA].filter((f) => !filesB.has(f));
const onlyB = [...filesB].filter((f) => !filesA.has(f));
const shared = [...filesA].filter((f) => filesB.has(f)).sort();

const rows = [];
for (const f of shared) {
  const imgA = PNG.sync.read(fs.readFileSync(path.join(dirA, f)));
  const imgB = PNG.sync.read(fs.readFileSync(path.join(dirB, f)));
  const w = Math.min(imgA.width, imgB.width);
  const h = Math.min(imgA.height, imgB.height);

  const crop = (img) => {
    if (img.width === w && img.height === h) return img;
    const out = new PNG({ width: w, height: h });
    PNG.bitblt(img, out, 0, 0, w, h, 0, 0);
    return out;
  };
  const ca = crop(imgA);
  const cb = crop(imgB);
  const diff = new PNG({ width: w, height: h });
  const changed = pixelmatch(ca.data, cb.data, diff.data, w, h, {
    threshold: 0.12,
    includeAA: false,
  });
  const pct = (changed / (w * h)) * 100;
  const dH = imgB.height - imgA.height;
  const dW = imgB.width - imgA.width;

  if (pct > maxPct || dW !== 0) {
    fs.writeFileSync(path.join(diffDir, f), PNG.sync.write(diff));
  }
  rows.push({ f, pct, changed, dH, dW });
}

rows.sort((x, y) => y.pct - x.pct);
const bad = rows.filter((r) => r.pct > maxPct || r.dW !== 0);

console.log(`compared ${shared.length} screenshots  (${a} -> ${b})`);
if (onlyA.length) console.log(`  only in ${a}: ${onlyA.length}`);
if (onlyB.length) console.log(`  only in ${b}: ${onlyB.length}`);
console.log(`  threshold: ${maxPct}% of pixels\n`);

const identical = rows.filter((r) => r.changed === 0).length;
console.log(`  pixel-identical      : ${identical}/${rows.length}`);
console.log(`  within threshold     : ${rows.length - bad.length}/${rows.length}`);
console.log(`  over threshold       : ${bad.length}\n`);

if (bad.length) {
  console.log('  largest differences:');
  for (const r of bad.slice(0, 20)) {
    const size = r.dW !== 0 ? ` width${r.dW > 0 ? '+' : ''}${r.dW}` : '';
    const hh = r.dH !== 0 ? ` height${r.dH > 0 ? '+' : ''}${r.dH}` : '';
    console.log(`    ${r.pct.toFixed(3).padStart(7)}%  ${r.f}${size}${hh}`);
  }
  console.log(`\n  diff images written to ${diffDir}`);
} else {
  console.log('  no page exceeds the threshold');
}

const heightOnly = rows.filter((r) => r.pct <= maxPct && r.dH !== 0);
if (heightOnly.length) {
  console.log(`\n  ${heightOnly.length} page(s) changed height only (content region grew/shrank)`);
}

process.exit(bad.length ? 1 : 0);
