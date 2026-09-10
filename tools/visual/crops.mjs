/**
 * Locate the vertical bands where two screenshots differ, then emit a compact
 * side-by-side contact sheet (legacy | ported) for each band.
 *
 * Looking at a whole 9000px page is useless; this shows only the regions that
 * actually changed, at a size worth reading.
 *
 *   node visual/crops.mjs <labelA> <labelB> <shotName> [maxBands]
 */
import fs from 'node:fs';
import path from 'node:path';
import { PNG } from 'pngjs';

const [a, b, shot, maxBandsArg] = process.argv.slice(2);
const maxBands = Number(maxBandsArg ?? 3);
const imgA = PNG.sync.read(fs.readFileSync(path.join('visual', 'shots', a, shot)));
const imgB = PNG.sync.read(fs.readFileSync(path.join('visual', 'shots', b, shot)));

const w = Math.min(imgA.width, imgB.width);
const h = Math.min(imgA.height, imgB.height);

// per-row difference count
const rowDiff = new Array(h).fill(0);
for (let y = 0; y < h; y++) {
  let n = 0;
  for (let x = 0; x < w; x++) {
    const ia = (imgA.width * y + x) << 2;
    const ib = (imgB.width * y + x) << 2;
    if (Math.abs(imgA.data[ia] - imgB.data[ib]) > 12 ||
        Math.abs(imgA.data[ia + 1] - imgB.data[ib + 1]) > 12 ||
        Math.abs(imgA.data[ia + 2] - imgB.data[ib + 2]) > 12) n++;
  }
  rowDiff[y] = n;
}

// group contiguous differing rows into bands, merging gaps under 40px
const bands = [];
let start = -1, gap = 0;
for (let y = 0; y < h; y++) {
  if (rowDiff[y] > w * 0.005) {
    if (start < 0) start = y;
    gap = 0;
  } else if (start >= 0) {
    if (++gap > 40) { bands.push([start, y - gap]); start = -1; gap = 0; }
  }
}
if (start >= 0) bands.push([start, h - 1]);

bands.sort((p, q) => (q[1] - q[0]) - (p[1] - p[0]));
console.log(`${shot}: ${imgA.height}px vs ${imgB.height}px, ${bands.length} differing band(s)`);
for (const [s, e] of bands.slice(0, 8)) {
  const rows = rowDiff.slice(s, e + 1).reduce((t, v) => t + v, 0);
  console.log(`   y ${s}-${e}  (${e - s + 1}px tall, ${rows} differing pixels)`);
}

const outDir = path.join('visual', 'crops');
fs.mkdirSync(outDir, { recursive: true });
bands.slice(0, maxBands).forEach(([s, e], i) => {
  const pad = 30;
  const y0 = Math.max(0, s - pad);
  const bh = Math.min(h - y0, e - s + 1 + pad * 2);
  const sheet = new PNG({ width: w * 2 + 12, height: bh });
  // fill separator
  for (let p = 0; p < sheet.data.length; p += 4) {
    sheet.data[p] = 255; sheet.data[p + 1] = 0; sheet.data[p + 2] = 0; sheet.data[p + 3] = 255;
  }
  PNG.bitblt(imgA, sheet, 0, y0, w, bh, 0, 0);
  PNG.bitblt(imgB, sheet, 0, y0, w, bh, w + 12, 0);
  const f = path.join(outDir, `${shot.replace('.png', '')}__band${i}_y${y0}.png`);
  fs.writeFileSync(f, PNG.sync.write(sheet));
  console.log(`   wrote ${f}`);
});
