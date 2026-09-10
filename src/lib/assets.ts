import fontsCss from '../styles/fonts.css?raw';
import sharedCss from '../styles/shared.css?raw';
import iconsBaseCss from '../styles/icons-base.css?raw';
import chromeCss from '../styles/chrome.css?raw';

/**
 * Short content hash used as a cache-busting query on the shared stylesheet.
 *
 * The sheet is linked from <head> rather than imported, so it always precedes
 * bundled module CSS and Astro does not hash its filename for us. The content
 * arrives through the bundler as a string, so this works the same during dev,
 * build and prerender — reading it from disk does not, because the compiled
 * module no longer sits next to the file.
 */
function fnv1a(input: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, '0');
}

export const sharedCssHash = fnv1a(fontsCss + sharedCss + iconsBaseCss + chromeCss);
