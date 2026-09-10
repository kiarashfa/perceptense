"""Prove every built module carries exactly the same words as its legacy page.

Compares the .page-wrap region of each legacy file against the built page using
the HTML5 parsing algorithm, so what is compared is what a browser would show.
Comments are excluded and element boundaries are separated identically on both
sides, so only visible text is measured.

    python tools/verify_drift.py
"""
from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEGACY = ROOT / 'modules'
REPAIRED = ROOT / 'tools' / 'repaired'
DIST = ROOT / 'dist' / 'modules'
SKIP = {'script', 'style'}

# The legacy back-link was removed at runtime by shared.js, so users never saw
# it; the port drops it from the markup as well.
ALLOWED_REMOVALS = {'All modules', '← All modules'}


def read(path: Path) -> str:
    with open(path, encoding='utf-8', newline='') as fh:
        return fh.read()


def collect(el, out: list[str]) -> None:
    if not isinstance(el.tag, str):          # comment or processing instruction
        if el.tail:
            out.append(el.tail)
        return
    if el.tag in SKIP:
        if el.tail:
            out.append(el.tail)
        return
    out.append(' ')
    if el.text:
        out.append(el.text)
    for child in el:
        collect(child, out)
    out.append(' ')
    if el.tail:
        out.append(el.tail)


def page_wrap_words(html: str, html5lib) -> list[str]:
    doc = html5lib.parse(html, namespaceHTMLElements=False)
    for el in doc.iter():
        if isinstance(el.tag, str) and 'page-wrap' in (el.get('class') or '').split():
            out: list[str] = []
            collect(el, out)
            text = ''.join(out).replace(' ', ' ')
            return re.sub(r'\s+', ' ', text).strip().split()
    raise SystemExit('no .page-wrap element found')


def main() -> int:
    try:
        import html5lib
    except ImportError:
        print('html5lib is required: pip install html5lib')
        return 2

    modules = json.loads((ROOT / 'src' / 'data' / 'modules.json').read_text(encoding='utf-8'))
    failures = 0
    notes: list[str] = []
    total = 0

    for mod in modules:
        override = REPAIRED / mod['legacyFile']
        legacy = override if override.exists() else LEGACY / mod['legacyFile']
        built = DIST / mod['slug'] / 'index.html'
        if not built.exists():
            print(f'  {mod["slug"]:44} NOT BUILT')
            failures += 1
            continue

        a = page_wrap_words(read(legacy), html5lib)
        b = page_wrap_words(read(built), html5lib)
        total += len(a)
        if a == b:
            continue

        matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
        runs = [(op, a[i1:i2], b[j1:j2])
                for op, i1, i2, j1, j2 in matcher.get_opcodes() if op != 'equal']
        if all(op == 'delete' and ' '.join(x).strip() in ALLOWED_REMOVALS for op, x, _ in runs):
            notes.append(f'{mod["slug"]}: legacy back-link removed')
            continue

        failures += 1
        print(f'  {mod["slug"]:44} DRIFT  {len(a)}w -> {len(b)}w  ({len(runs)} run(s))')
        for op, x, y in runs[:4]:
            print(f'      {op:7} legacy={" ".join(x)[:100]!r}')
            print(f'              built ={" ".join(y)[:100]!r}')

    for n in notes:
        print(f'  note: {n}')
    print()
    print(f'modules compared : {len(modules)}')
    print(f'words compared   : {total:,}')
    print(f'modules drifted  : {failures}')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
