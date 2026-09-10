"""Check every inline on*= handler in the built pages resolves to a real function.

Astro's default <script> is an ES module, so functions declared inside it never
reach `window` and every inline handler would silently break. This proves the
built pages keep their handlers callable.

    python tools/verify_handlers.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'dist'

BUILTIN = {
    'this', 'window', 'document', 'alert', 'console', 'event', 'Math', 'Number',
    'String', 'parseInt', 'parseFloat', 'JSON', 'Object', 'Array', 'Date',
    'setTimeout', 'setInterval', 'localStorage', 'navigator', 'location',
    'history', 'Boolean', 'isNaN', 'encodeURIComponent', 'decodeURIComponent',
}
CALL = re.compile(r'(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(')
DECL = re.compile(r'(?:function\s+([A-Za-z_$][\w$]*)\s*\('
                  r'|(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:function|\(|async)'
                  r'|window\.([A-Za-z_$][\w$]*)\s*=)')
HANDLER = re.compile(r'\son[a-z]+="([^"]*)"')
MODULE_SCRIPT = re.compile(r'<script\b[^>]*type="module"[^>]*>')


def main() -> int:
    pages = sorted(DIST.glob('modules/*/index.html'))
    if not pages:
        print('no built pages found; run the build first')
        return 2

    checked = 0
    problems = []
    for page in pages:
        html = page.read_text(encoding='utf-8')
        name = page.parent.name

        inline = '\n'.join(
            m.group(1) for m in
            re.finditer(r'<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>', html))
        defined = {g for m in DECL.finditer(inline) for g in m.groups() if g}

        called = set()
        for h in HANDLER.finditer(html):
            checked += 1
            code = re.sub(r"'[^']*'|&#39;[^&]*&#39;", "''", h.group(1))
            called.update(m.group(1) for m in CALL.finditer(code))

        missing = sorted(called - defined - BUILTIN)
        if missing:
            problems.append((name, missing))

    print(f'pages checked          : {len(pages)}')
    print(f'inline handlers checked: {checked}')
    print(f'pages with problems    : {len(problems)}')
    for name, missing in problems[:15]:
        print(f'   {name:44} missing: {", ".join(missing[:6])}')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
