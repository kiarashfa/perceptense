/**
 * Render the Open Graph card for every module and one for the site.
 *
 * Text is set in the site's own IBM Plex Sans and written into the SVG as glyph
 * outlines rather than <text>. SVG text is rasterised by whatever font stack the
 * host provides (DirectWrite on Windows, fontconfig on Linux), so the same card
 * would differ from machine to machine; outlines render identically everywhere.
 *
 *   node tools/build-og.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import * as fontkit from 'fontkit';
import sharp from 'sharp';

const ROOT = path.resolve(import.meta.dirname, '..');
const OUT = path.join(ROOT, 'public/og');

const W = 1200;
const H = 630;
const PAD = 88;
const TEXT_W = W - PAD * 2;

const INK = '#1a1a18';
const MUTED = '#5f5e5a';
const FAINT = '#888780';
const PAPER = '#ffffff';
const RULE = '#e4e3de';
const SITE_ACCENT = '#4E99A3';

const readJson = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), 'utf8'));
const modules = readJson('src/data/modules.json');
const categories = readJson('src/data/categories.json');
const site = readJson('src/data/site.json');

// Static instances of the two subsets the site serves, cut by build_og_fonts.py.
const FONT_CACHE = path.join(ROOT, 'node_modules/.cache/og-fonts');
const SUBSETS = ['ibm-plex-sans-latin', 'ibm-plex-sans-latin-ext'];
const faces = new Map();

function face(index, weight) {
  const key = `${SUBSETS[index]}-${weight}`;
  if (!faces.has(key)) faces.set(key, fontkit.openSync(path.join(FONT_CACHE, `${key}.ttf`)));
  return faces.get(key);
}

/** Split text into runs, each set in the first subset that covers it. */
function runs(text) {
  const out = [];
  for (const ch of text) {
    const index = SUBSETS.findIndex((_, i) => face(i, 400).hasGlyphForCodePoint(ch.codePointAt(0)));
    if (index < 0) {
      const cp = ch.codePointAt(0).toString(16).toUpperCase().padStart(4, '0');
      throw new Error(`no glyph for U+${cp} in ${JSON.stringify(text)}`);
    }
    if (out.length && out.at(-1).index === index) out.at(-1).text += ch;
    else out.push({ index, text: ch });
  }
  return out;
}

/** Lay out one line; returns its advance width and outline path data. */
function shape(text, size, weight, tracking = 0) {
  let x = 0;
  const d = [];
  for (const run of runs(text)) {
    const f = face(run.index, weight);
    const scale = size / f.unitsPerEm;
    const { glyphs, positions } = f.layout(run.text);
    glyphs.forEach((glyph, i) => {
      const p = positions[i];
      const outline = glyph.path
        .scale(scale, -scale)
        .translate(x + p.xOffset * scale, -p.yOffset * scale)
        .toSVG();
      if (outline) d.push(outline);
      x += p.xAdvance * scale + tracking * size;
    });
  }
  return { width: x - tracking * size, d: d.join('') };
}

