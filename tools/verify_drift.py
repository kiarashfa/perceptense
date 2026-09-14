"""Prove every built module carries exactly its approved words.

tools/baseline/<slug>.txt holds each module's visible text, one word per line.
The built .page-wrap is parsed with the HTML5 algorithm, so what is compared is
what a browser would show: comments, scripts and styles are excluded and element
boundaries separate words identically.

An approved content change is recorded by building and accepting the module,
which rewrites its baseline so the change appears as a reviewable diff:

    python tools/verify_drift.py
    python tools/verify_drift.py --accept <slug> [<slug> ...]
"""
from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / 'tools' / 'baseline'
DIST = ROOT / 'dist' / 'modules'
SKIP = {'script', 'style'}


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


def main(argv: list[str]) -> int:
    try:
        import html5lib
    except ImportError:
        print('html5lib is required: pip install html5lib')
        return 2

    accept = set(argv[argv.index('--accept') + 1:]) if '--accept' in argv else set()
    modules = json.loads((ROOT / 'src' / 'data' / 'modules.json').read_text(encoding='utf-8'))
    unknown = accept - {m['slug'] for m in modules}
    if unknown:
        print(f'unknown module(s): {", ".join(sorted(unknown))}')
        return 2

    failures = 0
    total = 0
    for mod in modules:
        slug = mod['slug']
        built_page = DIST / slug / 'index.html'
        baseline = BASELINE / f'{slug}.txt'
        if not built_page.exists():
            print(f'  {slug:44} NOT BUILT')
            failures += 1
            continue
        built = page_wrap_words(read(built_page), html5lib)

        if slug in accept:
            baseline.write_text('\n'.join(built) + '\n', encoding='utf-8', newline='\n')
            print(f'  {slug:44} ACCEPTED  {len(built)} words')
        if not baseline.exists():
            print(f'  {slug:44} NO BASELINE')
            failures += 1
            continue

        approved = read(baseline).split()
        total += len(approved)
        if approved == built:
            continue

        matcher = difflib.SequenceMatcher(None, approved, built, autojunk=False)
        runs = [(op, approved[i1:i2], built[j1:j2])
                for op, i1, i2, j1, j2 in matcher.get_opcodes() if op != 'equal']
        failures += 1
        print(f'  {slug:44} DRIFT  {len(approved)}w -> {len(built)}w  ({len(runs)} run(s))')
        for op, x, y in runs[:4]:
            print(f'      {op:7} approved={" ".join(x)[:100]!r}')
            print(f'              built   ={" ".join(y)[:100]!r}')

    print()
    print(f'modules compared : {len(modules)}')
    print(f'words compared   : {total:,}')
    print(f'modules drifted  : {failures}')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
