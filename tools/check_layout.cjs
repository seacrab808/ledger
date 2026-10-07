// Optional visual QA with an existing Playwright installation; installs nothing.
const { chromium } = require('playwright');
const path = require('node:path');
const fs = require('node:fs');
const { pathToFileURL } = require('node:url');

(async () => {
  const root = path.resolve(__dirname, '..');
  const output = path.join(root, 'artifacts', 'qa');
  fs.mkdirSync(output, { recursive: true });
  const options = { headless: true };
  if (process.env.LEDGER_BROWSER_PATH) options.executablePath = process.env.LEDGER_BROWSER_PATH;
  const browser = await chromium.launch(options);
  try {
    for (const width of [1280, 390]) {
      const context = await browser.newContext({ viewport: { width, height: 900 }, offline: true });
      const page = await context.newPage();
      for (const name of ['index', 'research-map', 'phase-01', 'experiment-log', 'decision-log', 'glossary']) {
        await page.goto(pathToFileURL(path.join(root, 'docs', name + '.html')).href);
        const layout = await page.evaluate(() => ({
          width: document.documentElement.clientWidth,
          scrollWidth: document.documentElement.scrollWidth,
          heading: document.querySelector('h1')?.textContent,
          navLinks: document.querySelectorAll('nav a').length
        }));
        if (layout.scrollWidth > layout.width + 1 || !layout.heading || layout.navLinks !== 6) {
          throw new Error(`${name}/${width}: ${JSON.stringify(layout)}`);
        }
        if (name === 'index' || name === 'phase-01') {
          await page.screenshot({ path: path.join(output, `${name}-${width}.png`), fullPage: true });
        }
        console.log(`${name}/${width}: offline layout passed`);
      }
      await context.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
