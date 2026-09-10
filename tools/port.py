"""Port legacy module pages into Astro pages and per-module stylesheets.

The body is carried over verbatim apart from four deliberate changes:

  * section headings are promoted from <div class="sec"> to <h2 id="...">
  * links to other modules are rewritten to their new URLs
  * the legacy back-link and any wrapper it leaves empty are dropped
  * page-level CSS moves to its own stylesheet, namespaced by a later step

Refuses to emit anything if the body is not well formed, if a link points at a
module that does not exist, or if a single non-ASCII character would be lost.

    python tools/port.py            # all modules
    python tools/port.py 01-weight.html 05-money.html
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEGACY = ROOT / 'modules'
REPAIRED = ROOT / 'tools' / 'repaired'
PAGES = ROOT / 'src' / 'pages' / 'modules'
STYLES = ROOT / 'src' / 'styles' / 'modules-src'
BASE_URL = '/perceptense'

MODULES = json.loads((ROOT / 'src' / 'data' / 'modules.json').read_text(encoding='utf-8'))
BY_ID = {m['id']: m for m in MODULES}
SLUG_FOR_FILE = {m['legacyFile']: m['slug'] for m in MODULES}

DIV = re.compile(r'<(/?)div\b[^>]*?(/?)>')
SEC = re.compile(
    r'<(div|p)((?:\s+[^>]*?)?\sclass="[^"]*(?<![-\w])sec(?![-\w])[^"]*"(?:\s+[^>]*?)?)>'
    r'([^<]*)</\1>')
HREF = re.compile(r'(<a\b[^>]*?\bhref=")([^"]+)(")')

# Legacy hrefs naming files that have never existed. Each resolves to the module
# named by the link's own visible title.
LEGACY_ALIASES = {
    '01-everyday.html': '01-weight.html',
    '31-painting.html': '32-painting.html',
    '32-literature.html': '31-literature.html',
}


def read(path) -> str:
    with open(path, encoding='utf-8', newline='') as fh:
        return fh.read()


def write(path, body: str) -> None:
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(body)


def slugify(s: str) -> str:
    s = re.sub(r'<[^>]+>', '', s).replace('&amp;', ' and ').replace('&', ' and ')
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    s = re.sub(r'[^a-zA-Z0-9]+', '-', s).strip('-').lower()
    return re.sub(r'-{2,}', '-', s) or 'section'


def assert_balanced(body: str, name: str) -> None:
    probe = re.sub(r'<script[\s\S]*?</script>', '', body)
    probe = re.sub(r'<style[\s\S]*?</style>', '', probe)
    depth = 0
    for m in DIV.finditer(probe):
        if m.group(2) == '/':
            continue
        depth += -1 if m.group(1) else 1
        if depth < 0:
            raise SystemExit(f'{name}: stray </div>; repair the source first')
    if depth:
        raise SystemExit(f'{name}: {depth} unclosed <div>; repair the source first')


def unwrap(html: str, cls: str, name: str) -> str:
    """Remove the wrapper carrying `cls` by matching its true closing tag."""
    m = re.search(r'<div\s+class="' + re.escape(cls) + r'"[^>]*>', html)
    if not m:
        raise SystemExit(f'{name}: no .{cls} wrapper found')
    start, depth = m.end(), 1
    for t in DIV.finditer(html, start):
        if t.group(2) == '/':
            continue
        depth += -1 if t.group(1) else 1
        if depth == 0:
            inner = html[start:t.start()]
            after = re.sub(r'^\s*<!--[^>]*page-wrap[^>]*-->', '', html[t.end():])
            return html[:m.start()] + inner + after
    raise SystemExit(f'{name}: no matching </div> for .{cls}')


def rewrite_links(body: str, name: str) -> tuple[str, int]:
    count = 0

    def sub(m: re.Match) -> str:
        nonlocal count
        pre, href, post = m.groups()
        if href.startswith(('mailto:', '#', 'tel:', 'http://', 'https://')):
            return m.group(0)
        path, _, frag = href.partition('#')
        base = os.path.basename(path)
        if not base.endswith('.html'):
            return m.group(0)
        count += 1
        if base == 'index.html':
            return f'{pre}{BASE_URL}/{post}'
        slug = SLUG_FOR_FILE.get(LEGACY_ALIASES.get(base, base))
        if slug is None:
            raise SystemExit(f'{name}: link to unknown module file {href!r}')
        tail = f'#{frag}' if frag else ''
        return f'{pre}{BASE_URL}/modules/{slug}/{tail}{post}'

    return HREF.sub(sub, body), count


def port(name: str) -> dict:
    override = REPAIRED / name
    source = override if override.exists() else LEGACY / name
    raw = read(source)
    mid = int(re.search(r'data-module="(\d+)"', raw).group(1))
    mod = BY_ID[mid]
    slug = mod['slug']

    body = raw[raw.find('>', raw.find('<body')) + 1:raw.rfind('</body>')]
    assert_balanced(body, name)

    # Page-level CSS lives in <head>. A <style> inside <body> belongs to an
    # inline <svg> and stays put, marked is:inline so Astro leaves it alone.
    head = raw[:raw.find('</head>')]
    styles = re.findall(r'<style[^>]*>([\s\S]*?)</style>', head)
    scripts = [m.group(1) for m in
               re.finditer(r'<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>', body)]
    payload = body + ''.join(styles)

    body = re.sub(r'<script[\s\S]*?</script>', '', body)
    body = re.sub(r'<style(?![^>]*\bis:inline)([^>]*)>', r'<style is:inline\1>', body)
    body = re.sub(r'<a class="nav-back"[\s\S]*?</a>\s*', '', body)
    body = re.sub(r'<nav\b[^>]*>\s*</nav>\s*', '', body)
    body = unwrap(body, 'page-wrap', name)

    seen: dict[str, int] = {}

    def promote(m: re.Match) -> str:
        _, attrs, inner = m.groups()
        s = slugify(inner)
        seen[s] = seen.get(s, 0) + 1
        if seen[s] > 1:
            s = f'{s}-{seen[s]}'
        return f'<h2{attrs} id="{s}">{inner}</h2>'

    body, headings = SEC.subn(promote, body)
    body, links = rewrite_links(body, name)

    parts = [
        '---\n',
        "import ModuleLayout from '../../layouts/ModuleLayout.astro';\n",
        "import modules from '../../data/modules.json';\n",
        f"import '../../styles/modules/{slug}.css';\n\n",
        f'const mod = modules.find((m) => m.id === {mid})!;\n',
        '---\n\n',
        '<ModuleLayout mod={mod}>\n',
        body.strip('\n'),
        '\n</ModuleLayout>\n',
    ]
    for sc in scripts:
        parts.append('\n<script is:inline>\n' + sc.strip('\n') + '\n</script>\n')
    astro = ''.join(parts)
    css = '\n'.join(s.strip('\n') for s in styles)

    lost = (Counter(c for c in payload if ord(c) > 127)
            - Counter(c for c in astro + css if ord(c) > 127))
    if lost:
        detail = ', '.join(f'{c!r} (U+{ord(c):04X}) x{n}' for c, n in lost.items())
        raise SystemExit(f'{name}: non-ASCII lost -> {detail}')

    PAGES.mkdir(parents=True, exist_ok=True)
    STYLES.mkdir(parents=True, exist_ok=True)
    write(PAGES / f'{slug}.astro', astro)
    write(STYLES / f'{slug}.css', css)
    if read(PAGES / f'{slug}.astro') != astro:
        raise SystemExit(f'{name}: file did not round-trip through disk')

    return {'name': name, 'slug': slug, 'kb': len(astro) // 1024, 'h2': headings,
            'css': len(css), 'scripts': len(scripts), 'links': links,
            'nonascii': sum(1 for c in payload if ord(c) > 127),
            'repaired': source == override}


def main(argv: list[str]) -> int:
    names = argv or sorted(p.name for p in LEGACY.glob('*.html'))
    rows = [port(n) for n in names]
    for r in rows:
        flag = '  [repaired source]' if r['repaired'] else ''
        print(f'{r["name"]:24} -> {r["slug"] + ".astro":44} {r["kb"]:>4} KB  '
              f'h2={r["h2"]:>2}  css={r["css"]:>6}  scripts={r["scripts"]}  '
              f'links={r["links"]}{flag}')
    print(f'\n{len(rows)} module(s) ported, {sum(r["h2"] for r in rows)} headings, '
          f'{sum(r["links"] for r in rows)} links rewritten, zero non-ASCII lost')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
