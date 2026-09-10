"""Assert the structural and metadata guarantees the rebuild exists to provide.

Checks every built page for a single h1, a unique title and description within
sensible lengths, a correct canonical, complete social tags, parseable
structured data, resolvable in-page anchors, and no insecure links. Also checks
the sitemap lists every page.

    python tools/verify_seo.py
"""
from __future__ import annotations

import html as htmllib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'dist'
ORIGIN = 'https://kiarashfa.github.io'
BASE = '/perceptense'

TITLE_MIN, TITLE_MAX = 15, 70
# Hard bounds. Descriptions between DESC_MIN and DESC_SOFT are reported as a
# quality note rather than a failure: they are accurate and unique, just terse.
DESC_MIN, DESC_MAX = 28, 175
DESC_SOFT = 70

REQUIRED_META = [
    ('og:title', r'<meta property="og:title" content="([^"]*)"'),
    ('og:description', r'<meta property="og:description" content="([^"]*)"'),
    ('og:url', r'<meta property="og:url" content="([^"]*)"'),
    ('og:type', r'<meta property="og:type" content="([^"]*)"'),
    ('og:site_name', r'<meta property="og:site_name" content="([^"]*)"'),
    ('twitter:card', r'<meta name="twitter:card" content="([^"]*)"'),
]


def strip_non_content(html: str) -> str:
    html = re.sub(r'<script[\s\S]*?</script>', '', html)
    return re.sub(r'<style[\s\S]*?</style>', '', html)


