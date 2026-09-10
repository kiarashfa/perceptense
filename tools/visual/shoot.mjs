/**
 * Capture a deterministic screenshot of each module's .page-wrap region.
 *
 * Only the content region is captured, so pages can be compared across layouts
 * that differ in surrounding chrome. Randomness, time and animation are frozen
 * before any page script runs, otherwise the interactive modules (quizzes,
 * games, generated charts) would never produce a stable image.
 *
 *   node visual/shoot.mjs <label> <urlTemplateFile>
 */
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const [label, urlsFile] = process.argv.slice(2);
if (!label || !urlsFile) {
  console.error('usage: node visual/shoot.mjs <label> <urls.json>');
  process.exit(1);
}

const targets = JSON.parse(fs.readFileSync(urlsFile, 'utf8'));
const outDir = path.join('visual', 'shots', label);
fs.mkdirSync(outDir, { recursive: true });

// Runs in the page before any other script.
const DETERMINISM = () => {
  // Seeded PRNG so quizzes/games pick the same items every run.
  let seed = 0x2f6e2b1;
  Math.random = () => {
    seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5;
    return ((seed >>> 0) % 1e6) / 1e6;
  };
  // Freeze the clock: several modules render "now" into the DOM.
  const FIXED = new Date('2026-01-01T12:00:00Z').getTime();
  const RealDate = Date;
  // eslint-disable-next-line no-global-assign
  Date = class extends RealDate {
    constructor(...a) { return a.length ? new RealDate(...a) : new RealDate(FIXED); }
    static now() { return FIXED; }
  };
  Date.UTC = RealDate.UTC;
  Date.parse = RealDate.parse;
  // Kill animation and transition timing.
  const kill = document.createElement('style');
  kill.textContent = `*,*::before,*::after{
    animation-duration:0s!important;animation-delay:0s!important;
    transition-duration:0s!important;transition-delay:0s!important;
    caret-color:transparent!important;scroll-behavior:auto!important}`;
  document.documentElement.appendChild(kill);
};

const VIEWPORTS = [
  { name: 'desktop', width: 1280, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
];
const THEMES = ['light', 'dark'];

const browser = await chromium.launch();
let shot = 0;
const failures = [];

for (const vp of VIEWPORTS) {
  for (const theme of THEMES) {
    const ctx = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      deviceScaleFactor: 1,
      colorScheme: theme,
      reducedMotion: 'reduce',
    });
    await ctx.addInitScript(DETERMINISM);

    for (const { slug, url } of targets) {
      const page = await ctx.newPage();
      try {
        await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 });
        // pin the theme explicitly; the site also supports a manual toggle
        await page.evaluate((t) => document.documentElement.setAttribute('data-theme', t), theme);
        await page.evaluate(() => document.fonts && document.fonts.ready);
        await page.waitForTimeout(350);

        const el = await page.$('.page-wrap');
        if (!el) throw new Error('no .page-wrap');
        await el.screenshot({
          path: path.join(outDir, `${slug}__${vp.name}__${theme}.png`),
          animations: 'disabled',
        });
        shot++;
      } catch (err) {
        failures.push(`${slug} ${vp.name} ${theme}: ${err.message}`);
      } finally {
        await page.close();
      }
    }
    await ctx.close();
  }
}
await browser.close();

console.log(`captured ${shot} screenshots into ${outDir}`);
if (failures.length) {
  console.log(`failures (${failures.length}):`);
  failures.forEach((f) => console.log('   ' + f));
  process.exit(1);
}
