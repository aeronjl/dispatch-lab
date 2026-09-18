const {revealOperation}=require('./navigation.cjs');
const {test,expect}=require('@playwright/test');
const fs=require('node:fs');
async function open(page){
 await page.goto('/');await page.locator('.m-plant').waitFor();await page.evaluate(()=>document.fonts.ready);
 await page.getByRole('button',{name:'Playback details',exact:true}).click();
 await page.locator('[data-m=scrubber]').evaluate(n=>{n.value=12;n.dispatchEvent(new Event('input',{bubbles:true}));});
 await page.getByRole('button',{name:'Playback details',exact:true}).click();
 await page.getByRole('button',{name:'Simulation menu',exact:true}).click();
 if(!await page.locator('[data-do=control]').isVisible())await revealOperation(page);await page.locator('[data-do=control]').click();
 await expect(page.locator('.cv-reading h3')).toContainText('Predicted H11');
}
test('control lens reveals plans, delivery and evidence without changing artwork',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await open(page);
 await expect(page.locator('.cv-workspace')).toBeVisible();
 await expect(page.locator('.m-inspector')).toBeHidden();
 await expect(page.locator('.cv-line-0')).toBeVisible();await expect(page.locator('.cv-line-1')).toBeVisible();
 await page.locator('[data-cv=offset]').focus();await page.keyboard.press('ArrowRight');await page.keyboard.press('ArrowRight');
 await expect(page.locator('.cv-reading h3')).toContainText('H13 → 14');
 await expect(page.locator('[data-m=scrubber]')).toHaveValue('12');
 await page.locator('.m-plant [data-component=reactor]').focus();await page.keyboard.press('Enter');
 await expect(page.locator('[data-cv=component]')).toHaveValue('reactor');await expect(page.locator('.m-inspector')).toBeHidden();
 await page.locator('[data-cv-tab=Delivery]').click();await expect(page.locator('.cv-table')).toContainText('Requested');
 await page.locator('[data-cv-tab=Evidence]').click();await expect(page.locator('.cv-evidence')).toContainText('Observe → test → check');
 await page.locator('[data-cv-tab=Plan]').click();
 fs.mkdirSync('build/control-view',{recursive:true});await page.screenshot({path:'build/control-view/desktop.png'});
 await page.keyboard.press('Escape');await expect(page.locator('.cv-workspace')).toBeHidden();
 await expect(page.locator('[data-do=control]')).toBeFocused();
 await page.keyboard.press('Escape');expect(await page.locator('.methane-console button:visible').count()).toBe(5);
 expect(errors).toEqual([]);
});
test('policy fork is explicit, identical-information and separate from recorded playback',async({page})=>{
 await open(page);await page.locator('[data-cv-tab=Compare]').click();
 await expect(page.locator('.cv-reading')).toContainText('same recorded estimate');
 await page.locator('[data-cv=calculate]').click();await expect(page.locator('[data-cv=cancel]')).toBeVisible();
 await expect(page.locator('[data-cv=status]')).toContainText('Comparison complete',{timeout:15000});
 await expect(page.locator('.cv-table').first()).toContainText('MPC · economics');
 await expect(page.locator('.cv-table').last()).toContainText('Termination');
 await expect(page.locator('[data-m=scrubber]')).toHaveValue('12');
 await expect(page.locator('.cv-reading')).toContainText('not alternative realised histories');
 await page.screenshot({path:'build/control-view/comparison.png'});
});
test('late recorded details cannot cross a policy or playhead selection',async({page})=>{
 let delayed=false;
 await page.route('**/dispatch/control-view',async route=>{const body=route.request().postDataJSON();if(body.operation==='describe'&&body.controller==='MPC · methane'&&!delayed){delayed=true;const response=await route.fetch();await new Promise(r=>setTimeout(r,700));await route.fulfill({response});}else await route.continue();});
 await page.goto('/');await page.locator('.m-plant').waitFor();
 await page.getByRole('button',{name:'Simulation menu',exact:true}).click();if(!await page.locator('[data-do=control]').isVisible())await revealOperation(page);await page.locator('[data-do=control]').click();
 await page.locator('[data-cv=controller]').selectOption('Greedy');
 await expect(page.locator('.cv-reading')).toContainText('Use a local dispatch rule');await page.waitForTimeout(800);
 await expect(page.locator('.cv-reading')).toContainText('Use a local dispatch rule');
 await page.getByRole('button',{name:'Step forward',exact:true}).click();
 await expect(page.locator('[data-cv=interval]')).toHaveText('Recorded H0 → 1');
 await expect(page.locator('[data-cv=controller]')).toHaveValue('Greedy');
});
test('cancellation before a start reply prevents a late replacement',async({page})=>{
 await open(page);
 await page.route('**/dispatch/control-view',async route=>{if(route.request().postDataJSON().operation==='start'){const response=await route.fetch();await new Promise(r=>setTimeout(r,800));await route.fulfill({response});}else await route.continue();});
 await page.locator('[data-cv-tab=Compare]').click();await page.locator('[data-cv=calculate]').click();await page.locator('[data-cv=cancel]').click();
 await expect(page.locator('[data-cv=status]')).toHaveText('Comparison cancelled.');await page.waitForTimeout(1100);
 await expect(page.locator('[data-cv=status]')).toHaveText('Comparison cancelled.');await expect(page.locator('.cv-table')).toHaveCount(0);
});
test('narrow screen, recorded event navigation and reduced motion',async({page})=>{
 await page.setViewportSize({width:390,height:844});await open(page);
 await page.locator('[data-cv=component]').selectOption('electrolyser');
 const options=await page.locator('[data-cv=events] option').count();expect(options).toBeGreaterThan(1);
 await page.locator('[data-cv=events]').selectOption({index:1});
 await expect(page.locator('.cv-status')).toBeHidden();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
 expect(await page.locator('.cv-panel').evaluate(n=>getComputedStyle(n).animationName)).toBe('none');
 await page.screenshot({path:'build/control-view/mobile.png'});
 await page.getByRole('button',{name:'Close Control view',exact:true}).click();await expect(page.locator('.cv-workspace')).toBeHidden();
});
test('inspector entry restores its focus and simple controls render promptly',async({page})=>{
 await page.goto('/');await page.locator('.m-plant').waitFor();await page.locator('[data-component=reactor]').focus();await page.keyboard.press('Enter');
 await page.getByRole('button',{name:'WHY',exact:true}).click();await page.locator('[data-do=watch-control]').click();
 await expect(page.locator('[data-cv=component]')).toHaveValue('reactor');await expect(page.locator('.cv-reading')).toBeVisible();
 for(let i=0;i<24;i++)await page.locator('[data-cv=component]').selectOption(['solar','battery','electrolyser','hydrogen','co2','reactor'][i%6]);
 const times=await page.evaluate(()=>performance.getEntriesByName('dispatch-control-render').map(e=>e.duration));times.sort((a,b)=>a-b);
 const p95=times[Math.floor(times.length*.95)];fs.mkdirSync('build/control-view',{recursive:true});fs.writeFileSync('build/control-view/performance.json',JSON.stringify({fixture:'browser-demo-v2',scope:'Control pane synchronous render; excludes network and optimiser',samples_ms:times,p95_ms:p95},null,2));expect(p95).toBeLessThanOrEqual(10);
 await page.keyboard.press('Escape');await expect(page.locator('.m-inspector')).toBeVisible();await expect(page.locator('[data-do=watch-control]')).toBeFocused();
 await expect(page.getByRole('button',{name:'WHY',exact:true})).toHaveAttribute('aria-pressed','true');
});
