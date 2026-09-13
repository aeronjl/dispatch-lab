// Offline presentation checks; numerical correctness belongs to the saved audits.
const {chromium,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),{pathToFileURL,fileURLToPath}=require('node:url');
(async()=>{
 const input=path.resolve(process.argv[2]),out=path.resolve(process.argv[3]),record=JSON.parse(fs.readFileSync(input.replace(/\.html$/,'.json'),'utf8'));
 fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({headless:true}),errors=[],network=[],checks=[];
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce',offline:true}),page=await context.newPage();
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))network.push(r.url());});
  await page.goto(pathToFileURL(input).href);await page.evaluate(()=>document.fonts.ready);
  await expect(page.locator('h1')).toHaveText('When can the plant manage itself?');await expect(page.locator('#cases tr')).toHaveCount(record.cases.length);
  for(const group of new Set(record.cases.map(c=>c.group))){await page.locator('#group').selectOption(group);await expect(page.locator('#cases tr')).toHaveCount(record.cases.filter(c=>c.group===group).length);}
  await page.locator('#group').selectOption('');
  for(const outcome of new Set(record.cases.map(c=>c.outcome))){await page.locator('#outcome').selectOption(outcome);await expect(page.locator('#cases tr')).toHaveCount(record.cases.filter(c=>c.outcome===outcome).length);}
  await page.locator('#outcome').selectOption('');
  const optionCount=await page.locator('#trace-case option').count();
  for(let i=0;i<optionCount;i++){
   await page.locator('#trace-case').selectOption(String(i));await page.locator('#hour').focus();await page.keyboard.press('End');
   const comparison=await page.evaluate(i=>{const source=JSON.parse(document.querySelector('#data').textContent).series[i].rows.at(-1),shown=JSON.parse(document.querySelector('#trace-values').textContent);return {shown:shown.ending_h2_kg,source:source.h2_kg,hour:shown.interval,last:source.hour};},i);
   if(comparison.shown!==comparison.source||comparison.hour!==comparison.last)throw Error('Wrong selected original operand');
  }
  await page.locator('#trace-case').focus();await page.keyboard.press('Home');await page.keyboard.press('ArrowDown');await expect(page.locator('#trace-case')).toHaveValue('1');
  const links=await page.locator('a[href]').evaluateAll(nodes=>nodes.map(n=>({href:n.href,raw:n.getAttribute('href')})));
  for(const link of links){if(link.raw.startsWith('#'))await expect(page.locator(link.raw)).toHaveCount(1);else if(link.href.startsWith('file:')&&!fs.existsSync(fileURLToPath(link.href)))throw Error('Missing local link: '+link.href);}
  await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(out,'desktop.png')});
  await page.locator('#trace').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'trace.png')});
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(out,'narrow.png')});
  const width=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('main *')].filter(n=>n.getBoundingClientRect().right>innerWidth&&!n.closest('.scroll')).slice(0,5).map(n=>({tag:n.tagName,class:n.className,text:n.textContent.slice(0,80)}))}));
  const value={scope:'Offline browser/keyboard consistency and presentation, not empirical comprehension or numerical validation.',declared_cases:record.cases.length,trace_options_checked:optionCount,local_links_checked:links.length,errors,network,width,reduced_motion:await page.evaluate(()=>matchMedia('(prefers-reduced-motion: reduce)').matches)};
  fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify(value,null,2));console.log(JSON.stringify(value));
  if(errors.length||network.length||width.document>width.viewport)throw Error('Report presentation failed; see checks.json');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
