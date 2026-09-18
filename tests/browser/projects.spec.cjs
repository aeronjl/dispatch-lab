const {test,expect}=require('@playwright/test');
async function openProject(page){if(!await page.locator('[data-do=project]').isVisible())await page.locator('[data-do=menu]').click();await page.locator('[data-do=project]').click();}
async function project(page){await page.goto('/');await page.locator('.m-plant').waitFor();await openProject(page);await expect(page.locator('.pj-sites button').first()).toBeVisible();await page.locator('.pj-sites button').first().click();await page.locator('[data-pj=create]').click();await expect(page.locator('.pj-build')).toBeVisible();}
test('project progressively reveals settings, preserves artwork and restores a design',async({page})=>{
 const errors=[];page.on('pageerror',err=>errors.push(err.message));await project(page);
 await expect(page.locator('.pj-inspector')).toBeHidden();await expect(page.locator('.pj-drawing [data-pj-component]')).toHaveCount(6);
 await page.locator('.pj-drawing [data-pj-component=battery]').focus();await page.keyboard.press('Enter');
 await expect(page.locator('.pj-inspector h2')).toHaveText('Battery');await expect(page.locator('[data-pj-field]')).toHaveCount(2);
 await page.locator('[data-pj-field="plant.battery_kwh"]').fill('1200');await expect(page.locator('[data-pj-save-state]')).toHaveText('Unsaved changes');
 await page.locator('[data-pj=save]').click();await expect(page.locator('[data-pj-save-state]')).toHaveText('Saved');
 await page.locator('[data-pj=more]').click();await expect(page.locator('[data-pj-field="plant.roundtrip_efficiency"]')).toBeVisible();
 await page.locator('[data-pj-field="plant.battery_kwh"]').fill('-1');await expect(page.locator('.pj-status')).toContainText('previous valid');
 await expect(page.locator('.pj-drawing [data-pj-svg=battery]')).toHaveText('1200 kWh');
 await page.locator('[data-pj-field="plant.battery_kwh"]').fill('1200');await expect(page.locator('[data-pj-save-state]')).toHaveText('Saved');
 await page.keyboard.press('Escape');await expect(page.locator('.pj-inspector')).toBeHidden();
 await page.locator('[data-pj=equipment]').click();await expect(page.locator('.pj-inspector')).toContainText('Dock, DC charging');await page.locator('[data-pj-equipment=cleaner]').click();await expect(page.locator('[data-pj-equipment=cleaner]')).toHaveText('Remove');
 await page.keyboard.press('Escape');await page.locator('[data-pj=settings]').click();await page.locator('[data-pj-field-search]').fill('solver');await expect(page.locator('[data-pj-field="scenario.solver_seconds"]')).toBeVisible();
 await page.keyboard.press('Escape');await page.locator('[data-pj=close]').click();await expect(page.locator('.pj-workspace')).toBeHidden();await expect(page.locator('[data-do=project]')).toBeFocused();
 await page.reload();await openProject(page);await page.locator('.pj-header [data-pj=build]').click();await expect(page.locator('.pj-build')).toBeVisible();await expect(page.locator('.pj-drawing [data-pj-svg=battery]')).toHaveText('1200 kWh');
 await page.mouse.move(0,0);await page.screenshot({path:'build/project-build-desktop.png'});
 await page.setViewportSize({width:390,height:844});await page.locator('[data-pj=settings]').click();await expect(page.locator('.pj-inspector')).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:'build/project-settings-mobile.png'});expect(errors).toEqual([]);
});
test('project calculates explicit weather, plays saved operation and compares a revised design',async({page})=>{
 test.setTimeout(120000);const errors=[];page.on('pageerror',err=>errors.push(err.message));await project(page);
 await page.locator('.pj-build-bottom [data-pj=operate]').click();await expect(page.locator('.pj-run')).toBeVisible();
 await page.locator('[data-pj-weather]').selectOption('synthetic');await expect(page.locator('.pj-weather-context')).toContainText('not estimate this site');
 await page.locator('[data-pj-hours]').selectOption('24');await page.locator('[data-pj-controller]').selectOption('Greedy');await page.locator('[data-pj=run]').click();
 await expect(page.locator('[data-pj-play]').first()).toBeVisible({timeout:60000});await expect(page.locator('.pj-run-progress')).toContainText('Playback does not run the solver');
 await page.locator('[data-pj-play]').first().click();await expect(page.locator('.pj-workspace')).toBeHidden();
 await expect(page.locator('[data-do=project-revise]')).toBeVisible({timeout:20000});
 const playbackBoundary=await page.locator('[data-m=scrubber]').inputValue();
 await page.locator('.m-inspector [data-do=investigate]').click();await expect(page.locator('.iv-totals')).toContainText('Methane');
 await expect(page.locator('[data-iv-context]')).toContainText('Greedy');await page.locator('[data-iv=pin]').click();
 await page.locator('[data-iv=save]').click();await expect(page.locator('.iv-status')).toContainText('Saved. Original run unchanged.');
 await page.keyboard.press('Escape');await expect(page.locator('[data-m=scrubber]')).toHaveValue(playbackBoundary);await expect(page.locator('.m-inspector [data-do=investigate]')).toBeFocused();
 await page.locator('[data-do=project-revise]').click();
 await page.locator('[data-pj-field="plant.battery_kwh"]').fill('1600');await page.locator('[data-pj=save]').click();await page.locator('.pj-header [data-pj=operate]').click();
 await expect(page.locator('.pj-run h1')).toHaveText('Compare a revised design');await expect(page.locator('[data-pj-weather]')).toBeDisabled();await expect(page.locator('[data-pj-controller]')).toHaveValue('Greedy');
 await page.locator('[data-pj=run]').click();await expect(page.locator('[data-pj-play]:not([data-pj-destination])')).toHaveCount(2,{timeout:60000});await expect(page.locator('.pj-table tbody tr')).toHaveCount(2);await expect(page.locator('.pj-run-progress')).toContainText('Calculation complete');
 await page.screenshot({path:'build/project-comparison.png'});expect(errors).toEqual([]);
});
test('project reveals model and site tools and returns with context intact',async({page})=>{
 await project(page);await page.locator('.pj-drawing [data-pj-component=battery]').click();await page.locator('[data-pj=model]').click();await expect(page.locator('.d-workspace')).toBeVisible();await page.keyboard.press('Escape');await expect(page.locator('.pj-inspector h2')).toHaveText('Battery');
 await page.locator('[data-pj=close]').click();await page.locator('[data-do=menu]').click();await page.keyboard.press('Escape');await openProject(page);
 await page.locator('.pj-header [data-pj=site]').click();await page.locator('.pj-site-card [data-pj=site-details]').click();await expect(page.locator('.si-workspace')).toBeVisible();await page.keyboard.press('Escape');await expect(page.locator('.pj-site-card h2')).toBeVisible();
 await page.locator('.pj-header [data-pj=build]').click();await page.locator('[data-pj=equipment]').click();await page.locator('[data-pj=taxonomy]').click();await expect(page.locator('.x-workspace')).toBeVisible();await page.keyboard.press('Escape');await expect(page.locator('.pj-inspector')).toBeVisible();
});
test('missing weather stays incomplete and stale previews cannot replace a newer edit',async({page})=>{
 await project(page);await page.locator('.pj-drawing [data-pj-component=battery]').click();
 await page.route('**/dispatch/sites',async route=>{const body=route.request().postDataJSON();if(body.operation==='project-preview'&&body.data.config.plant.battery_kwh===900){const response=await route.fetch();await new Promise(r=>setTimeout(r,600));await route.fulfill({response});}else await route.continue();});
 await page.locator('[data-pj-field="plant.battery_kwh"]').fill('900');await page.waitForTimeout(300);await page.locator('[data-pj-field="plant.battery_kwh"]').fill('1300');await expect(page.locator('.pj-drawing [data-pj-svg=battery]')).toHaveText('1300 kWh');await page.waitForTimeout(700);await expect(page.locator('.pj-drawing [data-pj-svg=battery]')).toHaveText('1300 kWh');
 await page.locator('[data-pj=save]').click();await page.locator('.pj-header [data-pj=operate]').click();await page.locator('[data-pj-weather]').selectOption('retrieve');await page.locator('[data-pj-offline]').check();await page.locator('[data-pj=run]').click();await expect(page.locator('.pj-run-progress')).toContainText('incomplete',{timeout:20000});await expect(page.locator('[data-pj-weather]')).toHaveValue('retrieve');await expect(page.locator('[data-pj-play]')).toHaveCount(0);
});

