"""Report what the module stylesheets could collapse into.

Groups every rule in src/styles/modules-src by its declaration block so that
classes which merely restate an existing shared component, or each other, become
visible. Read-only: it changes nothing.

    python tools/analyse_css.py
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE_CSS = ROOT / 'src' / 'styles' / 'modules-src'
SHARED_CSS = ROOT / 'src' / 'styles' / 'shared.css'

NUMBERED = re.compile(r'-\d+$')
UTILITY = re.compile(r'^u-')


def rules(css: str):
    css = re.sub(r'/\*[\s\S]*?\*/', '', css)
    css = re.sub(r'@media[^{]*\{', '', css)
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
        selector = re.sub(r'\s+', ' ', m.group(1)).strip()
        if not selector or selector.startswith('@'):
            continue
        decls = {}
        for d in m.group(2).split(';'):
            if ':' in d:
                k, _, v = d.partition(':')
                decls[k.strip().lower()] = re.sub(r'\s+', ' ', v).strip().lower()
        if decls:
            yield selector, decls


def key(decls: dict) -> tuple:
    return tuple(sorted(decls.items()))


def main() -> int:
    shared_by_block: dict[tuple, list[str]] = defaultdict(list)
    for selector, decls in rules(SHARED_CSS.read_text(encoding='utf-8')):
        shared_by_block[key(decls)].append(selector)

    module_rules: list[tuple[str, str, dict]] = []
    for f in sorted(MODULE_CSS.glob('*.css')):
        for selector, decls in rules(f.read_text(encoding='utf-8')):
            module_rules.append((f.stem, selector, decls))

    simple = [(mod, sel, d) for mod, sel, d in module_rules
              if re.fullmatch(r'\.[A-Za-z][\w-]*', sel)]

    # 1. module classes whose block already exists in shared.css
    restates: dict[str, list[str]] = defaultdict(list)
    for mod, sel, d in simple:
        match = shared_by_block.get(key(d))
        if match:
            restates[match[0]].append(f'{mod}{sel}')

    # 2. module classes that duplicate each other
    by_block: dict[tuple, list[str]] = defaultdict(list)
    for mod, sel, d in simple:
        by_block[key(d)].append(f'{mod}{sel}')
    clusters = sorted((v for v in by_block.values() if len(v) > 1), key=len, reverse=True)

    # 3. how many are throwaway names
    names = Counter()
    for mod, sel, d in simple:
        names[sel[1:]] += 1
    numbered = [n for n in names if NUMBERED.search(n)]
    utility = [n for n in names if UTILITY.match(n)]

    # 4. value sprawl on the properties that matter
    print('=== module stylesheets ===')
    print(f'rules            : {len(module_rules)}')
    print(f'single-class rules: {len(simple)}')
    print(f'distinct classes : {len(names)}')
    print(f'  numbered names : {len(numbered)}')
    print(f'  utility names  : {len(utility)}')
    print()

    total_restated = sum(len(v) for v in restates.values())
    print('=== 1. module classes that restate an existing shared component ===')
    print(f'{total_restated} rule(s) across {len(restates)} shared component(s)\n')
    for shared_sel, users in sorted(restates.items(), key=lambda kv: -len(kv[1]))[:12]:
        print(f'  {shared_sel:26} <- {len(users):4} rule(s)   e.g. {", ".join(users[:3])}')

    print()
    print('=== 2. module classes that duplicate each other ===')
    print(f'{len(clusters)} cluster(s) covering {sum(len(c) for c in clusters)} rules\n')
    for c in clusters[:10]:
        print(f'  {len(c):3} identical: {", ".join(sorted(c)[:4])}{" ..." if len(c) > 4 else ""}')

    print()
    print('=== 3. value sprawl ===')
    for prop in ('padding', 'margin-bottom', 'gap', 'font-size', 'border-radius'):
        vals = Counter(d[prop] for _, _, d in module_rules if prop in d)
        top = ', '.join(f'{k} x{v}' for k, v in vals.most_common(5))
        covered = sum(v for _, v in vals.most_common(5)) / max(1, sum(vals.values())) * 100
        print(f'  {prop:14} {len(vals):3} distinct, {sum(vals.values()):4} uses; '
              f'top 5 cover {covered:.0f}%  [{top}]')

    reducible = total_restated + sum(len(c) - 1 for c in clusters)
    print()
    print(f'rules removable without changing any rendered value: ~{reducible} '
          f'of {len(simple)} ({reducible / max(1, len(simple)) * 100:.0f}%)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
