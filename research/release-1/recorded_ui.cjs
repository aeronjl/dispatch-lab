const {chromium,expect}=require('@playwright/test');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true}),page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:7861/');await page.locator('.m-plant').waitFor();
 await page.locator('[data-m=scrubber]').evaluate(n=>{n.value=20;n.dispatchEvent(new Event('input',{bubbles:true}))});
 const physical=()=>page.locator('.m-plant [data-svg]').evaluateAll(nodes=>nodes.filter(n=>!n.dataset.svg.includes('cost')).map(n=>[n.dataset.svg,n.textContent]));
 const before=await physical();
 await page.getByRole('button',{name:'Simulation menu',exact:true}).click();await page.locator('[data-panel=services]').click();
 await page.getByRole('button',{name:'Trace this service decision',exact:true}).click();
 await expect(page.locator('.d-reference-body')).toContainText('recovery_obligation');
 const estimate=page.getByRole('heading',{name:'Estimated state at decision time',exact:true}).locator('xpath=following-sibling::table[1]');
 const expected=JSON.parse(fs.readFileSync('build/release-1/receipts/original-estimate.json'));
 await expect(page.locator('.d-reference-body')).toContainText('interval '+expected.interval);
 for(const [key,value] of Object.entries(expected.estimate)){
  await expect(estimate).toContainText(key);await expect(estimate).toContainText(typeof value==='number'?value.toLocaleString('en-GB',{maximumFractionDigits:3}):String(value));
 }
 await expect(page.locator('.d-reference-body')).toContainText('scheduled-load-tests/5');
 await page.locator('.d-reference').screenshot({path:'build/release-1/screenshots/recorded-recovery.png'});
 const estimateText=await estimate.innerText();await page.keyboard.press('Escape');
 await expect(page.getByRole('button',{name:'Trace this service decision',exact:true})).toBeFocused();
 await page.keyboard.press('Escape');await page.getByRole('button',{name:'Simulation menu',exact:true}).click();await page.locator('[data-do=setup]').first().click();
 if(!await page.getByRole('checkbox',{name:'Use complete service accounting',exact:true}).isVisible())await page.getByText('Economic assumptions / component costs and decision value',{exact:true}).click();
 await page.getByRole('spinbutton',{name:'rates / crew eur per hour',exact:true}).fill('100');
 const started=Date.now();await page.getByRole('button',{name:'Reprice completed run',exact:true}).click();
 await expect(page.getByText('Cost report repriced.',{exact:false})).toBeVisible({timeout:30000});const repriceMs=Date.now()-started;
 await page.getByRole('button',{name:'← Simulation',exact:true}).click();await expect(page.locator('[data-m=scrubber]')).toHaveValue('20');
 const after=await physical();expect(after).toEqual(before);
 await page.getByRole('button',{name:'Simulation menu',exact:true}).click();await page.locator('[data-panel=services]').click();await page.getByRole('button',{name:'Trace service costs',exact:true}).click();
 await expect(page.locator('.d-reference-body')).toContainText('dispatch_service_price_version');await expect(page.locator('.d-reference-body')).toContainText('report_service_price_version');
 fs.writeFileSync('build/release-1/receipts/recorded-service-ui.json',JSON.stringify({version:'release-recorded-service-ui/1',recorded_estimate:estimateText,playhead_boundary:20,interval:expected.interval,original_policy:'scheduled-load-tests/5',repricing_ms:repriceMs,physical_display_preserved:true,errors,scope:'Original version-5 archive rendered by current reader; repricing waits for the full report and retains its physical display and original price identity. Full-report repricing is measured separately from simple example latency.'},null,2));
 await browser.close();console.log('Recorded recovery and repricing passed',repriceMs);if(errors.length)process.exitCode=1;
})().catch(e=>{console.error(e);process.exit(1)});
