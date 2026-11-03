/** Render already-generated local reports. This is not a human visual approval. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require('playwright');

async function findReports(directory) {
  const reports = [];
  for (const entry of await fs.readdir(directory, {withFileTypes: true})) {
    const file = path.join(directory, entry.name);
    if (entry.isDirectory()) reports.push(...await findReports(file));
    else if (entry.name === 'START-HERE.html') reports.push(file);
  }
  return reports.sort();
}

async function inspectPage(page) {
  return page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([...document.images].map(img => img.decode()));
    const luminance = color => {
      const values = color.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => {
        v /= 255;
        return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
      });
      return values[0] * 0.2126 + values[1] * 0.7152 + values[2] * 0.0722;
    };
    const contrast = [...document.querySelectorAll('.muted,small')].map(el => {
      let background = el;
      while (background && getComputedStyle(background).backgroundColor === 'rgba(0, 0, 0, 0)') {
        background = background.parentElement;
      }
      const foreground = luminance(getComputedStyle(el).color);
      const back = luminance(getComputedStyle(background).backgroundColor);
      return {text: el.textContent, ratio: (Math.max(foreground, back) + 0.05) /
        (Math.min(foreground, back) + 0.05)};
    });
    return {
      viewport: innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      images: [...document.images].map(img => ({alt: img.alt, loaded: img.complete &&
        img.naturalWidth > 0 && img.clientWidth > 0 && img.clientHeight > 0})),
      contrast,
      details: document.querySelectorAll('details').length,
      replacementCharacters: document.body.textContent.includes('\ufffd'),
    };
  });
}

async function main() {
  const [input, output] = process.argv.slice(2);
  assert(input && output, 'Usage: node audit.cjs REPORT_DIRECTORY QA_OUTPUT_DIRECTORY');
  const root = path.resolve(input);
  const destination = path.resolve(output);
  assert(destination !== root && !destination.startsWith(root + path.sep),
    'Keep QA output outside the generated report directory');
  await fs.mkdir(destination, {recursive: true});
  const manifest = path.join(destination, 'browser-qa.json');
  // A failed rerun must never leave an earlier passing manifest authoritative.
  await fs.writeFile(manifest, JSON.stringify({status: 'running',
    manual_visual_review_completed: false}) + '\n');
  let browser;
  const results = [];
  try {
    const reports = await findReports(root);
    assert(reports.length, 'No START-HERE.html found');
    browser = await chromium.launch({headless: true,
      ...(process.env.BROWSER_QA_CHANNEL ? {channel: process.env.BROWSER_QA_CHANNEL} : {})});
    for (const report of reports) {
      const relative = path.relative(root, report);
      const folder = path.join(destination, path.dirname(relative));
      await fs.mkdir(folder, {recursive: true});
      for (const viewport of [{width: 1440, height: 1000}, {width: 390, height: 844},
        {width: 320, height: 740}]) {
        const context = await browser.newContext({viewport, deviceScaleFactor: 1,
          serviceWorkers: 'block'});
        const page = await context.newPage();
        const networkRequests = [];
        await context.route(/^https?:/, route => {
          networkRequests.push(route.request().url());
          return route.abort();
        });
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        try {
          await page.goto(pathToFileURL(report).href);
          // Exercise native keyboard behavior instead of merely changing the open attribute.
          for (const summary of await page.locator('details > summary').all()) {
            await summary.focus();
            await page.keyboard.press('Enter');
            assert(await summary.evaluate(el => el.parentElement.open), 'Details did not open');
            await page.keyboard.press('Enter');
            assert(!await summary.evaluate(el => el.parentElement.open), 'Details did not close');
          }
          for (const state of ['closed', 'open']) {
            await page.locator('details').evaluateAll((nodes, open) => {
              nodes.forEach(node => { node.open = open; });
            }, state === 'open');
            const checks = await inspectPage(page);
            assert(checks.documentWidth <= viewport.width + 1,
              `${relative}: page overflow at ${viewport.width}px (${state})`);
            assert(checks.images.length && checks.images.every(img => img.loaded && img.alt),
              `${relative}: image failed to render`);
            assert(checks.contrast.every(item => item.ratio >= 4.5),
              `${relative}: small text contrast below 4.5:1`);
            assert(!checks.replacementCharacters, `${relative}: invalid Unicode`);
            const screenshot = path.join(folder, `${viewport.width}-${state}.png`);
            await page.screenshot({path: screenshot, fullPage: true});
            results.push({report: relative, viewport, state, checks,
              screenshot: path.relative(destination, screenshot)});
          }
          assert.deepEqual(networkRequests, [], 'Report attempted external HTTP requests');
          assert.deepEqual(errors, [], 'Browser JavaScript error');
        } finally {
          await context.close();
        }
      }
    }
    await fs.writeFile(manifest, JSON.stringify({
      schema_version: '1.0', status: 'automated_browser_checks_passed',
      browser: browser.version(), report_count: reports.length, browser_rendered: true,
      mobile_viewport_checked: true, manual_visual_review_completed: false,
      real_repository_accuracy_audited: false, aws_account_checked: false, results,
    }, null, 2) + '\n');
    console.log(`${reports.length} reports, ${results.length} rendered states passed`);
  } catch (error) {
    await fs.writeFile(manifest, JSON.stringify({status: 'failed',
      error: error.message, manual_visual_review_completed: false, results}, null, 2) + '\n');
    throw error;
  } finally {
    if (browser) await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
