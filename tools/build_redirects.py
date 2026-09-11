"""Emit a redirect stub for every legacy .html URL.

The old site published each page as a .html file, and those are the URLs search
engines and any existing bookmark already know. GitHub Pages cannot issue a real
301, so each stub carries an instant meta refresh plus a canonical link to the
new address; Google follows those and consolidates on the canonical.

Astro's own `redirects` option cannot be used here: with `format: 'directory'`
it writes `<name>.html/index.html`, a directory rather than the file the old URL
actually names.

Run after the build.

    python tools/build_redirects.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'dist'
ORIGIN = 'https://kiarashfa.github.io'
BASE = '/perceptense'

TEMPLATE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Moved — {title}</title>
    <link rel="canonical" href="{origin}{target}" />
    <meta http-equiv="refresh" content="0; url={target}" />
  </head>
  <body>
    <p>This page has moved to <a href="{target}">{title}</a>.</p>
  </body>
</html>
"""


def main() -> int:
    if not (DIST / 'index.html').exists():
        print('no build found; run the build first')
        return 2

    modules = json.loads((ROOT / 'src' / 'data' / 'modules.json').read_text(encoding='utf-8'))

    # The homepage is emitted at dist/index.html, so /index.html already
    # resolves; only pages whose address changed need a stub.
    routes = [('about.html', f'{BASE}/about/', 'About')]
    routes += [(f'modules/{m["legacyFile"]}', f'{BASE}/modules/{m["slug"]}/', m['name'])
               for m in modules]

    written = 0
    for rel, target, title in routes:
        out = DIST / rel
        if out.is_dir():
            print(f'  refusing to overwrite directory {rel}')
            return 1
        destination = DIST / target[len(BASE):].strip('/') / 'index.html'
        if not destination.exists():
            print(f'  target missing for {rel}: {destination.relative_to(DIST)}')
            return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            TEMPLATE.format(origin=ORIGIN, target=target,
                            title=title.replace('&', '&amp;').replace('<', '&lt;')),
            encoding='utf-8')
        written += 1

    print(f'redirect stubs written : {written}')
    print(f'  about.html           -> {BASE}/about/')
    print(f'  modules/*.html       -> {BASE}/modules/<slug>/  ({len(modules)})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