test('fresh project entry starts at Site without opening configuration panels',async({page})=>{
 test.skip(!process.env.DISPATCH_PROJECT_START,'Explicit first-entry app fixture');await page.goto('/');await expect(page.locator('.pj-workspace')).toBeVisible();await expect(page.locator('.pj-site-panel h1')).toHaveText('Where would you build?');await expect(page.locator('.pj-inspector')).toBeHidden();await expect(page.locator('.pj-build')).toBeHidden();await expect(page.locator('.pj-sites button')).toHaveCount(3);await expect(page.locator('.pj-workspace')).toHaveAttribute('data-map-ready','true');expect((await page.locator('.pj-map').boundingBox()).height).toBeGreaterThan(800);await page.screenshot({path:'build/project-site-desktop.png'});
});

test('common design preview stays responsive on the reference fixture',async({page})=>{
 await project(page);await page.locator('.pj-drawing [data-pj-component=battery]').click();const samples=[];
 for(let i=0;i<20;i++)samples.push(await page.evaluate(i=>new Promise(resolve=>{const label=document.querySelector('.pj-drawing [data-pj-svg=battery]'),value=1000+i,start=performance.now();const observer=new MutationObserver(()=>{if(label.textContent===value+' kWh'){observer.disconnect();resolve(performance.now()-start);}});observer.observe(label,{childList:true});const input=document.querySelector('[data-pj-field="plant.battery_kwh"]');input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));}),i));
 const sorted=[...samples].sort((a,b)=>a-b),p95=sorted[Math.ceil(sorted.length*.95)-1];require('node:fs').writeFileSync('build/project-preview-performance.json',JSON.stringify({scope:'20 common battery edits on the isolated reference browser; no concurrent batch',samples_ms:samples,p95_ms:p95},null,2));expect(p95).toBeLessThan(200);
});

test('new design does not inherit recorded fault or thermal appearance',async({page})=>{
 await page.goto('/');await page.locator('.m-plant').waitFor();await openProject(page);await page.locator('.pj-sites button').first().click();
 // The scene is paused before setting a recorded appearance; opening the menu
 // itself legitimately redraws the original scene from its recorded state.
 await page.locator('.m-plant .stack-component').evaluate(n=>n.dataset.fault='true');await page.locator('.m-plant .reactor-component').evaluate(n=>{n.dataset.heating='true';n.dataset.cooling='true';});
 await page.locator('[data-pj=create]').click();await expect(page.locator('.pj-drawing .stack-component')).toHaveAttribute('data-fault','false');await expect(page.locator('.pj-drawing .reactor-component')).toHaveAttribute('data-heating','false');await expect(page.locator('.pj-drawing .reactor-component')).toHaveAttribute('data-cooling','false');await expect(page.locator('.m-plant .stack-component')).toHaveAttribute('data-fault','true');
});
