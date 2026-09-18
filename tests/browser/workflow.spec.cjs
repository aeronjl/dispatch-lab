const {test,expect}=require('@playwright/test');
const fs=require('node:fs');
async function ready(page){await page.goto('/');await page.locator('.m-plant').waitFor();}
async function menu(page){await page.getByRole('button',{name:'Simulation menu',exact:true}).click();}
async function newProject(page){await ready(page);await menu(page);await page.locator('[data-do=project]').click();await page.locator('.pj-sites button').first().click();await page.locator('[data-pj=create]').click();await expect(page.locator('.pj-build')).toBeVisible();}
test('six tasks reveal expert tools without adding anything to the quiet plant',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await ready(page);
 await expect(page.locator('.m-utility')).toBeHidden();await menu(page);
 await expect(page.locator('.wf-journey button')).toHaveCount(6);
 await expect(page.locator('[data-do=setup]')).toBeHidden();await expect(page.locator('[data-do=studies]')).toBeHidden();
 await page.locator('[data-panel=tools]').click();await page.locator('[data-work-search]').fill('weather');
 await expect(page.locator('[data-do=sites]')).toBeVisible();await expect(page.locator('[data-do=setup]')).toBeHidden();
 await page.locator('[data-work-search]').fill('unfindable');await expect(page.locator('[data-work-empty]')).toBeVisible();
 await page.locator('[data-work-search]').fill('mechanics');await page.locator('.m-utility [data-model-topic=battery]').click();
 await expect(page.locator('.d-workspace')).toBeVisible();await page.keyboard.press('Escape');
 await expect(page.locator('.m-utility [data-model-topic=battery]')).toBeFocused();await expect(page.locator('[data-work-search]')).toHaveValue('mechanics');
 await page.locator('[data-panel=work]').click();fs.mkdirSync('build/ux',{recursive:true});await page.screenshot({path:'build/ux/work-desktop.png'});
 if(process.platform==='darwin')await expect(page).toHaveScreenshot('workflow-desktop.png',{animations:'disabled',maxDiffPixelRatio:.001});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'build/ux/work-mobile.png'});
 if(process.platform==='darwin')await expect(page).toHaveScreenshot('workflow-mobile.png',{animations:'disabled',maxDiffPixelRatio:.001});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);expect(errors).toEqual([]);
});
test('project operation choices survive stage changes, nested evidence and reload',async({page})=>{
 await newProject(page);await page.locator('.pj-header [data-pj=operate]').click();
 await page.locator('[data-pj-weather]').selectOption('synthetic');await page.locator('[data-pj-hours]').selectOption('24');await page.locator('[data-pj-controller]').selectOption('Greedy');await page.locator('[data-pj-start]').fill('2025-04-10');
 await expect(page.locator('[data-pj=expert-study]')).toBeHidden();
 await page.locator('.pj-header [data-pj=build]').click();await page.locator('.pj-drawing [data-pj-component=battery]').click();await page.locator('[data-pj=model]').click();
 await expect(page.getByRole('button',{name:'Back to project',exact:true})).toBeVisible();
 // Reproduce a parent's progress/render refresh while its child workspace is open.
 await page.locator('[data-pj=model]').evaluate(button=>button.replaceWith(button.cloneNode(true)));
 await page.keyboard.press('Escape');await expect(page.locator('[data-pj=model]')).toBeFocused();
 await page.locator('.pj-header [data-pj=operate]').click();await expect(page.locator('[data-pj-weather]')).toHaveValue('synthetic');await expect(page.locator('[data-pj-hours]')).toHaveValue('24');await expect(page.locator('[data-pj-controller]')).toHaveValue('Greedy');await expect(page.locator('[data-pj-start]')).toHaveValue('2025-04-10');
 await page.reload();await menu(page);await page.locator('[data-panel=operate]').click();await page.locator('[data-work=operate]').click();
 await expect(page.locator('[data-pj-start]')).toHaveValue('2025-04-10');await expect(page.locator('[data-pj-weather]')).toHaveValue('synthetic');
 await page.screenshot({path:'build/ux/operate-desktop.png'});
});
test('investigation and writing share one draft; returning restores the recording',async({page})=>{
 await ready(page);await page.locator('[data-do=next]').click();await menu(page);await page.locator('.wf-journey [data-do=investigate]').click();
 await expect(page.locator('.iv-totals')).toBeVisible();await expect(page.locator('.iv-intervals table')).toBeHidden();
 await page.locator('[data-iv=pin]').click();await page.locator('[data-iv-next=Notes]').click();await page.locator('[data-iv-field=finding]').fill('A saved interpretation.');await page.locator('[data-iv=save]').click();await expect(page.locator('.iv-status')).toContainText('Saved.');
 await page.locator('[data-iv-field=finding]').fill('A newer unsaved interpretation.');await expect(page.locator('[data-iv-dirty]')).toContainText('Newer edits not exported');
 await page.keyboard.press('Escape');await expect(page.locator('[data-m=scrubber]')).toHaveValue('1');await page.locator('[data-panel=write]').click();await page.locator('[data-work=notes]').click();
 await expect(page.locator('[data-iv-field=finding]')).toHaveValue('A newer unsaved interpretation.');await expect(page.locator('[data-iv=html]')).toBeEnabled();
 const download=page.waitForEvent('download');await page.locator('[data-iv=html]').click();const artifact=await download;await artifact.saveAs('build/ux/saved-writeup.html');const html=fs.readFileSync('build/ux/saved-writeup.html','utf8');expect(html).toContain('A saved interpretation.');expect(html).not.toContain('A newer unsaved interpretation.');
 await page.screenshot({path:'build/ux/write-desktop.png'});await page.keyboard.press('Escape');await expect(page.locator('[data-work=notes]')).toBeFocused();
});
test('comparison choices distinguish recorded outcomes from alternative predictions',async({page})=>{
 await ready(page);await menu(page);await page.locator('[data-panel=compare]').click();
 await expect(page.locator('[data-work=alternative]')).toContainText('Predictions');await expect(page.locator('[data-m=comparison]')).toBeHidden();
 await page.locator('.wf-disclosure summary').click();await expect(page.locator('[data-m=comparison]')).toContainText('Greedy');
 await page.locator('[data-work=designs]').click();await expect(page.locator('.si-page h1')).toHaveText('Compare sites and designs');await page.keyboard.press('Escape');await expect(page.locator('[data-work=designs]')).toBeFocused();
 await page.locator('[data-panel=work]').click();await page.locator('[data-panel=write]').click();await page.locator('[data-work=reports]').click();await expect(page.locator('.si-page h1')).toHaveText('Write up a study');
});
test('site → build → run → investigate → comparison → write-up uses the new recording',async({page})=>{
 test.setTimeout(120000);await newProject(page);await page.locator('.pj-header [data-pj=operate]').click();
 await page.locator('[data-pj-weather]').selectOption('synthetic');await page.locator('[data-pj-hours]').selectOption('24');await page.locator('[data-pj-controller]').selectOption('Greedy');await page.locator('[data-pj=run]').click();
 await expect(page.locator('[data-pj-destination=investigate]').first()).toBeVisible({timeout:60000});await page.locator('[data-pj-destination=investigate]').first().click();
 await expect(page.locator('.iv-totals')).toBeVisible({timeout:20000});await expect(page.locator('[data-iv-context]')).toContainText('Greedy');await expect(page.locator('.pj-workspace')).toBeHidden();
 await page.locator('[data-iv=pin]').click();await page.locator('[data-iv=alternative]').click();await expect(page.locator('[data-cv-controller], [data-cv=controller]')).toHaveValue('Greedy');
 await page.locator('[data-cv=alternative]').selectOption('battery');await page.locator('[data-cv=calculate]').click();await expect(page.locator('[data-cv=status]')).toContainText('Comparison complete',{timeout:20000});
 await page.keyboard.press('Escape');await expect(page.locator('.iv-comparison')).toContainText('saved predictions');await page.locator('[data-iv-tab=Notes]').click();await page.locator('[data-iv-field=question]').fill('Does conserving the first interval’s battery change predicted output?');
 await page.locator('[data-iv=save]').click();await expect(page.locator('.iv-status')).toContainText('Saved. Original run unchanged.');await page.keyboard.press('Escape');
 await menu(page);await page.locator('[data-do=study-origin]').click();await expect(page.locator('.si-page')).toContainText('24 / 24 hours');
 const studyId=await page.locator('[data-si=publish-study]').getAttribute('data-id');
 await page.locator('[data-si=publish-study]').click();await expect(page.locator('.si-page h1')).toHaveText('Edit write-up');
 await page.locator('[data-writeup=findings]').fill('Observed in the bounded browser rehearsal.');
 await page.locator('.si-header [data-si=reports]').click();await page.locator(`[data-si=publish-study][data-id="${studyId}"]`).click();
 await expect(page.locator('[data-writeup=findings]')).toHaveValue('Observed in the bounded browser rehearsal.');
 await page.locator('[data-si=report-publish]').click();await expect(page.locator('.si-page')).toContainText('Write-up frozen as edition');
 const link=page.getByRole('link',{name:'Open self-contained report'});const response=await page.request.get(await link.getAttribute('href'));expect(await response.text()).toContain('Observed in the bounded browser rehearsal.');
});
test('a delayed saved-edition restore cannot replace a newly saved write-up',async({page})=>{
 await ready(page);await menu(page);await page.locator('.wf-journey [data-do=investigate]').click();await expect(page.locator('.iv-totals')).toBeVisible();
 await page.locator('[data-iv-tab=Notes]').click();await page.locator('[data-iv-field=finding]').fill('First edition.');await page.locator('[data-iv=save]').click();await expect(page.locator('.iv-status')).toContainText('Saved.');await page.keyboard.press('Escape');
 let release;const hold=new Promise(resolve=>release=resolve);let waiting;const started=new Promise(resolve=>waiting=resolve);
 await page.route('**/dispatch/investigation',async route=>{const body=route.request().postDataJSON();if(body.operation==='load'&&body.key.includes('restore-saved')){const response=await route.fetch();waiting();await hold;await route.fulfill({response});}else await route.continue();});
 await page.locator('[data-panel=write]').click();await page.locator('[data-work=notes]').click();await started;
 await page.locator('[data-iv-field=finding]').fill('New saved edition.');await page.locator('[data-iv=save]').click();await expect(page.locator('.iv-status')).toContainText('Saved.');const edition=await page.locator('[data-iv-dirty]').textContent();release();await page.waitForTimeout(200);await expect(page.locator('[data-iv-dirty]')).toHaveText(edition);
 const download=page.waitForEvent('download');await page.locator('[data-iv=html]').click();const artifact=await download;await artifact.saveAs('build/ux/latest-writeup.html');expect(fs.readFileSync('build/ux/latest-writeup.html','utf8')).toContain('New saved edition.');
});
test('offline navigation explains which tasks require the restored application',async({page})=>{
 test.skip(!process.env.DISPATCH_OFFLINE_PLAYER,'Requires a current extracted bundle');await page.context().setOffline(true);await page.goto('file://'+process.env.DISPATCH_OFFLINE_PLAYER);await page.locator('.m-plant').waitFor();await menu(page);
 await expect(page.locator('.wf-offline')).toBeVisible();await expect(page.locator('[data-work=build]')).toBeDisabled();await page.locator('[data-panel=tools]').click();await expect(page.locator('[data-do=setup]')).toBeHidden();await expect(page.locator('.m-utility [data-model-topic=battery]')).toBeVisible();
 await page.locator('[data-panel=work]').click();await page.locator('[data-panel=operate]').click();await page.locator('[data-work=watch]').click();await page.locator('[data-do=next]').click();await expect(page.locator('[data-m=scrubber]')).toHaveValue('1');
});
