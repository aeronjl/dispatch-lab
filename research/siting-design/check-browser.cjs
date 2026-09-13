// Isolated file-based research report verification. Does not touch the running app.
const {chromium} = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {pathToFileURL} = require('node:url');
const crypto = require('node:crypto');
const root = __dirname;
const build = path.resolve(root, '../../build/siting-design');
const url = pathToFileURL(path.join(root, 'report.html')).href;
const hash = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
(async()=>{
  fs.mkdirSync(build,{recursive:true});
  const browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  const errors=[], external=[], checks=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route(/^https?:\/\//,route=>{external.push(route.request().url());return route.abort()});
  const done = name => checks.push({name,passed:true});
  try {
    await page.goto(url);await page.evaluate(()=>document.fonts.ready);
    await page.locator('#annual-yield').waitFor();
    assert.equal(await page.locator('h2[id]').count(),12);done('12 anchored report sections');
    for(let i=0;i<6;i++) {await page.locator(`[data-stage="${i}"]`).click();assert.equal(await page.locator(`[data-stage="${i}"]`).getAttribute('aria-pressed'),'true')}
    done('six proposed journey stages');
    for(let i=0;i<19;i++){await page.locator(`[data-family="${i}"]`).click();assert.ok(await page.locator('#family-detail h3').textContent())}
    await page.locator('#family-search').fill('unmatchable-test');assert.equal(await page.locator('[data-family]').count(),0);
    await page.locator('#clear-search').click();assert.equal(await page.locator('[data-family]').count(),19);
    await page.locator('#family-search').fill('water');assert.ok(await page.locator('[data-family]').count()>0);
    await page.locator('#clear-search').click();done('19 data families, search, empty state and reset');
    const data=JSON.parse(fs.readFileSync(path.join(root,'retrieval-20260913/resource-samples.json')));
    for(let i=0;i<3;i++){
      await page.locator(`[data-site="${i}"]`).click();
      assert.equal(Number((await page.locator('#annual-yield').textContent()).replaceAll(',','')),data.sites[i].annual.E_y);
      for(let month=0;month<12;month++){await page.locator('#month-select').selectOption(String(month));const text=await page.locator('#month-output').textContent();assert.ok(text.includes(data.sites[i].monthly[month].E_m.toFixed(2)))}
      assert.equal(await page.locator('.chart rect').count(),12);
    }
    done('all 36 monthly outputs and three annual outputs reconcile to saved data');
    await page.locator('[data-site="0"]').focus();await page.keyboard.press('Tab');await page.keyboard.press('Enter');
    assert.equal(await page.locator('[data-site="1"]').getAttribute('aria-pressed'),'true');done('keyboard site selection');
    await page.locator('a[href="#section-7"]').first().click();assert.equal(new URL(page.url()).hash,'#section-7');done('section navigation');
    await page.goto(url);await page.evaluate(()=>document.fonts.ready);
    await page.screenshot({path:path.join(build,'desktop.png')});
    await page.locator('#resource-example').scrollIntoViewIfNeeded();await page.locator('#resource-example').screenshot({path:path.join(build,'resource.png')});
    await page.setViewportSize({width:390,height:844});await page.goto(url);await page.evaluate(()=>document.fonts.ready);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.screenshot({path:path.join(build,'mobile.png')});
    await page.locator('#data-catalogue').scrollIntoViewIfNeeded();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.locator('#resource-example').scrollIntoViewIfNeeded();await page.locator('#month-select').selectOption('7');
    await page.locator('#resource-example').screenshot({path:path.join(build,'resource-mobile.png')});
    done('390px layout, resource control and reduced motion');
    const nojs=await browser.newPage({javaScriptEnabled:false});await nojs.goto(url);assert.ok((await nojs.locator('noscript').textContent()).includes('1010.28'));await nojs.close();done('no-script saved yield fallback');
    assert.deepEqual(errors,[]);assert.deepEqual(external,[]);done('no page errors or network requests during report use');
    const result={checked_at:new Date().toISOString(),scope:'Isolated report interaction only. Not the application or proposed Sites feature.',checks,errors,external_requests:external,files:Object.fromEntries(['report.html','report.css','report.js','check-browser.cjs'].map(f=>[f,hash(path.join(root,f))])),screenshots:Object.fromEntries(['desktop.png','resource.png','mobile.png','resource-mobile.png'].map(f=>['../../build/siting-design/'+f,hash(path.join(build,f))]))};
    fs.writeFileSync(path.join(root,'browser-validation.json'),JSON.stringify(result,null,2)+'\n');
    console.log(`${checks.length} browser check groups passed; screenshots in ${build}`);
  } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
