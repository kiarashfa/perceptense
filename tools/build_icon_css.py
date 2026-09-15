"""Generate per-page icon stylesheets from src/icons.

Replicates how Font Awesome renders <i class="fa-solid fa-x">, but from local
files: the element becomes a box filled with currentColor and masked by the
icon. Nothing in the markup or in any script changes, which matters because six
modules build icon markup at runtime.

Each page gets only the icons it actually references, in markup or in its own
scripts. The median module uses two, so this avoids shipping the whole set to
every page. A page that renders module icons from the data (its source
mentions `faIcon`) also gets every icon named in src/data/modules.json.

Writes:
  src/styles/icons-base.css        sizing rules, folded into the shared sheet
  src/styles/icons/<page>.css      one file per page that uses icons

    python tools/build_icon_css.py
"""
from __future__ import annotations

import gzip
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / 'src' / 'icons'
PAGES = ROOT / 'src' / 'pages'
OUT_DIR = ROOT / 'src' / 'styles' / 'icons'
BASE_OUT = ROOT / 'src' / 'styles' / 'icons-base.css'

STYLE_CLASSES = {'fa-solid', 'fa-regular', 'fa-brands', 'fas', 'far', 'fab', 'fa'}
MODIFIERS = re.compile(
    r'^fa-(fw|lg|sm|xs|xl|2xs|2xl|[2-9]x|10x|spin|pulse|beat|fade|flip|shake|bounce'
    r'|border|pull-left|pull-right|inverse|stack|stack-1x|stack-2x|li|ul|rotate-\d+'
    r'|flip-horizontal|flip-vertical|flip-both|spin-reverse|spin-pulse|beat-fade'
    r'|sr-only|sr-only-focusable|layers|swap-opacity)$')

BASE = """/* ============================================================
   Icon sizing.

   An <i class="fa-solid fa-x"> element is drawn as a box filled with
   currentColor and masked by the icon, which is how Font Awesome renders its
   own inline SVGs. Keeping the original class names means no markup and no
   script had to change.

   The masks themselves live in a per-page stylesheet, so a page only carries
   the icons it uses.

   Font Awesome Free icons, CC BY 4.0, (c) Fonticons, Inc.
   ============================================================ */

.fa-solid,
.fa-regular,
.fa-brands,
.fas,
.far,
.fab {
  display: inline-block;
  height: 1em;
  width: 1em;
  vertical-align: -0.125em;
  /* An icon with no mask stays an empty box rather than a filled square. */
  background-color: transparent;
}

.fa-fw { width: 1.25em; }
.fa-lg { font-size: 1.33em; line-height: 0.75em; vertical-align: -0.225em; }
.fa-2x { font-size: 2em; }
.fa-3x { font-size: 3em; }
"""


def data_uri(svg: str) -> str:
    svg = re.sub(r'\s+', ' ', svg).strip()
    return 'data:image/svg+xml,' + quote(svg, safe="/:=;,'()<>+*!$&@?~[] ")


def icon_names(text: str) -> set[str]:
    names: set[str] = set()
    for token in re.findall(r'fa-[a-z0-9-]+', text):
        if token in STYLE_CLASSES or MODIFIERS.match(token):
            continue
        names.add(token[3:])
    return names


def main() -> int:
    available = {p.stem: p for p in ICONS.rglob('*.svg')}
    if not available:
        print('no icons found; run tools/build_icons.py first')
        return 2

    BASE_OUT.write_text(BASE, encoding='utf-8')
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob('*.css'):
        stale.unlink()

    modules = json.loads((ROOT / 'src' / 'data' / 'modules.json').read_text(encoding='utf-8'))
    data_icons = icon_names(' '.join(m.get('faIcon', '') for m in modules))

    rows = []
    keys: dict[str, Path] = {}
    unknown: set[str] = set()
    for page in sorted(PAGES.rglob('*.astro')):
        text = page.read_text(encoding='utf-8')
        found = icon_names(text)
        if 'faIcon' in text:
            found |= data_icons
        names = sorted(found)
        key = page.stem if page.stem != 'index' else (
            'home' if page.parent == PAGES else f'{page.parent.name}-index')

        chunks = []
        for name in names:
            src = available.get(name)
            if src is None:
                unknown.add(name)
                continue
            svg = src.read_text(encoding='utf-8')
            m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
            ratio = (float(m.group(1)) / float(m.group(2))) if m else 1.0
            uri = data_uri(svg)
            rule = [f'.fa-{name} {{']
            if abs(ratio - 1.0) > 0.01:
                rule.append(f'  width: {ratio:.4f}em;')
            rule.append('  background-color: currentColor;')
            rule.append(f'  -webkit-mask: url("{uri}") no-repeat center / contain;')
            rule.append(f'  mask: url("{uri}") no-repeat center / contain;')
            rule.append('}')
            chunks.append('\n'.join(rule))

        # A page with no icons still gets a (near empty) stylesheet, so pages can
        # import theirs unconditionally and the import always resolves.
        body = '\n\n'.join(chunks) + '\n' if chunks else '/* none */\n'
        css = '/* Icons used by this page. Generated by tools/build_icon_css.py */\n\n' + body
        (OUT_DIR / f'{key}.css').write_text(css, encoding='utf-8')
        rows.append((key, len(chunks), len(css), len(gzip.compress(css.encode()))))
        keys[key] = page

    rows.sort(key=lambda r: -r[1])
    total_raw = sum(r[2] for r in rows)
    print(f'pages with icons : {len(rows)}')
    print(f'base stylesheet  : {len(BASE) / 1024:.1f} KB')
    print()
    print(f'{"page":34} {"icons":>5} {"raw":>9} {"gzipped":>9}')
    for key, n, raw, gz in rows[:6]:
        print(f'{key:34} {n:5} {raw / 1024:8.1f}K {gz / 1024:8.1f}K')
    median = sorted(r[3] for r in rows)[len(rows) // 2]
    print(f'\nmedian page cost : {median / 1024:.1f} KB gzipped')
    print(f'whole set would  : {total_raw / len(rows) / 1024:.1f} KB avg if shipped together')
    if unknown:
        print(f'\nNOT IN THE ICON SET ({len(unknown)}): {", ".join(sorted(unknown))}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
