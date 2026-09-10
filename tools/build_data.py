"""Generate the module and category data files from the legacy site.

Every text field is stored as plain text. The legacy sources disagree about
escaping — shared.js holds JS string literals, index.html holds escaped HTML —
so entities are decoded once here and re-escaped only at render time.

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
LEGACY = ROOT / 'modules'
OUT = ROOT / 'src' / 'data'

TITLE_MAX = 60          # characters Google typically renders
DESC_MIN, DESC_MAX = 70, 165


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


def main() -> int:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print('beautifulsoup4 and lxml are required: pip install beautifulsoup4 lxml')
        return 2

    # --- id, legacy filename and canonical name come from the module registry ---
    registry = read(ROOT / 'files' / 'shared.js')
    block = re.search(r'var MODULES = \[([\s\S]*?)\n\];', registry).group(1)
    mods: dict[int, dict] = {}
    for m in re.finditer(r"\{\s*id:\s*(\d+),\s*file:\s*'([^']+)',\s*name:\s*'([^']+)'\s*\}", block):
        i = int(m.group(1))
        mods[i] = {'id': i, 'legacyFile': m.group(2), 'name': text(m.group(3))}

    # --- category, blurb, icon and search keywords come from the index listing ---
    index = read(ROOT / 'index.html')
    categories = [
        {'id': cid, 'label': text(label)}
        for cid, label in re.findall(
            r'<button class="filter-btn[^"]*" data-cat="([^"]+)">([^<]+)</button>', index)
        if cid != 'all'
    ]
    for m in re.finditer(
            r'<a href="modules/(\d+)-[^"]+\.html" class="mod-item" data-cat="([^"]+)"'
            r' data-search="([^"]*)">[\s\S]*?<i class="([^"]+)"></i>'
            r'[\s\S]*?<div class="mod-name">([\s\S]*?)</div>'
            r'\s*<p class="mod-desc">([\s\S]*?)</p>', index):
        i = int(m.group(1))
        if i in mods:
            mods[i].update(category=m.group(2), keywords=text(m.group(3)).split(),
                           faIcon=m.group(4), blurb=text(m.group(6)))

    # --- subtitle, section outline and Q&A come from each module page ---
    for mod in mods.values():
        raw = read(LEGACY / mod['legacyFile'])
        head = raw[:raw.find('</head>')]
        soup = BeautifulSoup(raw, 'lxml')
        body = soup.body
        for tag in body.find_all(['script', 'style']):
            tag.decompose()

        icon = re.search(r'<link rel="icon"[^>]*href="\.\./assets/icons/([^"]+)"', head)
        mod['icon'] = icon.group(1) if icon else None

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
        for blockEl in body.find_all(class_='qa'):
            q = blockEl.find(class_='qa-q')
            a = blockEl.find(class_='qa-ans')
            if q and a:
                qa.append({'q': q.get_text(' ', strip=True), 'a': a.get_text(' ', strip=True)})
        mod['qa'] = qa

        mod['slug'] = slugify(mod['name'])
        # Search metadata is derived from text the site already carries, never invented.
        mod['description'] = mod['subtitle'] or mod.get('blurb', '')

    accents = read(ROOT / 'files' / 'shared.css')
    for m in re.finditer(r'html\[data-module="(\d+)"\]\s*\{\s*--accent:\s*(#[0-9A-Fa-f]{6});', accents):
        mods[int(m.group(1))]['accent'] = m.group(2)

    ordered = [mods[i] for i in sorted(mods)]
    OUT.mkdir(parents=True, exist_ok=True)
    for name, payload in (('modules', ordered), ('categories', categories)):
        (OUT / f'{name}.json').write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    # --- checks ---
    problems: list[str] = []
    slugs = [m['slug'] for m in ordered]
    for s in set(slugs):
        if slugs.count(s) > 1:
            problems.append(f'duplicate slug: {s}')
    known = {c['id'] for c in categories}
    entity = re.compile(r'&(amp|lt|gt|quot|#\d+);')
    for m in ordered:
        for field in ('category', 'accent', 'icon', 'subtitle', 'blurb', 'name'):
            if not m.get(field):
                problems.append(f'module {m["id"]}: missing {field}')
        if m.get('category') not in known:
            problems.append(f'module {m["id"]}: unknown category {m.get("category")!r}')
        for field in ('name', 'subtitle', 'blurb', 'description'):
            if entity.search(m.get(field) or ''):
                problems.append(f'module {m["id"]}: undecoded entity in {field}')

    print(f'modules            : {len(ordered)}')
    print(f'categories         : {len(categories)}')
    print(f'sections           : {sum(len(m["sections"]) for m in ordered)}')
    print(f'Q&A pairs          : {sum(len(m["qa"]) for m in ordered)}')

    long_titles = [(m['id'], len(f'{m["name"]}: {m["subtitle"]}'))
                   for m in ordered if len(f'{m["name"]}: {m["subtitle"]}') > TITLE_MAX]
    short_desc = [m['id'] for m in ordered if len(m['description']) < DESC_MIN]
    long_desc = [m['id'] for m in ordered if len(m['description']) > DESC_MAX]
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
