"""Refresh the fields of src/data/modules.json that are derived from page content.

modules.json is the source for everything that identifies a module: id, slug,
name, category, keywords, faIcon, blurb, icon, accent and legacyFile. The
subtitle, section outline and Q&A pairs are read back from each module page on
every build, so the data can never disagree with what the page shows.
categories.json is plain source and is only checked here.

Every text field is stored as plain text; entities are decoded once here and
re-escaped only at render time.

    python tools/build_data.py
"""
from __future__ import annotations

import html
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / 'src' / 'pages' / 'modules'
DATA = ROOT / 'src' / 'data'

TITLE_MAX = 60          # characters Google typically renders
DESC_MIN, DESC_MAX = 70, 165

FRONTMATTER = re.compile(r'^---\r?\n[\s\S]*?\r?\n---\r?\n')
SCRIPT_OR_STYLE = re.compile(r'<(script|style)\b[^>]*>[\s\S]*?</\1>', re.I)


def read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def text(s: str) -> str:
    """Strip tags, decode entities, collapse whitespace."""
    s = re.sub(r'<[^>]+>', ' ', s)
    return re.sub(r'\s+', ' ', html.unescape(s)).strip()


def slugify(s: str) -> str:
    s = text(s).replace('&', ' and ')
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    s = re.sub(r'[^a-zA-Z0-9]+', '-', s).strip('-').lower()
    return re.sub(r'-{2,}', '-', s) or 'section'


def page_markup(slug: str) -> str:
    """The template of a module page, without frontmatter, scripts or styles."""
    raw = read(PAGES / f'{slug}.astro')
    return SCRIPT_OR_STYLE.sub('', FRONTMATTER.sub('', raw, count=1))


def main() -> int:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print('beautifulsoup4 and lxml are required: pip install beautifulsoup4 lxml')
        return 2

    modules = json.loads(read(DATA / 'modules.json'))
    categories = json.loads(read(DATA / 'categories.json'))
    problems: list[str] = []

    for mod in modules:
        page = PAGES / f'{mod["slug"]}.astro'
        if not page.exists():
            problems.append(f'module {mod["id"]}: no page at {page.relative_to(ROOT).as_posix()}')
            continue
        body = BeautifulSoup(page_markup(mod['slug']), 'lxml')

        subtitle = body.find(class_='module-subtitle')
        mod['subtitle'] = subtitle.get_text(' ', strip=True) if subtitle else ''

        seen: dict[str, int] = {}
        sections = []
        for sec in body.find_all(class_='sec'):
            label = sec.get_text(' ', strip=True)
            s = slugify(label)
            seen[s] = seen.get(s, 0) + 1
            if seen[s] > 1:
                s = f'{s}-{seen[s]}'
            sections.append({'label': label, 'slug': s})
        mod['sections'] = sections

        qa = []
        for block in body.find_all(class_='qa'):
            q = block.find(class_='qa-q')
            a = block.find(class_='qa-ans')
            if q and a:
                qa.append({'q': q.get_text(' ', strip=True), 'a': a.get_text(' ', strip=True)})
        mod['qa'] = qa

        # Controls a reader can actually work; the About page counts these.
        mod['interactives'] = sum(len(body.find_all(t)) for t in ('button', 'input', 'select', 'canvas', 'textarea'))

        # A hand-written summary wins; otherwise the page's own subtitle stands in.
        mod['description'] = mod.get('summary') or mod['subtitle'] or mod.get('blurb', '')

    (DATA / 'modules.json').write_text(
        json.dumps(modules, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    # --- checks ---
    slugs = [m['slug'] for m in modules]
    for s in set(slugs):
        if slugs.count(s) > 1:
            problems.append(f'duplicate slug: {s}')
    known = {c['id'] for c in categories}
    entity = re.compile(r'&(amp|lt|gt|quot|#\d+);')
    for m in modules:
        for field in ('category', 'accent', 'icon', 'subtitle', 'blurb', 'name'):
            if not m.get(field):
                problems.append(f'module {m["id"]}: missing {field}')
        if m.get('category') not in known:
            problems.append(f'module {m["id"]}: unknown category {m.get("category")!r}')
        for field in ('name', 'subtitle', 'blurb', 'description'):
            if entity.search(m.get(field) or ''):
                problems.append(f'module {m["id"]}: undecoded entity in {field}')

    print(f'modules            : {len(modules)}')
    print(f'categories         : {len(categories)}')
    print(f'sections           : {sum(len(m["sections"]) for m in modules)}')
    print(f'Q&A pairs          : {sum(len(m["qa"]) for m in modules)}')
    print(f'interactives       : {sum(m["interactives"] for m in modules)}')

    long_titles = [m['id'] for m in modules if len(f'{m["name"]}: {m["subtitle"]}') > TITLE_MAX]
    short_desc = [m['id'] for m in modules if len(m['description']) < DESC_MIN]
    long_desc = [m['id'] for m in modules if len(m['description']) > DESC_MAX]
    print(f'titles over {TITLE_MAX} chars: {len(long_titles)} (layout shortens these)')
    print(f'descriptions under {DESC_MIN}: {len(short_desc)}  over {DESC_MAX}: {len(long_desc)}')

    if problems:
        print('\nPROBLEMS')
        for p in problems:
            print('  ' + p)
        return 1
    print('\nno problems')
    return 0


if __name__ == '__main__':
    sys.exit(main())