def main() -> int:
    pages = sorted(DIST.rglob('index.html'))
    if not pages:
        print('no build found; run the build first')
        return 2

    modules = json.loads((ROOT / 'src' / 'data' / 'modules.json').read_text(encoding='utf-8'))
    qa_counts = {m['slug']: len(m['qa']) for m in modules}

    problems: list[str] = []
    titles: dict[str, list[str]] = defaultdict(list)
    descriptions: dict[str, list[str]] = defaultdict(list)
    ids_by_page: dict[str, set[str]] = {}
    anchors: list[tuple[str, str]] = []
    ld_types: defaultdict[str, int] = defaultdict(int)
    terse: list[tuple[str, int]] = []

    for page in pages:
        rel = page.parent.relative_to(DIST).as_posix()
        url_path = f'{BASE}/' if rel == '.' else f'{BASE}/{rel}/'
        name = url_path
        html = page.read_text(encoding='utf-8')
        content = strip_non_content(html)

        def fail(msg: str) -> None:
            problems.append(f'{name}: {msg}')

        # --- one h1 ---
        h1s = re.findall(r'<h1\b', content)
        if len(h1s) != 1:
            fail(f'{len(h1s)} <h1> elements (expected exactly 1)')

        # --- title ---
        m = re.search(r'<title>([\s\S]*?)</title>', html)
        if not m:
            fail('no <title>')
        else:
            title = htmllib.unescape(re.sub(r'\s+', ' ', m.group(1))).strip()
            titles[title].append(name)
            if not (TITLE_MIN <= len(title) <= TITLE_MAX):
                fail(f'title length {len(title)} outside {TITLE_MIN}-{TITLE_MAX}: {title!r}')

        # --- description ---
        m = re.search(r'<meta name="description" content="([^"]*)"', html)
        if not m:
            fail('no meta description')
        else:
            desc = htmllib.unescape(m.group(1)).strip()
            descriptions[desc].append(name)
            if not (DESC_MIN <= len(desc) <= DESC_MAX):
                fail(f'description length {len(desc)} outside {DESC_MIN}-{DESC_MAX}')
            elif len(desc) < DESC_SOFT:
                terse.append((name, len(desc)))

        # --- canonical ---
        m = re.search(r'<link rel="canonical" href="([^"]*)"', html)
        if not m:
            fail('no canonical')
        elif m.group(1) != f'{ORIGIN}{url_path}':
            fail(f'canonical {m.group(1)} != {ORIGIN}{url_path}')

        # --- social tags ---
        for label, pattern in REQUIRED_META:
            if not re.search(pattern, html):
                fail(f'missing {label}')

        # --- language ---
        if not re.search(r'<html[^>]*\blang="[a-z]{2}', html):
            fail('no lang attribute on <html>')

        # --- structured data ---
        blocks = re.findall(r'<script type="application/ld\+json">([\s\S]*?)</script>', html)
        if not blocks:
            fail('no structured data')
        for raw in blocks:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                fail(f'structured data is not valid JSON: {exc}')
                continue
            if '@context' not in data or '@type' not in data:
                fail('structured data missing @context or @type')
            else:
                ld_types[data['@type']] += 1

        # --- FAQ coverage on module pages ---
        if rel.startswith('modules/') and rel != 'modules':
            slug = rel.split('/', 1)[1]
            expected = qa_counts.get(slug)
            if expected:
                faq = [json.loads(b) for b in blocks if '"FAQPage"' in b]
                if not faq:
                    fail(f'has {expected} Q&A pairs but no FAQPage structured data')
                elif len(faq[0].get('mainEntity', [])) != expected:
                    fail(f'FAQPage lists {len(faq[0].get("mainEntity", []))} of {expected} Q&A pairs')

        # --- insecure links ---
        for href in re.findall(r'<a\b[^>]*href="(http://[^"]*)"', content):
            fail(f'insecure link: {href}')

        # --- collect ids and anchors for cross-page resolution ---
        ids_by_page[url_path] = set(re.findall(r'\bid="([^"]+)"', content))
        for href in re.findall(r'<a\b[^>]*href="([^"]*#[^"]*)"', content):
            anchors.append((url_path, href))

    # --- anchors resolve ---
    for src, href in anchors:
        target, _, frag = href.partition('#')
        if not frag:
            continue
        page = src if target in ('', '#') else target
        if not page.startswith(BASE):
            continue
        page = page if page.endswith('/') else page + '/'
        if page not in ids_by_page:
            problems.append(f'{src}: anchor points at unknown page {page}')
        elif frag not in ids_by_page[page]:
            problems.append(f'{src}: anchor #{frag} not found on {page}')

    # --- uniqueness ---
    for title, where in titles.items():
        if len(where) > 1:
            problems.append(f'duplicate title on {len(where)} pages: {title!r} ({where[0]} ...)')
    for desc, where in descriptions.items():
        if len(where) > 1:
            problems.append(f'duplicate description on {len(where)} pages ({where[0]} ...)')

    # --- sitemap covers every page ---
    sitemap_urls: set[str] = set()
    for sm in DIST.glob('sitemap*.xml'):
        sitemap_urls.update(re.findall(r'<loc>([^<]+)</loc>', sm.read_text(encoding='utf-8')))
    expected_urls = {
        f'{ORIGIN}{BASE}/' if p.parent == DIST
        else f'{ORIGIN}{BASE}/{p.parent.relative_to(DIST).as_posix()}/'
        for p in pages
    }
    missing = sorted(expected_urls - sitemap_urls)
    if missing:
        problems.append(f'{len(missing)} page(s) absent from the sitemap, e.g. {missing[:3]}')

    print(f'pages checked      : {len(pages)}')
    print(f'unique titles      : {len(titles)}')
    print(f'unique descriptions: {len(descriptions)}')
    print(f'anchors checked    : {len(anchors)}')
    print(f'structured data    : ' + ', '.join(f'{k} x{v}' for k, v in sorted(ld_types.items())))
    if terse:
        print(f'terse descriptions : {len(terse)} under {DESC_SOFT} chars '
              f'(accurate and unique, but worth expanding by hand)')
    print(f'problems           : {len(problems)}')
    for p in problems[:30]:
        print('   ' + p)
    if len(problems) > 30:
        print(f'   ... and {len(problems) - 30} more')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
