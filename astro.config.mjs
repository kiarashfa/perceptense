import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

/**
 * Every absolute URL on the site derives from `site` + `base`, so moving to a
 * different host later is a one-line change here.
 */
export default defineConfig({
  site: 'https://kiarashfa.github.io',
  base: '/perceptense',
  trailingSlash: 'always',
  build: { format: 'directory' },

  // The default collapses whitespace between inline elements, which joins
  // words across tag boundaries ("Sector Finance" -> "SectorFinance").
  compressHTML: false,

  integrations: [
    sitemap({
      changefreq: 'monthly',
      lastmod: new Date(),
    }),
  ],
});
