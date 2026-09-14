import { defineConfig, envField } from 'astro/config';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: 'https://kiarashfa.github.io',
  base: '/perceptense',
  trailingSlash: 'always',
  build: { format: 'directory' },

  env: {
    schema: {
      // Google Analytics 4 measurement ID. Analytics are omitted when unset.
      GA_MEASUREMENT_ID: envField.string({ context: 'server', access: 'public', optional: true }),
    },
  },

  // The default collapses whitespace between inline elements, which joins
  // words across tag boundaries ("Sector Finance" -> "SectorFinance").
  compressHTML: false,

  integrations: [
    sitemap({
      changefreq: 'monthly',
      lastmod: new Date(),
      // Legacy .html addresses are redirect stubs, not content.
      filter: (page) => !/\.html$/.test(page),
    }),
  ],
});
