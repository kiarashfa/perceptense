"""Repair unclosed <div> wrappers in a legacy module, verifying nothing else changes.

Walks the body with a real tag stack, so every inserted </div> is attributed to
the exact opening tag it closes. Closes only what is genuinely left open and
never invents elements. Verifies the result with the HTML5 parsing algorithm
(the same one browsers use) so rendered text is provably unchanged.
"""
import re
import sys
import html5lib

TAG = re.compile(r'<(/?)div\b[^>]*?(/?)>')
PART = re.compile(r'[ \t]*<!--\s*PART\s+[A-Z]\s*-->')


def read(p):
    with open(p, encoding='utf-8', newline='') as fh:
        return fh.read()


def write(p, t):
    with open(p, 'w', encoding='utf-8', newline='') as fh:
        fh.write(t)


def blank_out(s):
    s = re.sub(r'<script[\s\S]*?</script>', lambda m: '\n' * m.group(0).count('\n'), s)
    return re.sub(r'<style[\s\S]*?</style>', lambda m: '\n' * m.group(0).count('\n'), s)


def dom_text(html):
    doc = html5lib.parse(html, namespaceHTMLElements=False)
    for el in doc.iter():
        if el.tag in ('script', 'style'):
            el.text = ''
    return re.sub(r'\s+', ' ', ''.join(doc.itertext())).strip()


def plan(body, line_of):
    """Walk the body once, returning (insert_position, count, [tags_closed])."""
    probe = blank_out(body)
    boundaries = [m.start() for m in PART.finditer(probe)]
    stack, inserts, bi = [], [], 0

    for m in TAG.finditer(probe):
        # settle any PART boundary we have just crossed
        while bi < len(boundaries) and boundaries[bi] <= m.start():
            if len(stack) > 1:
                closing = stack[1:]
                inserts.append((boundaries[bi], len(closing), list(closing)))
                del stack[1:]
            bi += 1
        if m.group(2) == '/':
            continue
        if m.group(1):
            if stack:
                stack.pop()
        else:
            stack.append(f'<div…>@L{line_of(m.start())} '
                         f'{re.sub(r"\\s+", " ", m.group(0))[:44]}')

    while bi < len(boundaries):
        if len(stack) > 1:
            inserts.append((boundaries[bi], len(stack) - 1, list(stack[1:])))
            del stack[1:]
        bi += 1
    if stack:
        inserts.append((len(body.rstrip()), len(stack), list(stack)))
    return inserts


def repair(path, out_path, apply=True):
    raw = read(path)
    b0 = raw.find('>', raw.find('<body')) + 1
    b1 = raw.rfind('</body>')
    head, body, tail = raw[:b0], raw[b0:b1], raw[b1:]
    base = raw[:b0].count('\n') + 1

    def line_of(pos):
        return base + body[:pos].count('\n')

    inserts = plan(body, line_of)
    if not inserts:
        print(f'{path}: already well-formed, nothing to do')
        return False

    print(f'--- {path}')
    for pos, n, tags in inserts:
        print(f'    line {line_of(pos):>5}: insert {n} </div>  closing:')
        for t in tags:
            print(f'                    {t}')

    new_body = body
    for pos, n, _ in sorted(inserts, key=lambda x: -x[0]):
        at_end = pos >= len(body.rstrip())
        text = ('\n' + '</div>' * n) if at_end else ''.join('  </div>\n' for _ in range(n))
        new_body = new_body[:pos] + text + new_body[pos:]
    new_raw = head + new_body + tail

    # --- verification ---
    probe2 = blank_out(new_body)
    depth = 0
    off = []
    bounds = [m.start() for m in PART.finditer(probe2)]
    bi = 0
    for m in TAG.finditer(probe2):
        while bi < len(bounds) and bounds[bi] <= m.start():
            if depth != 1:
                off.append(depth)
            bi += 1
        if m.group(2) == '/':
            continue
        depth += -1 if m.group(1) else 1

    same_text = dom_text(raw) == dom_text(new_raw)
    na_before = [c for c in raw if ord(c) > 127]
    na_after = [c for c in new_raw if ord(c) > 127]

    print(f'    final div balance      : {depth} (want 0)')
    print(f'    PART comments off-depth: {off or "none"}')
    print(f'    rendered text identical: {same_text}')
    print(f'    non-ASCII preserved    : {na_before == na_after} '
          f'({len(na_before)} chars)')

    ok = depth == 0 and not off and same_text and na_before == na_after
    if not ok:
        print('    REPAIR REJECTED — verification failed')
        return False
    if apply:
        write(out_path, new_raw)
        print(f'    verified, written -> {out_path}')
    return True


if __name__ == '__main__':
    repair(sys.argv[1], sys.argv[2])
