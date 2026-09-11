"""Fold module classes that merely restate a shared component into that component.

Only touches a class when every one of these holds, so nothing can change what
renders or what scripts can find:

  * the module declares it exactly once, as a plain single-class selector
  * its declaration block is identical to a shared component's
  * the class name appears nowhere else in that module's stylesheet, so no
    compound selector depends on it
  * no script or style block names it at all — six modules build their markup as
    strings, and only the static regions are ever rewritten
  * in those static regions the name appears only inside class="..." attributes,
    so no attribute, comment or expression mentions it

--dead reports the other half of the same problem: single-class rules whose name
appears nowhere in the page at all — not in the markup, not in a script, not in
a style block — so nothing they declare can ever reach an element.

    python tools/consolidate_css.py            # report only
    python tools/consolidate_css.py --apply    # rewrite pages and stylesheets
    python tools/consolidate_css.py --dead     # report unreachable rules
    python tools/consolidate_css.py --dead --apply
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


def split_parts(page: str) -> list[tuple[str, str]]:
    """Split a page into (text, kind) parts, where kind is markup/script/style.

    The three are treated differently. Scripts contain strings such as
    '<div class="x">' that look exactly like markup, so a blind rewrite
    corrupts the JavaScript; only the class attributes inside them may move,
    and only once nothing else in the script names the class. Style blocks are
    never rewritten — a name in one is a rule that depends on it.
    """
    parts: list[tuple[str, str]] = []
    last = 0
    for m in SCRIPT_OR_STYLE.finditer(page):
        if m.start() > last:
            parts.append((page[last:m.start()], 'markup'))
        parts.append((m.group(0), m.group(1).lower()))
        last = m.end()
    if last < len(page):
        parts.append((page[last:], 'markup'))
    return parts


def region(page: str, kind: str) -> str:
    return ''.join(t for t, k in split_parts(page) if k == kind)


def markup_only(page: str) -> str:
    return region(page, 'markup')


def blank_class_attrs(text: str) -> str:
    """The text with every class attribute emptied, for before/after comparison."""
    return re.sub(r'\bclass="[^"]*"', 'class=""', text)


DYNAMIC = re.compile(r'([A-Za-z][\w-]*)(?:\$\{|["\']\s*\+)')


def dynamic_prefixes(page: str) -> set[str]:
    """Literal fragments the page glues a value onto to build a class name.

    Six modules assemble class names at runtime — `planet-color-${p.name}`,
    'bar-' + kind. The finished name never appears in the source, so a rule it
    matches looks unreachable and a rename would never reach the generated
    element. Anything starting with one of these fragments is left alone.
    """
    return {m.group(1) for m in DYNAMIC.finditer(page)}


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


def drop_rule(css: str, name: str) -> str:
    """Delete the single rule whose selector is exactly .name.

    Located through iter_rules rather than by pattern, so a rule introduced by a
    comment is cut like any other; matching on '}' as the left boundary silently
    skipped those and left the rule in place.
    """
    for selector, _decls, (start, end) in iter_rules(css):
        if selector != f'.{name}':
            continue
        line_start = css.rfind('\n', 0, start) + 1
        owns_line = not css[line_start:start].strip()
        if owns_line:
            start = line_start
        while end < len(css) and css[end] in ' \t':
            end += 1
        if owns_line:
            # take the line ending too, so no blank line is left behind
            if css[end:end + 2] == '\r\n':
                end += 2
            elif css[end:end + 1] == '\n':
                end += 1
        else:
            # the rule shared a line: keep the line, drop the gap before it
            while start > line_start and css[start - 1] in ' \t':
                start -= 1
        return css[:start] + css[end:]
    return css


def sweep_dead(apply: bool) -> int:
    """Remove single-class rules no element in the page could ever match."""
    found: dict[str, list[str]] = defaultdict(list)
    for css_file in sorted(MODULE_CSS.glob('*.css')):
        slug = css_file.stem
        page = PAGES / f'{slug}.astro'
        if not page.exists():
            continue
        css = read(css_file)
        raw = read(page)
        built = dynamic_prefixes(raw)

        occurrences: dict[str, int] = defaultdict(int)
        for selector, _decls, _span in iter_rules(css):
            m = SINGLE_CLASS.match(selector)
            if m:
                occurrences[m.group(1)] += 1

        for name, count in occurrences.items():
            if count != 1:
                continue
            if any(name.startswith(p) for p in built):
                continue
            # the one mention in the stylesheet must be this rule's own selector,
            # so no compound selector or media query variant depends on the name
            if len(re.findall(r'(?<![\w-])\.' + re.escape(name) + r'(?![\w-])', css)) != 1:
                continue
            if re.search(r'(?<![\w-])' + re.escape(name) + r'(?![\w-])', raw):
                continue
            found[slug].append(name)

    total = sum(len(v) for v in found.values())
    print(f'modules affected     : {len(found)}')
    print(f'unreachable rules    : {total}')
    print()
    for slug, names in sorted(found.items(), key=lambda kv: -len(kv[1]))[:10]:
        print(f'  {slug:44} {len(names):3}   {", ".join(names[:4])}')

    if not apply:
        print('\nreport only; pass --apply to rewrite')
        return 0

    for slug, names in found.items():
        css_file = MODULE_CSS / f'{slug}.css'
        css = read(css_file)
        for name in names:
            css = drop_rule(css, name)
        write(css_file, css)
    print(f'\nrewritten: {len(found)} stylesheet(s)')
    return 0


def main(argv: list[str]) -> int:
    apply = '--apply' in argv
    if '--dead' in argv:
        return sweep_dead(apply)

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
        raw = read(page)
        # Only non-script regions are ever rewritten, so every check has to be
        # made against exactly that text. Checking the whole page instead lets a
        # class that a script builds ('<div class="war-stat">' inside a template
        # literal) read as an ordinary class attribute: the rule gets deleted
        # and the generated element keeps a name nothing styles any more.
        markup = markup_only(raw)
        script = region(raw, 'script')
        style = region(raw, 'style')

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
            if re.search(r'(?<![\w-])' + re.escape(name) + r'(?![\w-])', style):
                skipped['named in a style block'] += 1
                continue
            if any(name.startswith(p) for p in dynamic_prefixes(raw)):
                skipped['assembled at runtime'] += 1
                continue
            # A class a script builds can move too, but only when the script
            # mentions it purely as markup — never as a selector, a classList
            # argument, or a string it compares against.
            if class_positions_outside_class_attr(markup + script, name):
                skipped['referenced outside a class attribute'] += 1
                continue
            if not re.search(r'\bclass="[^"]*(?<![\w-])' + re.escape(name) + r'(?![\w-])',
                             markup + script):
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

        parts = split_parts(markup)
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
                (re.sub(r'\bclass="([^"]*)"', swap, text) if kind != 'style' else text, kind)
                for text, kind in parts
            ]
            css = drop_rule(css, name)

        rewritten = ''.join(text for text, _ in parts)
        if region(markup, 'style') != region(rewritten, 'style'):
            raise SystemExit(f'{slug}: a style block changed; refusing to write')
        # Scripts may differ only inside class attributes. Blanking those out
        # proves every other byte of JavaScript survived intact.
        if (blank_class_attrs(region(markup, 'script'))
                != blank_class_attrs(region(rewritten, 'script'))):
            raise SystemExit(f'{slug}: a script changed outside a class attribute; refusing to write')

        markup = rewritten
        write(page, markup)
        write(css_file, css)
        changed_pages += 1
        changed_css += 1

    print(f'\nrewritten: {changed_pages} page(s), {changed_css} stylesheet(s)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
