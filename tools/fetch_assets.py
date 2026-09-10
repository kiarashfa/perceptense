"""Download the remaining third-party assets so the site serves everything itself.

  * country flags used by the diplomacy module
  * the author photograph used on the about page

Re-running only fetches what is missing.

    python tools/fetch_assets.py
"""
from __future__ import annotations

import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLAGS = ROOT / 'public' / 'flags'
IMAGES = ROOT / 'public' / 'images'
DIPLOMACY = ROOT / 'src' / 'pages' / 'modules' / 'diplomacy.astro'
ABOUT = ROOT / 'src' / 'pages' / 'about.astro'

# One size is downloaded and scaled down where a smaller flag is shown, so the
# list renders crisply on high-density displays from a single file.
FLAG_SIZE = 'w80'
UA = {'User-Agent': 'Mozilla/5.0 (compatible; perceptense-build)'}


def get(url: str, tries: int = 3) -> bytes | None:
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == tries - 1:
                return None
            time.sleep(1 + attempt)
    return None


def fetch_flags() -> int:
    codes = sorted(set(re.findall(r"iso:'([a-z]{2})'", DIPLOMACY.read_text(encoding='utf-8'))))
    FLAGS.mkdir(parents=True, exist_ok=True)
    got = skipped = failed = 0
    total = 0
    for code in codes:
        target = FLAGS / f'{code}.png'
        if target.exists():
            skipped += 1
            total += target.stat().st_size
            continue
        data = get(f'https://flagcdn.com/{FLAG_SIZE}/{code}.png')
        if data is None or not data.startswith(b'\x89PNG'):
            print(f'  failed: {code}')
            failed += 1
            continue
        target.write_bytes(data)
        got += 1
        total += len(data)
    print(f'flags: {got} downloaded, {skipped} already present, {failed} failed '
          f'({total / 1024:.0f} KB total for {len(codes)} countries)')
    return failed


def fetch_photo() -> int:
    text = ABOUT.read_text(encoding='utf-8')
    m = re.search(r'https://raw\.githubusercontent\.com/[^"\')\s]+\.(png|jpg|jpeg|webp)', text)
    if not m:
        print('photo: no remote image referenced')
        return 0
    url = m.group(0)
    IMAGES.mkdir(parents=True, exist_ok=True)
    target = IMAGES / ('author' + Path(url).suffix)
    if target.exists():
        print(f'photo: already present ({target.stat().st_size / 1024:.0f} KB)')
        return 0
    data = get(url)
    if data is None:
        print(f'photo: failed to download {url}')
        return 1
    target.write_bytes(data)
    print(f'photo: {target.relative_to(ROOT)} ({len(data) / 1024:.0f} KB)')
    return 0


def main() -> int:
    failed = fetch_flags() + fetch_photo()
    if failed:
        print(f'\n{failed} asset(s) could not be fetched')
        return 1
    print('\nall external assets are now local')
    return 0


if __name__ == '__main__':
    sys.exit(main())