function wrap(text, size, weight) {
  const lines = [];
  let line = '';
  for (const word of text.split(/\s+/)) {
    const next = line ? `${line} ${word}` : word;
    if (line && shape(next, size, weight).width > TEXT_W) {
      lines.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) lines.push(line);
  return lines;
}

/** Largest size at which the text fits the width in at most maxLines lines. */
function fitWidth(text, sizes, weight, maxLines) {
  for (const size of sizes) {
    const lines = wrap(text, size, weight);
    if (lines.length <= maxLines && lines.every((l) => shape(l, size, weight).width <= TEXT_W)) {
      return { size, lines };
    }
  }
  return null;
}

const NAME = { sizes: [88, 80, 72, 64, 56], weight: 600, leading: 1.12, maxLines: 2 };
const BLURB = { sizes: [38, 34, 30, 27], weight: 400, leading: 1.36, maxLines: 3 };
const BODY_TOP = 236;
const BODY_BOTTOM = 468;
const GAP = 22;

const blockHeight = (b, spec) => b.lines.length * b.size * spec.leading;

/** Fit headline and blurb together into the body area, shrinking both as needed. */
function fitBody(name, blurb) {
  for (const nameSize of NAME.sizes) {
    const head = fitWidth(name, [nameSize], NAME.weight, NAME.maxLines);
    if (!head) continue;
    const room = BODY_BOTTOM - BODY_TOP - blockHeight(head, NAME) - GAP;
    for (const blurbSize of BLURB.sizes) {
      const sub = fitWidth(blurb, [blurbSize], BLURB.weight, BLURB.maxLines);
      if (sub && blockHeight(sub, BLURB) <= room) return { head, sub };
    }
  }
  throw new Error(`cannot fit ${JSON.stringify(name)} on a card`);
}

function lines(block, spec, top, fill) {
  return block.lines.map((text, i) => {
    const lineTop = top + i * block.size * spec.leading;
    const baseline = lineTop + block.size * (spec.leading - 1) / 2 + block.size * 0.8;
    const { d } = shape(text, block.size, spec.weight);
    return `<path transform="translate(${PAD} ${baseline.toFixed(1)})" fill="${fill}" d="${d}"/>`;
  }).join('');
}

function icon(faIcon, x, y, size, fill, opacity = 1) {
  const [style, name] = faIcon.split(/\s+/).map((c) => c.replace(/^fa-/, ''));
  const file = [style, 'solid', 'brands']
    .map((dir) => path.join(ROOT, 'src/icons', dir, `${name}.svg`))
    .find((p) => fs.existsSync(p));
  if (!file) throw new Error(`no local icon for ${faIcon}`);
  const svg = fs.readFileSync(file, 'utf8');
  const viewBox = svg.match(/viewBox="([^"]+)"/)[1];
  const inner = svg.replace(/^[\s\S]*?<svg[^>]*>|<\/svg>\s*$/g, '').replaceAll('currentColor', fill);
  return `<svg x="${x}" y="${y}" width="${size}" height="${size}" viewBox="${viewBox}" opacity="${opacity}">${inner}</svg>`;
}

function card({ accent, faIcon, overline, name, blurb, footer }) {
  const { head, sub } = fitBody(name, blurb);
  const over = shape(overline.toUpperCase(), 26, 600, 0.1);
  const overX = faIcon ? PAD + 64 + 24 : PAD;
  const brand = shape(site.brand, 32, 600);
  const right = footer ? shape(footer, 28, 400) : null;
  const subTop = BODY_TOP + blockHeight(head, NAME) + GAP;

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
  <rect width="${W}" height="${H}" fill="${PAPER}"/>
  <rect width="${W}" height="14" fill="${accent}"/>
  ${faIcon ? icon(faIcon, W - PAD - 300, 96, 340, accent, 0.07) : ''}
  ${faIcon ? icon(faIcon, PAD, 104, 64, accent) : ''}
  <path transform="translate(${overX} 146)" fill="${accent}" d="${over.d}"/>
  ${lines(head, NAME, BODY_TOP, INK)}
  ${lines(sub, BLURB, subTop, MUTED)}
  <rect x="${PAD}" y="500" width="${TEXT_W}" height="2" fill="${RULE}"/>
  <path transform="translate(${PAD} 562)" fill="${INK}" d="${brand.d}"/>
  ${right ? `<path transform="translate(${(W - PAD - right.width).toFixed(1)} 560)" fill="${FAINT}" d="${right.d}"/>` : ''}
</svg>`;
}

async function render(svg, file) {
  await sharp(Buffer.from(svg)).png({ compressionLevel: 9 }).toFile(path.join(OUT, file));
}

fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(OUT, { recursive: true });

const label = new Map(categories.map((c) => [c.id, c.label]));

await render(card({
  accent: SITE_ACCENT,
  overline: `${modules.length} interactive modules`,
  name: site.tagline,
  blurb: site.description,
}), 'site.png');

for (const m of modules) {
  await render(card({
    accent: m.accent,
    faIcon: m.faIcon,
    overline: `Module ${m.id}`,
    name: m.name,
    blurb: m.subtitle,
    footer: label.get(m.category),
  }), `${m.slug}.png`);
}

console.log(`og cards: ${modules.length + 1} -> public/og/`);
