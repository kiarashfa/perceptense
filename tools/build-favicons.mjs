/**
 * Render the favicon set from its single SVG source.
 *
 * The ICO and the manifest icons keep the rounded tile. The apple-touch icon is
 * square and full-bleed, because iOS applies its own mask and needs an opaque
 * image.
 *
 *   node tools/build-favicons.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import sharp from 'sharp';

const ROOT = path.resolve(import.meta.dirname, '..');
const DIR = path.join(ROOT, 'public/assets/favicons');
const GRID = 64;

const source = fs.readFileSync(path.join(DIR, 'favicon.svg'), 'utf8');
const rounded = Buffer.from(source);
const square = Buffer.from(source.replace(/ rx="[\d.]+"/, ''));

const png = (svg, size) =>
  sharp(svg, { density: (72 * size) / GRID }).resize(size, size).png({ compressionLevel: 9 }).toBuffer();

/** An ICO file whose entries are PNG-compressed images. */
function ico(entries) {
  const header = Buffer.alloc(6);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(entries.length, 4);
  let offset = 6 + 16 * entries.length;
  const directory = entries.map(({ size, data }) => {
    const e = Buffer.alloc(16);
    e.writeUInt8(size >= 256 ? 0 : size, 0);
    e.writeUInt8(size >= 256 ? 0 : size, 1);
    e.writeUInt16LE(1, 4);
    e.writeUInt16LE(32, 6);
    e.writeUInt32LE(data.length, 8);
    e.writeUInt32LE(offset, 12);
    offset += data.length;
    return e;
  });
  return Buffer.concat([header, ...directory, ...entries.map((e) => e.data)]);
}

const icoSizes = [16, 32, 48];
const icoEntries = [];
for (const size of icoSizes) icoEntries.push({ size, data: await png(rounded, size) });
fs.writeFileSync(path.join(DIR, 'favicon.ico'), ico(icoEntries));

fs.writeFileSync(path.join(DIR, 'apple-touch-icon.png'), await png(square, 180));
for (const size of [192, 512]) {
  fs.writeFileSync(path.join(DIR, `icon-${size}.png`), await png(rounded, size));
}

console.log('favicons: favicon.ico, apple-touch-icon.png, icon-192.png, icon-512.png');
