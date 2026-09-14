const {chromium,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path');
(async()=>{
 const root=__dirname,report=path.join(root,'report.html'),browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
 const errors=[],requests=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))requests.push(r.url())});
 await page.context().setOffline(true);await page.goto('file://'+report);await expect(page.locator('h1')).toHaveText('Qualified reference autonomy');
 await expect(page.locator('#case option')).toHaveCount(104);
 for(let i=0;i<104;i++){
  await page.locator('#case').selectOption(String(i));
  await page.locator('#hour').evaluate(n=>{n.value=n.max;n.dispatchEvent(new Event('input',{bubbles:true}))});
  const expected=await page.evaluate(i=>{const c=data.cases[i];return {hour:c.trace.at(-1).hour,case:c.case_id,study:c.study_id}},i);
  const shown=JSON.parse(await page.locator('#operands').textContent());expect(shown.hour).toEqual(expected.hour);expect(shown.case).toEqual(expected.case);expect(shown.study).toEqual(expected.study);
  expect(await page.locator('#plot').innerHTML()).not.toMatch(/NaN|undefined/);
  expect(JSON.parse(await page.locator('#ending').textContent()).plant).toBeTruthy();
 }
 await page.locator('#case').selectOption('0');await page.locator('#hour').focus();await page.keyboard.press('Home');await page.keyboard.press('ArrowRight');await expect(page.locator('#hour')).toHaveValue('1');
 await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'build/release-1/screenshots/publication-desktop.png'});
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();await page.screenshot({path:'build/release-1/screenshots/publication-mobile.png'});
 const links=await page.locator('a[href]').evaluateAll(ns=>ns.map(n=>n.getAttribute('href')));
 for(const href of links){if(href.startsWith('#')){expect(await page.locator(href).count()).toBeGreaterThan(0)}else if(!/^https?:/.test(href)){expect(fs.existsSync(path.resolve(root,href.split('#')[0])),href).toBeTruthy()}}
 const saved=path.resolve('build/release-1/release-example/offline/model-report.html');await page.goto('file://'+saved);
 const summary=JSON.parse(fs.readFileSync('build/release-1/release-example/summary.json'));
 for(const topic of summary.topics){await expect(page.locator('#'+topic)).toHaveCount(1);await expect(page.getByRole('heading',{name:topic+' · saved learning output',exact:true})).toHaveCount(1);}
 expect(errors).toEqual([]);expect(requests).toEqual([]);
 const result={version:'release-publication-browser/1',status:'passed',cases:104,keyboard:true,narrow_screen:true,local_links:links.length,saved_topics:summary.topics.length,network_requests:requests,errors,scope:'Read-only report/recorded Model outputs, offline Chromium. No claim of participant comprehension or remote artifact backup.'};
 fs.writeFileSync(path.join(root,'publication-check.json'),JSON.stringify(result,null,2));await browser.close();console.log(JSON.stringify(result));
})().catch(e=>{console.error(e);process.exit(1)});
