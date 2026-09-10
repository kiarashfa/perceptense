"""Make each page import its own icon stylesheet.

Idempotent: running it twice changes nothing. Run after
tools/build_icon_css.py, which decides the file names.

    python tools/wire_icons.py
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / 'src' / 'pages'
ICON_CSS = ROOT / 'src' / 'styles' / 'icons'


def read(p) -> str:
    with io.open(p, encoding='utf-8', newline='') as fh:
        return fh.read()


def write(p, t: str) -> None:
    with io.open(p, 'w', encoding='utf-8', newline='') as fh:
        fh.write(t)


def key_for(page: Path) -> str:
    if page.stem != 'index':
        return page.stem
    return 'home' if page.parent == PAGES else f'{page.parent.name}-index'


def main() -> int:
    added = present = skipped = 0
    for page in sorted(PAGES.rglob('*.astro')):
        key = key_for(page)
        css = ICON_CSS / f'{key}.css'
        if not css.exists():
            skipped += 1
            continue

        # from src/pages/<dirs>/page.astro up to src/, then into styles/
        depth = len(page.relative_to(PAGES).parts)
        rel = '../' * depth + f'styles/icons/{key}.css'
        line = f"import '{rel}';"

        text = read(page)
        if line in text:
            present += 1
            continue

        m = re.search(r'^---\r?\n', text)
        if not m:
            print(f'  {page.relative_to(ROOT)}: no frontmatter, skipped')
            skipped += 1
            continue

        # place it after the last existing import so grouping stays tidy
        end = text.find('\n---', m.end())
        head = text[m.end():end]
        imports = list(re.finditer(r'^import .*;\r?\n', head, re.M))
        newline = '\r\n' if '\r\n' in text[:200] else '\n'
        if imports:
            at = m.end() + imports[-1].end()
        else:
            at = m.end()
        write(page, text[:at] + line + newline + text[at:])
        added += 1

    print(f'imports added   : {added}')
    print(f'already present : {present}')
    print(f'no stylesheet   : {skipped}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
