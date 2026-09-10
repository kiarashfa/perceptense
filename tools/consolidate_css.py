"""Fold module classes that merely restate a shared component into that component.

Only touches a class when every one of these holds, so nothing can change what
renders or what scripts can find:

  * the module declares it exactly once, as a plain single-class selector
  * its declaration block is identical to a shared component's
  * the class name appears nowhere else in that module's stylesheet, so no
    compound selector depends on it
  * the class name appears in the page only inside class="..." attributes, so no
    script queries it and no attribute or string mentions it

    python tools/consolidate_css.py            # report only
    python tools/consolidate_css.py --apply    # rewrite pages and stylesheets
"""
from __future__ import annotations

import io
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE_CSS = ROOT / 'src' / 'styles' / 'modules-src'
PAGES = ROOT / 'src' / 'pages' / 'modules'
SHARED = ROOT / 'src' / 'styles' / 'shared.css'

SINGLE_CLASS = re.compile(r'^\.([A-Za-z][\w-]*)$')


def read(p) -> str:
    with io.open(p, encoding='utf-8', newline='') as fh:
        return fh.read()


def write(p, t: str) -> None:
    with io.open(p, 'w', encoding='utf-8', newline='') as fh:
        fh.write(t)


def iter_rules(css: str):
    """Yield (selector, declarations, span) for every top-level-ish rule."""
    stripped = re.sub(r'/\*[\s\S]*?\*/', lambda m: ' ' * len(m.group(0)), css)
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', stripped):
        selector = re.sub(r'\s+', ' ', m.group(1)).strip()
        if not selector or selector.startswith('@'):
            continue
        decls = {}
        for d in m.group(2).split(';'):
            if ':' in d:
                k, _, v = d.partition(':')
                decls[k.strip().lower()] = re.sub(r'\s+', ' ', v).strip().lower()
        if decls:
            yield selector, decls, (m.start(), m.end())


def block_key(decls: dict) -> tuple:
    return tuple(sorted(decls.items()))


SCRIPT_OR_STYLE = re.compile(r'<(script|style)\b[^>]*>[\s\S]*?</\1>', re.I)


def split_markup(page: str) -> list[tuple[str, bool]]:
    """Split a page into (text, is_markup) parts, isolating script and style.

    Scripts contain strings such as '<div class="x">' that look exactly like
    markup; rewriting inside them corrupts the JavaScript.
    """
    parts: list[tuple[str, bool]] = []
    last = 0
    for m in SCRIPT_OR_STYLE.finditer(page):
        if m.start() > last:
            parts.append((page[last:m.start()], True))
        parts.append((m.group(0), False))
        last = m.end()
    if last < len(page):
        parts.append((page[last:], True))
    return parts


def markup_only(page: str) -> str:
    return ''.join(t for t, is_markup in split_markup(page) if is_markup)


def class_positions_outside_class_attr(text: str, name: str) -> bool:
    """True when the class name occurs anywhere other than inside class="...".

    Anything else — a script, a data attribute, a comment — means renaming it
    could break something invisible to the stylesheet.
    """
    spans = [m.span(1) for m in re.finditer(r'\bclass="([^"]*)"', text)]
    for m in re.finditer(r'(?<![\w-])' + re.escape(name) + r'(?![\w-])', text):
        if not any(a <= m.start() and m.end() <= b for a, b in spans):
            return True
    return False


def main(argv: list[str]) -> int:
    apply = '--apply' in argv

    # Utility classes are never merge targets: folding a meaningful name like
    # .diagram-svg into .u-shrink-0 removes a rule but moves a styling decision
    # into the markup and loses the name. Only shared components qualify.
    shared_blocks: dict[tuple, str] = {}
    for selector, decls, _ in iter_rules(read(SHARED)):
        m = SINGLE_CLASS.match(selector)
        if m and not m.group(1).startswith('u-') and block_key(decls) not in shared_blocks:
            shared_blocks[block_key(decls)] = m.group(1)

    planned: dict[str, list[tuple[str, str]]] = defaultdict(list)   # module -> [(from, to)]
    skipped: dict[str, int] = defaultdict(int)

    for css_file in sorted(MODULE_CSS.glob('*.css')):
        slug = css_file.stem
        page = PAGES / f'{slug}.astro'
        if not page.exists():
            continue
        css = read(css_file)
        markup = read(page)

        occurrences: dict[str, int] = defaultdict(int)
        rules: dict[str, tuple[dict, tuple[int, int]]] = {}
        for selector, decls, span in iter_rules(css):
            m = SINGLE_CLASS.match(selector)
            if m:
                occurrences[m.group(1)] += 1
                rules[m.group(1)] = (decls, span)

        for name, (decls, _span) in rules.items():
            target = shared_blocks.get(block_key(decls))
            if not target or target == name:
                continue
            if occurrences[name] != 1:
                skipped['declared more than once'] += 1
                continue
            # the class must not appear in any other selector in this stylesheet
            others = re.findall(r'(?<![\w-])\.' + re.escape(name) + r'(?![\w-])', css)
            if len(others) != 1:
                skipped['used by another selector'] += 1
                continue
            if class_positions_outside_class_attr(markup, name):
                skipped['referenced outside a class attribute'] += 1
                continue
            if not re.search(r'\bclass="[^"]*(?<![\w-])' + re.escape(name) + r'(?![\w-])', markup):
                skipped['not used in the markup'] += 1
                continue
            planned[slug].append((name, target))

    total = sum(len(v) for v in planned.values())
    print(f'shared components available : {len(shared_blocks)}')
    print(f'modules affected            : {len(planned)}')
    print(f'class merges planned        : {total}')
    print('skipped for safety          : ' + (', '.join(f'{k} x{v}' for k, v in skipped.items()) or 'none'))
    print()
    for slug, pairs in sorted(planned.items(), key=lambda kv: -len(kv[1]))[:10]:
        preview = ', '.join(f'{a} -> {b}' for a, b in pairs[:3])
        print(f'  {slug:44} {len(pairs):3}   {preview}')

    if not apply:
        print('\nreport only; pass --apply to rewrite')
        return 0

    changed_pages = changed_css = 0
    for slug, pairs in planned.items():
        page = PAGES / f'{slug}.astro'
        css_file = MODULE_CSS / f'{slug}.css'
        markup = read(page)
        css = read(css_file)

        parts = split_markup(markup)
        for name, target in pairs:
            def swap(m: re.Match) -> str:
                classes = m.group(1).split()
                if name not in classes:
                    return m.group(0)          # leave unrelated attributes untouched
                out, seen = [], set()
                for c in classes:
                    c = target if c == name else c
                    if c not in seen:
                        seen.add(c)
                        out.append(c)
                return f'class="{" ".join(out)}"'

            parts = [
                (re.sub(r'\bclass="([^"]*)"', swap, text) if is_markup else text, is_markup)
                for text, is_markup in parts
            ]
            css = re.sub(
                r'(^|\})(\s*)\.' + re.escape(name) + r'\s*\{[^{}]*\}',
                lambda m: m.group(1), css, count=1)

        rewritten = ''.join(text for text, _ in parts)
        before = [t for t, is_markup in split_markup(markup) if not is_markup]
        after = [t for t, is_markup in split_markup(rewritten) if not is_markup]
        if before != after:
            raise SystemExit(f'{slug}: a script or style block changed; refusing to write')

        markup = rewritten
        write(page, markup)
        write(css_file, css)
        changed_pages += 1
        changed_css += 1

    print(f'\nrewritten: {changed_pages} page(s), {changed_css} stylesheet(s)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
