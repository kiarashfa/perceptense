"""Rename module classes to readable names, proving nothing else changes.

    python tools/rename_classes.py <map.json>            # check only
    python tools/rename_classes.py <map.json> --apply

<map.json> is {"<slug>": {"old-class": "new-class", ...}, ...}.

A rename is exact. The class changes in the module stylesheet, in every class
attribute (static markup and markup that scripts build), in script selector
strings such as querySelector('.old') and in exact quoted tokens such as
classList.add('old') — and nowhere else. A rename is refused when:

  * the new name is not a plain lowercase hyphenated name, or still ends in a
    number, or is used twice in the map
  * the new name already exists anywhere in the module or in a site-wide
    stylesheet, where it would pick up rules it never had
  * the old name is assembled at runtime ('bar-' + n), named in a style block,
    or mentioned in any other way

Because every new name is absent beforehand, mapping it back to the old name
must reproduce the original page and stylesheet byte for byte; that is checked
before anything is written. Nothing is written unless every rename in the map
passes.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from consolidate_css import (MODULE_CSS, PAGES, dynamic_prefixes, read, region,
                             rename_in_class_attrs, split_parts, word, write)

ROOT = Path(__file__).resolve().parent.parent
STYLES = ROOT / 'src' / 'styles'
GLOBAL_SHEETS = ['shared.css', 'chrome.css', 'home.css', 'about.css', 'fonts.css', 'icons-base.css']

NAME = re.compile(r'^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$')
TRAILING_NUMBER = re.compile(r'-\d+$')


def global_classes() -> set[str]:
    sheets = [STYLES / s for s in GLOBAL_SHEETS] + sorted((STYLES / 'icons').glob('*.css'))
    found: set[str] = set()
    for sheet in sheets:
        if sheet.exists():
            text = re.sub(r'url\([^)]*\)', '', read(sheet))
            found.update(re.findall(r'\.([A-Za-z_][\w-]*)', text))
    return found


def allowed_spans(page: str, name: str) -> list[tuple[int, int]]:
    """Spans where the old name may legitimately occur."""
    spans = [m.span(1) for m in re.finditer(r'\bclass="([^"]*)"', page)]
    spans += [m.span() for m in re.finditer(r'\bid="[^"]*"', page)]
    for start, end, kind in _regions(page):
        if kind != 'script':
            continue
        body = page[start:end]
        spans += [(start + m.start(), start + m.end())
                  for m in re.finditer(r'(?<![\w-])\.' + re.escape(name) + r'(?![\w-])', body)]
        spans += [(start + m.start(), start + m.end())
                  for m in re.finditer(r'([\'"`])' + re.escape(name) + r'\1', body)]
    return spans


def _regions(page: str):
    pos = 0
    for text, kind in split_parts(page):
        yield pos, pos + len(text), kind
        pos += len(text)


def rename_page(page: str, old: str, new: str) -> str:
    parts = []
    for text, kind in split_parts(page):
        if kind == 'style':
            parts.append(text)
            continue
        text = rename_in_class_attrs(text, old, new)
        if kind == 'script':
            text = re.sub(r'(?<![\w-])\.' + re.escape(old) + r'(?![\w-])', f'.{new}', text)
            text = re.sub(r'([\'"`])' + re.escape(old) + r'\1', lambda m: f'{m.group(1)}{new}{m.group(1)}', text)
        parts.append(text)
    return ''.join(parts)


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith('--'):
        print(__doc__)
        return 2
    apply = '--apply' in argv
    plan = json.loads(Path(argv[0]).read_text(encoding='utf-8'))
    taken_globally = global_classes()

    refusals: list[str] = []
    results: dict[str, tuple[str, str]] = {}
    total = 0

    for slug, mapping in plan.items():
        page_file = PAGES / f'{slug}.astro'
        css_file = MODULE_CSS / f'{slug}.css'
        if not page_file.exists() or not css_file.exists():
            refusals.append(f'{slug}: no such module')
            continue
        page = original_page = read(page_file)
        css = original_css = read(css_file)
        built = dynamic_prefixes(page)
        news = list(mapping.values())
        applied: dict[str, str] = {}

        def refuse(msg: str) -> None:
            refusals.append(f'{slug}: {msg}')

        for old, new in mapping.items():
            if not re.search(r'(?<![\w-])\.' + re.escape(old) + r'(?![\w-])', css):
                refuse(f'.{old} is not in the module stylesheet')
                continue
            if not NAME.match(new) or TRAILING_NUMBER.search(new) or len(new) > 40:
                refuse(f'.{old} -> .{new}: not a plain readable name')
                continue
            if news.count(new) > 1 or new in mapping:
                refuse(f'.{new} is used twice in the map or is itself being renamed')
                continue
            if new in taken_globally:
                refuse(f'.{new} already exists in a site-wide stylesheet')
                continue
            if re.search(word(new), original_page) or re.search(word(new), original_css):
                refuse(f'.{new} already occurs in the module')
                continue
            if any(old.startswith(p) for p in built):
                refuse(f'.{old} may be assembled at runtime')
                continue
            if re.search(word(old), region(original_page, 'style')):
                refuse(f'.{old} is named in a style block')
                continue
            spans = allowed_spans(original_page, old)
            stray = [m.start() for m in re.finditer(word(old), original_page)
                     if not any(a <= m.start() and m.end() <= b for a, b in spans)]
            if stray:
                at = original_page[max(0, stray[0] - 40):stray[0] + len(old) + 20].replace('\n', ' ')
                refuse(f'.{old} is mentioned outside class attributes and selectors: {at!r}')
                continue

            page = rename_page(page, old, new)
            css = re.sub(r'(?<![\w-])\.' + re.escape(old) + r'(?![\w-])', f'.{new}', css)
            applied[old] = new
            total += 1

        # proof: mapping every applied new name back must give the original files exactly
        back_page, back_css = page, css
        for old, new in applied.items():
            back_page = re.sub(word(new), old, back_page)
            back_css = re.sub(r'(?<![\w-])\.' + re.escape(new) + r'(?![\w-])', f'.{old}', back_css)
        if back_page != original_page:
            refuse('page does not map back to the original; refusing')
        if back_css != original_css:
            refuse('stylesheet does not map back to the original; refusing')
        leftover = [o for o in applied if re.search(r'class="[^"]*' + word(o), page)
                    or re.search(r'(?<![\w-])\.' + re.escape(o) + r'(?![\w-])', css)]
        if leftover:
            refuse(f'still referenced after rename: {", ".join(leftover)}')
        results[slug] = (page, css)

    print(f'modules in map   : {len(plan)}')
    print(f'renames checked  : {total}')
    print(f'refused          : {len(refusals)}')
    for r in refusals:
        print('   ' + r)
    if refusals:
        return 1
    if not apply:
        print('\nall renames pass; pass --apply to write')
        return 0
    for slug, (page, css) in results.items():
        write(PAGES / f'{slug}.astro', page)
        write(MODULE_CSS / f'{slug}.css', css)
    print(f'\nrewritten: {len(results)} module(s)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
