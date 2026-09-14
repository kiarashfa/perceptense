"""Collapse per-element style variants into one rule plus custom properties.

Two kinds of variant family, both found inside a single module:

--data   Chart data. Classes that exist only to give one bar, fill or marker its
         size, position or colour, e.g. `.tb-copper { width: 83%; background:
         #185fa5 }`. Every element carrying such a class also carries one
         structural class (`tb`). The family becomes a single rule
             .tb-data { width: var(--data-width); background: var(--data-background) }
         and each element carries its own values:
             class="tb tb-data" style="--data-width: 83%; --data-background: #185fa5"

--tints  Colour variants. Classes whose declarations are identical except for
         literal colours, sharing a name stem of at least two words, e.g.
         `.factor-panel-reputation` and `.factor-panel-provenance`. The shared
         declarations move into a base class named after the stem, the varying
         ones read custom properties, and each variant keeps only its values:
             .factor-panel { border-radius: ...; background: var(--tint-background) }
             .factor-panel-reputation { --tint-background: #eeedfe }
         Every element with a variant class also gets the base class.

Cascade position and specificity are kept: the new rule takes the place of the
family's first rule and is a single class like the rules it replaces.

A family is left alone when any member class is declared more than once or
inside an at-rule, used by any other selector, named in a script or style
block, assembled at runtime, mentioned outside a plain class attribute, used on
an element whose style attribute is an expression, or carries !important; or
when the new class or custom property name already exists anywhere.

    python tools/variant_styles.py --data  [--modules a,b] [--apply]
    python tools/variant_styles.py --tints [--modules a,b] [--apply]
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

from consolidate_css import (MODULE_CSS, PAGES, dynamic_prefixes, read, region,
                             split_parts, word, write)

ROOT = Path(__file__).resolve().parent.parent
STYLES = ROOT / 'src' / 'styles'
GLOBAL_SHEETS = ['shared.css', 'components.css', 'chrome.css', 'home.css', 'about.css', 'fonts.css']

SINGLE = re.compile(r'^\.([a-z][\w-]*)$')
UTILITY = re.compile(r'^(u-[\w-]+|(text|bg|border)-[a-z]+-\d+)$')
COLOUR = re.compile(r'#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)')
DATA_PROPS = {'width', 'height', 'left', 'right', 'top', 'bottom', 'flex'}
TAG = re.compile(r'<[a-zA-Z][\w:-]*(?:\s+[^\s"\'<>=/{}]+(?:\s*=\s*(?:"[^"]*"|\'[^\']*\'|\{[^{}]*\}|[^\s"\'<>]+))?)*\s*/?>')
CLASS_ATTR = re.compile(r'\bclass="([^"]*)"')
STYLE_ATTR = re.compile(r'\bstyle="([^"]*)"')


def rules_with_spans(css: str):
    """Top-level rules: (selector, [(prop, value)], start, end, depth_ok)."""
    blank = re.sub(r'/\*[\s\S]*?\*/', lambda m: ' ' * len(m.group(0)), css)
    out = []
    stack: list[tuple[int, int]] = []
    start = 0
    for t in re.finditer(r'[{}]', blank):
        if t.group() == '{':
            stack.append((start, t.start()))
            start = t.end()
            continue
        s0, s1 = stack.pop()
        raw_sel = blank[s0:s1]
        selector = re.sub(r'\s+', ' ', raw_sel).strip()
        body = css[s1 + 1:t.start()]
        if '{' not in blank[s1 + 1:t.start()] and selector and not selector.startswith('@'):
            decls = []
            for d in re.sub(r'/\*[\s\S]*?\*/', '', body).split(';'):
                if ':' in d:
                    k, _, v = d.partition(':')
                    decls.append((k.strip(), re.sub(r'\s+', ' ', v).strip()))
            lead = len(raw_sel) - len(raw_sel.lstrip())
            out.append((selector, decls, s0 + lead, t.end(), not stack))
        start = t.end()
    return out


def cut(css: str, start: int, end: int, replacement: str = '') -> str:
    """Replace css[start:end]; when it owned its lines and is being removed, take the line too."""
    line_start = css.rfind('\n', 0, start) + 1
    if not replacement and not css[line_start:start].strip():
        start = line_start
        while end < len(css) and css[end] in ' \t':
            end += 1
        if css[end:end + 2] == '\r\n':
            end += 2
        elif css[end:end + 1] == '\n':
            end += 1
        # take the blank separator line too, when the rule had one on both sides
        before_blank = css[:start].endswith(('\n\n', '\r\n\r\n'))
        after = re.match(r'[ \t]*\r?\n', css[end:])
        if before_blank and after:
            end += after.end()
    return css[:start] + replacement + css[end:]


def taken_names() -> tuple[set[str], str]:
    classes: set[str] = set()
    text = ''
    for name in GLOBAL_SHEETS:
        sheet = STYLES / name
        if sheet.exists():
            s = read(sheet)
            text += s
            classes.update(re.findall(r'\.([A-Za-z_][\w-]*)', s))
    return classes, text


def members_blocked(names, css, raw, counts, nested) -> str | None:
    markup = ''.join(t for t, k in split_parts(raw) if k == 'markup')
    script, style = region(raw, 'script'), region(raw, 'style')
    built = dynamic_prefixes(raw)
    spans_ok = [m.span(1) for m in CLASS_ATTR.finditer(markup)]
    for n in names:
        if counts[n] != 1 or n in nested:
            return f'{n} declared more than once or inside an at-rule'
        if len(re.findall(r'(?<![\w-])\.' + re.escape(n) + r'(?![\w-])', css)) != 1:
            return f'{n} used by another selector'
        if re.search(word(n), script) or re.search(word(n), style):
            return f'{n} named in a script or style block'
        if any(n.startswith(p) for p in built):
            return f'{n} may be assembled at runtime'
        for m in re.finditer(word(n), markup):
            if not any(a <= m.start() and m.end() <= b for a, b in spans_ok):
                return f'{n} mentioned outside a class attribute'
    return None


def rewrite_tags(raw: str, edit) -> str:
    """Apply edit(tag_text) to every tag in the static markup regions only."""
    parts = []
    for text, kind in split_parts(raw):
        if kind == 'markup':
            text = TAG.sub(lambda m: edit(m.group(0)), text)
        parts.append(text)
    return ''.join(parts)


def plan_module(slug: str, mode: str, taken: set[str], taken_text: str):
    css = read(MODULE_CSS / f'{slug}.css')
    raw = read(PAGES / f'{slug}.astro')
    markup = ''.join(t for t, k in split_parts(raw) if k == 'markup')
    rules = rules_with_spans(css)
    counts: dict[str, int] = defaultdict(int)
    nested: set[str] = set()
    single: dict[str, tuple] = {}
    for sel, decls, s, e, top in rules:
        m = SINGLE.match(sel)
        if m:
            counts[m.group(1)] += 1
            if not top:
                nested.add(m.group(1))
            else:
                single[m.group(1)] = (decls, s, e)
    local_classes = set(re.findall(r'\.([A-Za-z_][\w-]*)', css)) | {c for a in CLASS_ATTR.findall(raw) for c in a.split()}

    families = []
    skipped: dict[str, int] = defaultdict(int)
    if mode == 'data':
        groups = defaultdict(list)
        for name, (decls, s, e) in single.items():
            if UTILITY.match(name):
                continue
            props = {k.lower(): v for k, v in decls}
            if not any(p in DATA_PROPS and '%' in v for p, v in props.items()):
                continue
            attrs = [a.split() for a in CLASS_ATTR.findall(markup) if name in a.split()]
            if not attrs:
                continue
            common = set(attrs[0]) - {name}
            for a in attrs[1:]:
                common &= set(a)
            common -= {n for n in common if UTILITY.match(n)}
            if not common:
                continue
            groups[(sorted(common)[0], tuple(sorted(props)))].append(name)
        for (base, props), names in groups.items():
            if len(names) < 2:
                continue
            new_class = f'{base}-data'
            var = {p: f'--data-{p}' for p in props}
            families.append({'kind': 'data', 'base': base, 'class': new_class, 'names': names, 'props': list(props), 'var': var})
    else:
        groups = defaultdict(list)
        for name, (decls, s, e) in single.items():
            if UTILITY.match(name):
                continue
            if not any(COLOUR.search(v) for _, v in decls):
                continue
            if any(k.lower() in DATA_PROPS and '%' in v for k, v in decls):
                continue
            masked = tuple(sorted((k.lower(), COLOUR.sub('C', v)) for k, v in decls))
            groups[masked].append(name)
        for masked, names in groups.items():
            if len(names) < 2:
                continue
            prefix = []
            for seg in zip(*(n.split('-') for n in names)):
                if len(set(seg)) != 1:
                    break
                prefix.append(seg[0])
            if len(prefix) < 2 or any(len(n.split('-')) <= len(prefix) for n in names):
                skipped['no two-word stem'] += 1
                continue
            stem = '-'.join(prefix)
            values = defaultdict(set)
            for n in names:
                for k, v in single[n][0]:
                    values[k.lower()].add(v)
            varying = [p for p in sorted(values) if len(values[p]) > 1]
            var = {p: f'--tint-{p}' for p in varying}
            families.append({'kind': 'tints', 'base': stem, 'class': stem, 'names': names, 'props': varying, 'var': var})

    # Two families can land on the same new class. Chart families get a suffix
    # naming the properties the larger family lacks; colour families sharing a
    # stem are left alone, because one base class would carry both blocks.
    by_class = defaultdict(list)
    for f in families:
        by_class[f['class']].append(f)
    resolved = []
    for name, group in by_class.items():
        if len(group) == 1:
            resolved.append(group[0])
            continue
        if mode == 'tints':
            skipped['stem shared by two colour families'] += len(group)
            continue
        group.sort(key=lambda f: -len(f['names']))
        resolved.append(group[0])
        used = {name}
        for f in group[1:]:
            extra = sorted(set(f['props']) - set(group[0]['props'])) or sorted(set(group[0]['props']) - set(f['props']))
            suffix = '-'.join(extra) if extra else 'alt'
            f['class'] = f'{name}-{suffix}'
            if f['class'] in used:
                skipped['chart families not told apart'] += len(f['names'])
                continue
            used.add(f['class'])
            resolved.append(f)
    families = resolved

    planned = []
    for f in families:
        why = members_blocked(f['names'], css, raw, counts, nested)
        if not why and any('!important' in v for n in f['names'] for _, v in single[n][0]):
            why = '!important'
        if not why:
            new = f['class']
            if new in taken or new in local_classes or re.search(word(new), raw):
                why = f'{new} already exists'
            elif any(v in taken_text or v in css or v in raw for v in f['var'].values()):
                why = 'custom property name already in use'
        if not why:
            for tag in TAG.findall(markup):
                cm = CLASS_ATTR.search(tag)
                if cm and set(cm.group(1).split()) & set(f['names']) and re.search(r'\bstyle=\{', tag):
                    why = 'element style is an expression'
                    break
        if why:
            skipped[why.split(' ', 1)[1] if why.split(' ', 1)[0] in f['names'] else why] += 1
            continue
        planned.append(f)
    return css, raw, single, planned, skipped


def apply_family(css: str, raw: str, single: dict, f: dict):
    names = f['names']
    order = sorted(names, key=lambda n: single[n][1])
    first = order[0]
    decls0, s0, e0 = single[first]
    indent = css[css.rfind('\n', 0, s0) + 1:s0]

    if f['kind'] == 'data':
        body = ''.join(f'{indent}  {p}: var({f["var"][p]});\n' for p in f['props'])
        new_rule = f'.{f["class"]} {{\n{body}{indent}}}'
        edits = [(s0, e0, new_rule)] + [(single[n][1], single[n][2], '') for n in order[1:]]
        values = {n: {k.lower(): v for k, v in single[n][0]} for n in names}

        def edit(tag: str) -> str:
            cm = CLASS_ATTR.search(tag)
            if not cm:
                return tag
            classes = cm.group(1).split()
            hit = [c for c in classes if c in values]
            if not hit:
                return tag
            n = hit[0]
            out = []
            for c in classes:
                c = f['class'] if c == n else c
                if c not in out:
                    out.append(c)
            tag = tag[:cm.start()] + f'class="{" ".join(out)}"' + tag[cm.end():]
            decl = '; '.join(f'{f["var"][p]}: {values[n][p]}' for p in f['props'])
            sm = STYLE_ATTR.search(tag)
            if sm:
                existing = sm.group(1).strip().rstrip(';')
                merged = f'{existing}; {decl}' if existing else decl
                tag = tag[:sm.start()] + f'style="{merged}"' + tag[sm.end():]
            else:
                cm2 = CLASS_ATTR.search(tag)
                tag = tag[:cm2.end()] + f' style="{decl}"' + tag[cm2.end():]
            return tag
    else:
        shared = [(k, v) for k, v in decls0 if k.lower() not in f['var']]
        refs = [(k, f'var({f["var"][k.lower()]})') for k, v in decls0 if k.lower() in f['var']]
        body = ''.join(f'{indent}  {k}: {v};\n' for k, v in [*shared, *refs])
        base_rule = f'.{f["class"]} {{\n{body}{indent}}}\n{indent}'
        edits = []
        for n in order:
            decls, s, e = single[n]
            vbody = ''.join(f'{indent}  {f["var"][k.lower()]}: {v};\n' for k, v in decls if k.lower() in f['var'])
            text = f'.{n} {{\n{vbody}{indent}}}'
            edits.append((s, e, (base_rule if n == first else '') + text))

        def edit(tag: str) -> str:
            cm = CLASS_ATTR.search(tag)
            if not cm:
                return tag
            classes = cm.group(1).split()
            if not set(classes) & set(names) or f['class'] in classes:
                return tag
            out = []
            for c in classes:
                if c in names:
                    out.append(f['class'])
                out.append(c)
            return tag[:cm.start()] + f'class="{" ".join(out)}"' + tag[cm.end():]

    for s, e, text in sorted(edits, key=lambda x: -x[0]):
        css = cut(css, s, e, text)
    new_raw = rewrite_tags(raw, edit)
    return css, new_raw


def main(argv: list[str]) -> int:
    mode = 'data' if '--data' in argv else 'tints' if '--tints' in argv else None
    if not mode:
        print(__doc__)
        return 2
    apply = '--apply' in argv
    only = set(argv[argv.index('--modules') + 1].split(',')) if '--modules' in argv else None
    taken, taken_text = taken_names()

    total_families = total_rules = 0
    skipped_all: dict[str, int] = defaultdict(int)
    changed = []
    for css_file in sorted(MODULE_CSS.glob('*.css')):
        slug = css_file.stem
        if only is not None and slug not in only:
            continue
        if not (PAGES / f'{slug}.astro').exists():
            continue
        css, raw, single, planned, skipped = plan_module(slug, mode, taken, taken_text)
        for k, v in skipped.items():
            skipped_all[k] += v
        if not planned:
            continue
        total_families += len(planned)
        total_rules += sum(len(f['names']) for f in planned)
        print(f'  {slug:36} ' + ', '.join(f'{f["class"]} ({len(f["names"])})' for f in planned))
        if not apply:
            continue
        new_css, new_raw = css, raw
        for f in planned:
            _, _, single_now, _, _ = plan_module_state(new_css, new_raw)
            new_css, new_raw = apply_family(new_css, new_raw, single_now, f)
        if region(raw, 'script') != region(new_raw, 'script') or region(raw, 'style') != region(new_raw, 'style'):
            raise SystemExit(f'{slug}: a script or style block changed; refusing to write')
        write(MODULE_CSS / f'{slug}.css', new_css)
        write(PAGES / f'{slug}.astro', new_raw)
        changed.append(slug)

    print(f'\nmode              : {mode}')
    print(f'families planned  : {total_families} ({total_rules} rules)')
    print('skipped           : ' + (', '.join(f'{k} x{v}' for k, v in sorted(skipped_all.items())) or 'none'))
    print(f'rewritten         : {len(changed)} module(s)' if apply else 'report only; pass --apply to rewrite')
    return 0


def plan_module_state(css: str, raw: str):
    """Re-read rule spans from in-progress text, so later families use fresh offsets."""
    single = {}
    for sel, decls, s, e, top in rules_with_spans(css):
        m = SINGLE.match(sel)
        if m and top:
            single[m.group(1)] = (decls, s, e)
    return css, raw, single, None, None


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
