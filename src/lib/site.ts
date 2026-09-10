/** Single source of truth for anything that depends on where the site lives. */

export const site = {
  brand: 'Perceptense',
  tagline: 'Have a Sense About Everything',
  author: 'Kiarash Farajzadehahary',
  locale: 'en',
  description:
    'A free, self-directed course of 50 interactive modules for building real ' +
    'intuition about numbers, science, culture and the systems that shape daily life.',
} as const;

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
