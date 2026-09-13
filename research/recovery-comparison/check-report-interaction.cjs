// Offline research-report checks; does not navigate or modify the user's browser.
const {chromium} = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const assert = require('node:assert/strict');
const {createHash} = require('node:crypto');

(async () => {
  const root = path.resolve(__dirname, '../..');
  const browser = await chromium.launch({headless: true});
  const page = await browser.newPage({viewport: {width: 1280, height: 950}});
  const errors = [], requests = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.route(/^https?:/, route => {requests.push(route.request().url()); return route.abort();});
  try {
    await page.goto(pathToFileURL(path.join(__dirname, 'report.html')).href);
    await page.evaluate(() => document.fonts.ready);
    assert(await page.evaluate(() => document.fonts.check('14px Departure')));
    const conditions = await page.locator('#condition option').evaluateAll(options => options.map(x => x.value));
    assert.equal(conditions.length, 16);
    let caseRows = 0;
    for (const condition of conditions) {
      await page.locator('#condition').selectOption(condition);
      const count = await page.locator('#case-table tbody tr').count();
      assert.equal(count, condition === 'null' ? 18 : 9);
      caseRows += count;
      assert.equal(await page.locator('#case-table tbody a').count(), count);
      assert(!/NaN|undefined/.test(await page.locator('#case-table').innerText()));
    }
    assert.equal(caseRows, 153);
    await page.locator('#condition').selectOption('persistent-damage');
    await page.locator('#stocks').click();
    assert.equal(await page.locator('#stocks').getAttribute('aria-pressed'), 'true');
    assert((await page.locator('#case-table').innerText()).includes('Battery kWh'));
    await page.locator('#stocks').click();
    assert.equal(await page.locator('#trace-window option').count(), 2);
    for (const option of ['0', '1']) {
      await page.locator('#trace-window').selectOption(option);
      await page.locator('#trace-hour').evaluate(el => {el.value = 17; el.dispatchEvent(new Event('input', {bubbles: true}));});
      await page.locator('#trace-hour').focus();
      await page.keyboard.press('ArrowRight');
      assert.equal(await page.locator('#trace-hour-label').innerText(), 'H18–19');
      assert(!/NaN|undefined/.test(await page.locator('#trace-plot').innerHTML()));
      assert((await page.locator('#trace-values').innerText()).includes('retrospective physical capacity'));
    }
    const links = await page.locator('a[href]').evaluateAll(a => a.map(x => x.getAttribute('href')));
    for (const href of links) {
      if (href.startsWith('#')) assert.equal(await page.locator(href).count(), 1, href);
      else if (!/^https?:/.test(href)) assert(fs.existsSync(path.resolve(__dirname, href.split('#')[0])), href);
    }
    const captures = path.join(root, 'build/recovery-comparison/report'); fs.mkdirSync(captures, {recursive: true});
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({path: path.join(captures, 'desktop.png')});
    await page.locator('#window').scrollIntoViewIfNeeded();
    await page.screenshot({path: path.join(captures, 'recovery-timeline.png')});
    await page.setViewportSize({width: 390, height: 844});
    await page.emulateMedia({reducedMotion: 'reduce'});
    await page.evaluate(() => scrollTo(0, 0));
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await page.screenshot({path: path.join(captures, 'mobile.png')});
    assert.deepEqual(errors, []); assert.deepEqual(requests, []);
    const result = {status: 'passed', conditions: conditions.length, caseRows, timelineCases: 2,
      keyboardRange: true, stocksToggle: true, localLinks: links.length, localFont: true,
      narrowViewport: [390,844], reducedMotion: true, externalRequests: requests, pageErrors: errors,
      artifacts: Object.fromEntries(['report.html','timeline.js','check-report-interaction.cjs'].map(name => [name, createHash('sha256').update(fs.readFileSync(path.join(__dirname,name))).digest('hex')])),
      scope: 'Offline research report controls and links, separate from the application browser suite.'};
    fs.writeFileSync(path.join(__dirname, 'validation/report-interaction.json'), JSON.stringify(result,null,2), {flag:'wx'});
    console.log(JSON.stringify(result));
  } finally {await browser.close();}
})().catch(error => {console.error(error);process.exitCode=1;});
