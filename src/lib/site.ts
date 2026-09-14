/** Single source of truth for anything that depends on where the site lives. */

import siteData from '../data/site.json';
import modules from '../data/modules.json';
import categories from '../data/categories.json';

/** Collection sizes, for copy that states them. */
export const counts = { modules: modules.length, categories: categories.length };

const WORDS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve'];

/** A count in words up to twelve, in digits beyond. */
export const spelled = (n: number): string => WORDS[n] ?? String(n);

/**
 * Brand strings, shared with the build tools through src/data/site.json.
 * `{modules}` in the description stands for the module count.
 */
export const site = {
  ...siteData,
  description: siteData.description.replaceAll('{modules}', String(counts.modules)),
};

/** Base path with no trailing slash, e.g. "/perceptense". */
export const base = import.meta.env.BASE_URL.replace(/\/$/, '');

/** A site-root-relative path, e.g. path('modules', slug) -> "/perceptense/modules/x/". */
export function path(...parts: Array<string | number>): string {
  const joined = parts
    .map((p) => String(p).replace(/^\/+|\/+$/g, ''))
    .filter(Boolean)
    .join('/');
  return joined ? `${base}/${joined}/` : `${base}/`;
}

/** Absolute URL for canonicals, Open Graph and structured data. */
export function absolute(pathname: string, origin: string): string {
  return new URL(pathname, origin).href;
}

/**
 * Compose a page title. The topic leads, the brand closes; overlong pairings
 * drop the descriptive half rather than being truncated mid-word.
 */
export function pageTitle(name: string, detail?: string): string {
  const suffix = ` | ${site.brand}`;
  const full = detail ? `${name}: ${detail}` : name;
  return (full.length + suffix.length <= 60 ? full : name) + suffix;
}
