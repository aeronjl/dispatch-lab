const {chromium}=require('@playwright/test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
(async()=>{
 const root=__dirname;
 const browser=await chromium.launch({headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce',offline:true});
 const page=await context.newPage();
 const errors=[];const requests=[];const checks=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))requests.push(r.url())});
 const record=(name,condition)=>{checks.push({name,outcome:condition?'passed':'failed'});assert(condition,name)};
 try {
  await page.goto(pathToFileURL(path.join(root,'report.html')).href);
  await page.evaluate(()=>document.fonts.ready);
  record('All five embedded figures render offline',await page.locator('img').evaluateAll(imgs=>imgs.length===5&&imgs.every(i=>i.complete&&i.naturalWidth>0)));
  record('Departure font loaded',await page.evaluate(()=>document.fonts.check('15px Departure')));
  record('Desktop document has no horizontal overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(root,'report-desktop.png')});
  await page.getByRole('searchbox').fill('battery');
  record('Topic search isolates battery',await page.locator('nav li:visible').count()===1);
  await page.locator('nav li:visible a').press('Enter');
  record('Keyboard topic navigation moves focus',await page.evaluate(()=>document.activeElement.id.startsWith('battery-')));
  await page.screenshot({path:path.join(root,'report-battery.png')});
  await page.getByRole('searchbox').fill('zzzzzz');
  record('No-match state visible',await page.locator('#empty').isVisible());
  await page.getByRole('searchbox').fill('');
  record('Search reset restores topics',await page.locator('nav li:visible').count()===14);
  await page.setViewportSize({width:390,height:844});
  await page.goto(pathToFileURL(path.join(root,'report.html')).href);
  await page.evaluate(()=>document.fonts.ready);
  record('Narrow screen contains document width',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  record('Wide tables scroll inside their containers',await page.locator('.table-wrap').evaluateAll(t=>t.length>0&&t.every(e=>e.scrollWidth>e.clientWidth&&e.clientWidth<=innerWidth)));
  record('Reduced motion disables smooth scrolling',await page.evaluate(()=>getComputedStyle(document.documentElement).scrollBehavior==='auto'));
  await page.screenshot({path:path.join(root,'report-mobile.png')});
  await page.getByRole('searchbox').fill('hardware');
  await page.locator('nav li:visible a').press('Enter');
  record('Mobile keyboard navigation reaches family taxonomy',await page.evaluate(()=>document.activeElement.id.startsWith('the-14-hardware')));
  await page.screenshot({path:path.join(root,'report-families-mobile.png')});
  record('No external display requests',requests.length===0);
  record('No browser script errors',errors.length===0);
 } finally {
  fs.writeFileSync(path.join(root,'browser-validation.json'),JSON.stringify({scope:'Static research report only; does not test plant UI or physical accuracy.',checks,errors,external_requests:requests},null,2)+'\n');
  await browser.close();
 }
 console.log(`${checks.length} browser checks passed`);
})().catch(e=>{console.error(e);process.exit(1)});
