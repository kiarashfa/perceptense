"""Port the legacy about page into an Astro page and its own stylesheet.

Carried over verbatim apart from four deliberate changes:

  * the etymology wordmark becomes the page's <h1>; it is the visual title and
    the page previously had no top-level heading at all
  * the page's own footer is dropped, because the layout now supplies one
  * internal links are rewritten to their new URLs
  * the module and category counts are read from the data rather than hardcoded

    python tools/port_about.py
"""
from __future__ import annotations

import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = '/perceptense'

MODULES = json.loads((ROOT / 'src' / 'data' / 'modules.json').read_text(encoding='utf-8'))
SLUG_FOR_FILE = {m['legacyFile']: m['slug'] for m in MODULES}


def read(path) -> str:
    with io.open(path, encoding='utf-8', newline='') as fh:
        return fh.read()


def write(path, text: str) -> None:
    with io.open(path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(text)


def rewrite_links(body: str) -> tuple[str, int]:
    count = 0

    def sub(m: re.Match) -> str:
        nonlocal count
        pre, href, post = m.groups()
        if href.startswith(('http://', 'https://', 'mailto:', 'tel:', '#')):
            return m.group(0)
        path, _, frag = href.partition('#')
        base = path.rsplit('/', 1)[-1]
        if not base.endswith('.html'):
            return m.group(0)
        count += 1
        if base == 'index.html':
            return f'{pre}{BASE_URL}/{post}'
        slug = SLUG_FOR_FILE.get(base)
        if slug is None:
            raise SystemExit(f'about: link to unknown module file {href!r}')
        tail = f'#{frag}' if frag else ''
        return f'{pre}{BASE_URL}/modules/{slug}/{tail}{post}'

    return re.sub(r'(<a\b[^>]*?\bhref=")([^"]+)(")', sub, body), count


def main() -> int:
    raw = read(ROOT / 'about.html')
    head = raw[:raw.find('</head>')]
    body = raw[raw.find('>', raw.find('<body')) + 1:raw.rfind('</body>')]

    styles = re.findall(r'<style[^>]*>([\s\S]*?)</style>', head)
    scripts = [m.group(1) for m in
               re.finditer(r'<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>', body)]
    payload = body + ''.join(styles)

    body = re.sub(r'<script[\s\S]*?</script>', '', body)
    body = re.sub(r'<style(?![^>]*\bis:inline)([^>]*)>', r'<style is:inline\1>', body)

    # the layout supplies the footer
    body, dropped = re.subn(r'\s*<!--[^>]*FOOTER[^>]*-->\s*<footer class="home-footer">[\s\S]*?</footer>',
                            '', body)
    if dropped != 1:
        raise SystemExit(f'about: expected exactly one legacy footer, removed {dropped}')

    # the wordmark is the page heading
    body, promoted = re.subn(r'<div class="etym-word"([^>]*)>([\s\S]*?)</div>',
                             r'<h1 class="etym-word"\1>\2</h1>', body, count=1)
    if promoted != 1:
        raise SystemExit('about: could not find the etymology wordmark')

    body, links = rewrite_links(body)

    # counts that the data already guarantees
    categories = json.loads((ROOT / 'src' / 'data' / 'categories.json').read_text(encoding='utf-8'))
    body = body.replace('data-count="50"', 'data-count={modules.length}', 1)
    body = body.replace('data-count="8"', 'data-count={categories.length}', 1)

    # <h1> carries default margins that the wordmark rule never had to cancel
    css = '\n'.join(s.strip('\n') for s in styles)
    css = css.replace('.etym-word {', '.etym-word {\n  margin: 0;', 1)

    page = (
        '---\n'
        "import BaseLayout from '../layouts/BaseLayout.astro';\n"
        "import { site, path, pageTitle } from '../lib/site';\n"
        "import modules from '../data/modules.json';\n"
        "import categories from '../data/categories.json';\n"
        "import '../styles/about.css';\n\n"
        "const pathname = path('about');\n"
        'const url = new URL(pathname, Astro.site).href;\n\n'
        'const structuredData = [\n'
        '  {\n'
        "    '@context': 'https://schema.org',\n"
        "    '@type': 'AboutPage',\n"
        '    name: `About ${site.brand}`,\n'
        '    url,\n'
        '    description: site.description,\n'
        '    inLanguage: site.locale,\n'
        '    author: { \'@type\': \'Person\', name: site.author },\n'
        '    about: {\n'
        "      '@type': 'Course',\n"
        '      name: `${site.brand} — ${site.tagline}`,\n'
        "      url: new URL(path(), Astro.site).href,\n"
        "      provider: { '@type': 'Person', name: site.author },\n"
        '    },\n'
        '  },\n'
        '  {\n'
        "    '@context': 'https://schema.org',\n"
        "    '@type': 'BreadcrumbList',\n"
        '    itemListElement: [\n'
        "      { '@type': 'ListItem', position: 1, name: site.brand, item: new URL(path(), Astro.site).href },\n"
        "      { '@type': 'ListItem', position: 2, name: 'About', item: url },\n"
        '    ],\n'
        '  },\n'
        '];\n'
        '---\n\n'
        '<BaseLayout\n'
        "  title={pageTitle('About', 'why this course exists')}\n"
        '  description={`${site.brand} is ${site.description[0].toLowerCase()}${site.description.slice(1)}`.slice(0, 170)}\n'
        '  pathname={pathname}\n'
        '  bodyClass="about"\n'
        '  structuredData={structuredData}\n'
        '>\n'
        '  <nav class="crumbs" aria-label="Breadcrumb" slot="before-main">\n'
        '    <ol>\n'
        '      <li><a href={path()}>Home</a></li>\n'
        '      <li aria-current="page">About</li>\n'
        '    </ol>\n'
        '  </nav>\n\n'
        + body.strip('\n') + '\n'
        '</BaseLayout>\n'
    )
    for sc in scripts:
        page += '\n<script is:inline>\n' + sc.strip('\n') + '\n</script>\n'

    lost = (Counter(c for c in payload if ord(c) > 127)
            - Counter(c for c in page + css if ord(c) > 127))
    if lost:
        detail = ', '.join(f'{c!r} (U+{ord(c):04X}) x{n}' for c, n in lost.items())
        raise SystemExit(f'about: non-ASCII lost -> {detail}')

    write(ROOT / 'src' / 'pages' / 'about.astro', page)
    write(ROOT / 'src' / 'styles' / 'about.css', css.strip() + '\n')

    print(f'about.astro written  : {len(page) // 1024} KB, {page.count(chr(10))} lines')
    print(f'about.css written    : {len(css) // 1024} KB, {css.count(chr(10))} lines')
    print(f'scripts carried over : {len(scripts)}')
    print(f'links rewritten      : {links}')
    print(f'legacy footer removed: {dropped}   wordmark promoted to h1: {promoted}')
    print(f'non-ASCII preserved  : {sum(1 for c in payload if ord(c) > 127)} characters')
    return 0


if __name__ == '__main__':
    sys.exit(main())
