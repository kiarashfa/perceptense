"""List every Font Awesome icon the site uses and where it can be sourced from.

    python tools/audit_icons.py
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL_ICONS = ROOT / 'public' / 'assets' / 'icons'

STYLE_CLASSES = {'fa-solid', 'fa-regular', 'fa-brands', 'fa-light', 'fa-thin',
                 'fa-duotone', 'fa-sharp', 'fas', 'far', 'fab', 'fal', 'fa'}
MODIFIERS = re.compile(
    r'^fa-(fw|lg|sm|xs|xl|2xs|2xl|[2-9]x|10x|spin|pulse|beat|fade|flip|shake|bounce'
    r'|border|pull-left|pull-right|inverse|stack|stack-1x|stack-2x|li|ul|rotate-\d+'
    r'|flip-horizontal|flip-vertical|flip-both|spin-reverse|spin-pulse|beat-fade'
    r'|sr-only|sr-only-focusable|layers|swap-opacity)$')


def main() -> int:
    pages = sorted((ROOT / 'src' / 'pages').rglob('*.astro'))
    used: Counter[tuple[str, str]] = Counter()     # (style, name) -> count
    where: defaultdict[str, set[str]] = defaultdict(set)

    for page in pages:
        text = page.read_text(encoding='utf-8')
        # only class attributes; scripts may build class strings too, so include
        # any literal that names a fa- icon
        for attr in re.findall(r'class="([^"]*fa-[^"]*)"', text):
            classes = attr.split()
            style = next((c for c in classes if c in STYLE_CLASSES), 'fa-solid')
            style = {'fas': 'fa-solid', 'far': 'fa-regular', 'fab': 'fa-brands',
                     'fa': 'fa-solid'}.get(style, style)
            for c in classes:
                if not c.startswith('fa-') or c in STYLE_CLASSES or MODIFIERS.match(c):
                    continue
                used[(style, c)] += 1
                where[c].add(page.stem)

    local = {}
    for f in sorted(LOCAL_ICONS.glob('*.svg')):
        m = re.match(r'\d+_(fa-[a-z0-9-]+)\.svg$', f.name)
        if m:
            local[m.group(1)] = f.name

    have = sorted({n for _s, n in used} & set(local))
    missing = sorted({n for _s, n in used} - set(local))

    print(f'pages scanned      : {len(pages)}')
    print(f'icon references    : {sum(used.values())}')
    print(f'distinct icons     : {len({n for _s, n in used})}')
    print(f'  already local    : {len(have)}')
    print(f'  need downloading : {len(missing)}')
    print()
    styles = Counter(s for s, _n in used)
    print('by style           : ' + ', '.join(f'{k} x{v}' for k, v in styles.items()))
    print()
    print('most used icons:')
    for (style, name), n in used.most_common(12):
        mark = 'local' if name in local else 'MISSING'
        print(f'  {style:11} {name:28} x{n:<4} {mark}  ({len(where[name])} page(s))')
    print()
    print(f'unused local icons : {len(set(local) - {n for _s, n in used})}')
    if missing:
        print()
        print('to download:')
        for name in missing:
            style = next(s for s, n in used if n == name)
            print(f'  {style:11} {name}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
