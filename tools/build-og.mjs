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

// The GitHub preview is its own card: dark, abstract, built from the mark.
const GH_W = 1280;
const GH_H = 640;
const GH_PAPER = '#10212E';
const GH_INK = '#F4F1E6';
const GH_MUTED = '#9FB3C0';
const GH_CREAM = '#EADFB8';

const readJson = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), 'utf8'));
const modules = readJson('src/data/modules.json');
const categories = readJson('src/data/categories.json');
const site = readJson('src/data/site.json');
const config = fs.readFileSync(path.join(ROOT, 'astro.config.mjs'), 'utf8');
const SITE_HOST = config.match(/site:\s*'https?:\/\/([^']+)'/)[1];
const SITE_BASE = config.match(/base:\s*'([^']*)'/)[1];
site.description = site.description.replaceAll('{modules}', String(modules.length));

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

function wrap(text, size, weight, maxWidth = TEXT_W) {
  const lines = [];
  let line = '';
  for (const word of text.split(/\s+/)) {
    const next = line ? `${line} ${word}` : word;
    if (line && shape(next, size, weight).width > maxWidth) {
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

/** The site mark, read from the same file the browser tab uses. */
function mark(x, y, size, opacity = 1) {
  const svg = fs.readFileSync(path.join(ROOT, 'public/assets/favicons/favicon.svg'), 'utf8');
  const inner = svg.replace(/^[\s\S]*?<svg[^>]*>|<\/svg>\s*$/g, '');
  return `<svg x="${x}" y="${y}" width="${size}" height="${size}" viewBox="0 0 64 64" opacity="${opacity}">${inner}</svg>`;
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
  ${mark(PAD, 530, 46)}
  <path transform="translate(${PAD + 64} 562)" fill="${INK}" d="${brand.d}"/>
  ${right ? `<path transform="translate(${(W - PAD - right.width).toFixed(1)} 560)" fill="${FAINT}" d="${right.d}"/>` : ''}
</svg>`;
}

async function render(svg, file) {
  await sharp(Buffer.from(svg)).png({ compressionLevel: 9 }).toFile(path.join(OUT, file));
}

fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(OUT, { recursive: true });

const label = new Map(categories.map((c) => [c.id, c.label]));

const siteCard = card({
  accent: SITE_ACCENT,
  overline: `${modules.length} interactive modules`,
  name: site.tagline,
  blurb: site.description,
});
await render(siteCard, 'site.png');

/**
 * GitHub's social preview: 1280x640, cropped by up to 40 px on each side, so
 * nothing that matters sits near an edge. Unlike the module cards it is dark and
 * abstract, drawn from the mark's own geometry rather than a module icon.
 */
function githubCard() {
  const PX = 104;
  const COL = 620;
  const cx = 968;
  const cy = 318;
  const url = `${SITE_HOST}${SITE_BASE}/`;
  const brand = shape(site.brand, 34, 600);
  const over = shape(`${modules.length} interactive modules`.toUpperCase(), 22, 600, 0.12);
  const foot = shape(url, 24, 400);
  const tagline = wrap(site.tagline, 60, 600, COL);
  const blurb = wrap(site.description, 22, 400, COL);

  const rows = (lines, size, weight, top, leading, fill) =>
    lines.map((line, i) => {
      const baseline = top + i * size * leading + size * 0.8;
      return `<path transform="translate(${PX} ${baseline.toFixed(1)})" fill="${fill}" d="${shape(line, size, weight).d}"/>`;
    }).join('');

  // The mark's own eye, blown up and repeated as the card's graphic.
  const eye = (scale, stroke, width, opacity) =>
    `<path transform="translate(${cx} ${cy}) scale(${scale}) translate(-32 -28)" d="M7 28Q32 5 57 28Q32 51 7 28Z"`
    + ` fill="none" stroke="${stroke}" stroke-width="${width}" stroke-linejoin="round" opacity="${opacity}"/>`;
  const orbit = (r, opacity) =>
    `<ellipse cx="${cx}" cy="${cy}" rx="${r}" ry="${(r * 0.64).toFixed(1)}" fill="none" stroke="${SITE_ACCENT}" stroke-width="1.5" opacity="${opacity}"/>`;
  const speck = (deg, r, size, fill, opacity) => {
    const a = (deg * Math.PI) / 180;
    return `<circle cx="${(cx + Math.cos(a) * r).toFixed(1)}" cy="${(cy + Math.sin(a) * r * 0.64).toFixed(1)}" r="${size}" fill="${fill}" opacity="${opacity}"/>`;
  };

  const taglineTop = 246;
  const blurbTop = taglineTop + tagline.length * 60 * 1.14 + 26;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${GH_W}" height="${GH_H}" viewBox="0 0 ${GH_W} ${GH_H}">
  <defs>
    <pattern id="gh-grid" width="34" height="34" patternUnits="userSpaceOnUse">
      <circle cx="1.7" cy="1.7" r="1.7" fill="#ffffff" opacity="0.08"/>
    </pattern>
    <linearGradient id="gh-fade" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#000000"/><stop offset="1" stop-color="#ffffff"/>
    </linearGradient>
    <mask id="gh-mask"><rect width="${GH_W}" height="${GH_H}" fill="url(#gh-fade)"/></mask>
    <radialGradient id="gh-glow" cx="76%" cy="50%" r="52%">
      <stop offset="0" stop-color="${SITE_ACCENT}" stop-opacity="0.34"/>
      <stop offset="1" stop-color="${SITE_ACCENT}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="${GH_W}" height="${GH_H}" fill="${GH_PAPER}"/>
  <rect width="${GH_W}" height="${GH_H}" fill="url(#gh-grid)" mask="url(#gh-mask)"/>
  <rect width="${GH_W}" height="${GH_H}" fill="url(#gh-glow)"/>
  ${orbit(268, 0.22)}${orbit(202, 0.16)}
  ${eye(7.6, SITE_ACCENT, 3, 0.45)}${eye(5.4, GH_CREAM, 2.2, 0.22)}
  <circle cx="${cx}" cy="${cy}" r="66" fill="${SITE_ACCENT}" opacity="0.26"/>
  <circle cx="${cx}" cy="${cy}" r="66" fill="none" stroke="${GH_CREAM}" stroke-width="3" opacity="0.6"/>
  <circle cx="${cx}" cy="${cy}" r="21" fill="${GH_PAPER}"/>
  <circle cx="${cx + 17}" cy="${cy - 17}" r="7.5" fill="${GH_CREAM}" opacity="0.85"/>
  ${speck(-28, 268, 6, SITE_ACCENT, 0.9)}${speck(152, 268, 4.5, GH_CREAM, 0.55)}${speck(68, 202, 4, SITE_ACCENT, 0.7)}
  ${mark(PX, 96, 76)}
  <path transform="translate(${PX + 98} 152)" fill="${GH_CREAM}" d="${brand.d}"/>
  <path transform="translate(${PX} 212)" fill="${SITE_ACCENT}" d="${over.d}"/>
  ${rows(tagline, 60, 600, taglineTop, 1.14, GH_INK)}
  ${rows(blurb, 22, 400, blurbTop, 1.5, GH_MUTED)}
  <rect x="${PX}" y="534" width="${COL}" height="1.5" fill="#ffffff" opacity="0.14"/>
  <path transform="translate(${PX} 586)" fill="${GH_MUTED}" d="${foot.d}"/>
</svg>`;
}
await render(githubCard(), 'github.png');

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

console.log(`og cards: ${modules.length + 1} + github.png -> public/og/`);
