"""Cut static instances of the site's variable IBM Plex Sans for the og step.

The social cards are drawn from glyph outlines, and the outline library reads
static TrueType fonts only. Instances are written to node_modules/.cache/og-fonts/
and rebuilt only when a source font changes.

    python tools/build_og_fonts.py
"""
from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / 'public' / 'fonts'
OUT = ROOT / 'node_modules' / '.cache' / 'og-fonts'
SUBSETS = ('ibm-plex-sans-latin', 'ibm-plex-sans-latin-ext')
WEIGHTS = (400, 600)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for subset in SUBSETS:
        source = FONTS / f'{subset}.woff2'
        for weight in WEIGHTS:
            target = OUT / f'{subset}-{weight}.ttf'
            if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
                continue
            font = instantiateVariableFont(TTFont(source), {'wght': weight})
            font.flavor = None
            font.save(target)
    print(f'og fonts: {len(SUBSETS) * len(WEIGHTS)} instances -> '
          f'{OUT.relative_to(ROOT).as_posix()}/')


if __name__ == '__main__':
    main()
