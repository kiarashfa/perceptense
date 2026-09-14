import type { APIRoute } from 'astro';
import { site, base } from '../lib/site';

/** Web app manifest; generated so every URL in it carries the base path. */
export const GET: APIRoute = () =>
  new Response(
    JSON.stringify(
      {
        name: `${site.brand}: ${site.tagline}`,
        short_name: site.brand,
        description: site.description,
        lang: site.locale,
        start_url: `${base}/`,
        scope: `${base}/`,
        display: 'standalone',
        background_color: '#10212E',
        theme_color: '#10212E',
        icons: [192, 512].map((size) => ({
          src: `${base}/assets/favicons/icon-${size}.png`,
          sizes: `${size}x${size}`,
          type: 'image/png',
        })),
      },
      null,
      2,
    ),
    { headers: { 'Content-Type': 'application/manifest+json' } },
  );
