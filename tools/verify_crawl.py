"""Crawl the built site the way a search engine would: static HTML only, no JS.

Fails if any page is unreachable from the homepage, any internal link is broken,
or any module is a dead end.

    python tools/verify_crawl.py
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'dist'
BASE = '/perceptense'
START = f'{BASE}/'
HREF = re.compile(r'<a\b[^>]*\bhref="([^"]+)"', re.I)


def file_for(url: str) -> Path | None:
    p = url.split('#')[0].split('?')[0]
    if not p.startswith(BASE):
        return None
    rel = p[len(BASE):].lstrip('/')
    if rel.endswith('.html'):
        cand = DIST / rel
        return cand if cand.is_file() else None
    cand = (DIST / rel / 'index.html') if rel else (DIST / 'index.html')
    return cand if cand.is_file() else None


def links_in(fp: Path) -> list[str]:
    html = re.sub(r'<script[\s\S]*?</script>', '', fp.read_text(encoding='utf-8'))
    out = []
    for h in HREF.findall(html):
        if h.startswith(('http://', 'https://', 'mailto:', 'tel:', '#')):
            continue
        out.append(h if h.startswith('/') else f'{BASE}/{h.lstrip("./")}')
    return out


def main() -> int:
    if not (DIST / 'index.html').exists():
        print('no build found; run the build first')
        return 2

    seen = {START: 0}
    inbound = defaultdict(set)
    broken = []
    queue = deque([START])
    while queue:
        url = queue.popleft()
        fp = file_for(url)
        if fp is None:
            continue
        for href in links_in(fp):
            target = re.sub(r'/{2,}', '/', href.split('#')[0])
            if file_for(target) is None:
                broken.append((url, href))
                continue
            inbound[target].add(url)
            if target not in seen:
                seen[target] = seen[url] + 1
                queue.append(target)

    on_disk = set()
    for f in DIST.rglob('index.html'):
        rel = f.parent.relative_to(DIST).as_posix()
        on_disk.add(START if rel == '.' else f'{BASE}/{rel}/')

    orphans = sorted(on_disk - set(seen))
    module_pages = sorted(p for p in on_disk
                          if '/modules/' in p and p.rstrip('/') != f'{BASE}/modules')
    depths = defaultdict(int)
    for d in seen.values():
        depths[d] += 1

    counts = sorted((len(inbound[m]), m) for m in module_pages)
    outdeg = {m: len(set(links_in(file_for(m)))) for m in module_pages}
    dead_ends = [m for m, n in outdeg.items() if n == 0]

    print(f'pages on disk        : {len(on_disk)}')
    print(f'pages reachable      : {len(seen)}')
    print(f'orphan pages         : {len(orphans)} {orphans[:5] if orphans else ""}')
    print(f'broken links         : {len(broken)}')
    for src, href in broken[:8]:
        print(f'    {src}  ->  {href}')
    print('click depth from home:', dict(sorted(depths.items())))
    if module_pages:
        print(f'module pages         : {len(module_pages)}')
        print(f'inbound per module   : min={counts[0][0]} max={counts[-1][0]} '
              f'median={counts[len(counts) // 2][0]}')
        print(f'outbound per module  : min={min(outdeg.values())} max={max(outdeg.values())}')
    print(f'dead-end modules     : {len(dead_ends)}')

    bad = bool(orphans or broken or dead_ends or (counts and counts[0][0] == 0))
    print()
    print('RESULT:', 'FAIL' if bad else
          'PASS - every page reachable, no broken links, no dead ends')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
