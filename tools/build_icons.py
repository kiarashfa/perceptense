"""Assemble the inline icon set used by the pages.

Icons come from two places:

  * public/assets/icons — the 50 module icons that already ship with the site. Their
    fill is hardcoded to each module's accent because they double as favicons,
    so the inline copy is normalised to currentColor and the original is left
    alone.
  * the Font Awesome Free package — everything else.

Writes src/icons/<style>/<name>.svg, each normalised to a single-colour,
currentColor path with no fixed dimensions, so CSS controls size and colour.

    python tools/build_icons.py
"""
from __future__ import annotations

import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / 'public' / 'assets' / 'icons'
FA = ROOT / 'node_modules' / '@fortawesome' / 'fontawesome-free' / 'svgs'
OUT = ROOT / 'src' / 'icons'

STYLE_CLASSES = {'fa-solid', 'fa-regular', 'fa-brands', 'fa-light', 'fa-thin',
                 'fa-duotone', 'fa-sharp', 'fas', 'far', 'fab', 'fal', 'fa'}
MODIFIERS = re.compile(
    r'^fa-(fw|lg|sm|xs|xl|2xs|2xl|[2-9]x|10x|spin|pulse|beat|fade|flip|shake|bounce'
    r'|border|pull-left|pull-right|inverse|stack|stack-1x|stack-2x|li|ul|rotate-\d+'
    r'|flip-horizontal|flip-vertical|flip-both|spin-reverse|spin-pulse|beat-fade'
    r'|sr-only|sr-only-focusable|layers|swap-opacity)$')
STYLE_DIR = {'fa-solid': 'solid', 'fa-regular': 'regular', 'fa-brands': 'brands'}


def collect_used() -> set[str]:
    """Every icon name the pages reference, in markup or in their own scripts.

    Six modules build icon markup at runtime, so scanning class attributes
    alone misses more than half the set.
    """
    used: set[str] = set()
    for page in sorted((ROOT / 'src' / 'pages').rglob('*.astro')):
        for token in re.findall(r'fa-[a-z0-9-]+', page.read_text(encoding='utf-8')):
            if token in STYLE_CLASSES or MODIFIERS.match(token):
                continue
            used.add(token[3:])
    return used


def alias_map() -> dict[str, str]:
    """Old icon names to their current ones, from the package's own metadata."""
    meta = FA.parent / 'metadata' / 'icon-families.json'
    if not meta.exists():
        return {}
    import json
    families = json.loads(meta.read_text(encoding='utf-8'))
    out: dict[str, str] = {}
    for name, info in families.items():
        for old in (info.get('aliases', {}) or {}).get('names', []) or []:
            out[old] = name
    return out


def normalise(svg: str) -> str:
    """One line, currentColor, no fixed size, no comment banner."""
    svg = re.sub(r'<!--[\s\S]*?-->', '', svg)
    svg = re.sub(r'\s+(width|height)="[^"]*"', '', svg)
    svg = re.sub(r'fill="(?!none)[^"]*"', 'fill="currentColor"', svg)
    if 'fill=' not in svg.split('>', 1)[0] and 'fill="currentColor"' not in svg:
        svg = svg.replace('<path', '<path fill="currentColor"', 1)
    return re.sub(r'\s+', ' ', svg).strip()


def main() -> int:
    if not FA.exists():
        print('Font Awesome package not installed; run npm install first')
        return 2

    used = collect_used()
    aliases = alias_map()
    local_by_name = {}
    for f in LOCAL.glob('*.svg'):
        m = re.match(r'\d+_fa-([a-z0-9-]+)\.svg$', f.name)
        if m:
            local_by_name[m.group(1)] = f

    OUT.mkdir(parents=True, exist_ok=True)
    sources: Counter[str] = Counter()
    renamed: list[tuple[str, str]] = []
    missing: list[str] = []

    for name in sorted(used):
        if name in local_by_name:
            svg = local_by_name[name].read_text(encoding='utf-8')
            style = 'solid'
            sources['site assets'] += 1
        else:
            canonical = name
            candidate = next((FA / s / f'{name}.svg' for s in ('solid', 'regular', 'brands')
                              if (FA / s / f'{name}.svg').exists()), None)
            if candidate is None and name in aliases:
                canonical = aliases[name]
                candidate = next((FA / s / f'{canonical}.svg'
                                  for s in ('solid', 'regular', 'brands')
                                  if (FA / s / f'{canonical}.svg').exists()), None)
                if candidate is not None:
                    renamed.append((name, canonical))
            if candidate is None:
                missing.append(name)
                continue
            svg = candidate.read_text(encoding='utf-8')
            style = candidate.parent.name
            sources['font awesome'] += 1

        # Filed under the name the pages actually use, so an old alias still resolves.
        target = OUT / style / f'{name}.svg'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(normalise(svg) + '\n', encoding='utf-8')

    print(f'icons referenced : {len(used)}')
    for k, v in sources.items():
        print(f'  from {k:14} : {v}')
    print(f'written          : {sum(sources.values())} -> src/icons/')
    if renamed:
        print(f'\nresolved through the alias map ({len(renamed)}):')
        for old, new in renamed:
            print(f'  fa-{old} -> {new}')
    if missing:
        print(f'\nNOT FOUND ({len(missing)}): {", ".join(missing)}')
        return 1
    print('\nevery referenced icon resolved')
    return 0


if __name__ == '__main__':
    sys.exit(main())
