const {revealTool}=require('./navigation.cjs');
const {test,expect}=require('@playwright/test');
test.beforeEach(async()=>{test.skip(!process.env.DISPATCH_FIELD_STUDIES,'Requires an executed multi-arm study fixture.');});
async function open(page){await page.goto('/');await page.locator('.m-plant').waitFor();await page.getByRole('button',{name:'Simulation menu',exact:true}).click();await revealTool(page,'[data-do=studies]');await page.locator('[data-do=studies]').click();await expect(page.locator('.st-article h1')).toContainText('restore production');}
test('field write-up retains separate packages, service accounting and original calculation identities',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await open(page);
 await expect(page.locator('.st-article')).toContainText('4/4 complete cases');await expect(page.locator('.st-article')).toContainText('Rover-assisted service');await expect(page.locator('.st-article')).toContainText('Δ crew');
 await page.locator('button[data-case]').filter({hasText:'Arm'}).last().click();await expect(page.locator('.st-panel-body')).toContainText('Modelled service expenditure');
 await page.locator('[data-trace=service_allocated_eur]').click();await expect(page.locator('.st-panel-body')).toContainText('Calculation operands and sources');await expect(page.locator('.st-panel-body')).toContainText('original_service_cost_version');await expect(page.locator('.st-panel-body')).toContainText('price_path');
 await page.keyboard.press('Escape');await page.locator('button[data-case]').filter({hasText:'Arm'}).last().click();await page.locator('[data-trace=crew_hours]').click();await expect(page.locator('.st-panel-body')).toContainText('committed labour');
 await page.keyboard.press('Escape');await page.locator('button[data-case]').filter({hasText:'Arm'}).last().click();await page.getByRole('button',{name:'Inspect full service record',exact:true}).click();await expect(page.locator('.st-panel-body')).toContainText('executive');await page.getByRole('button',{name:'Return to this case',exact:true}).click();await expect(page.locator('[data-trace=crew_hours]')).toBeVisible();expect(errors).toEqual([]);
});
test('new study chooses a protocol without inheriting the previous edition and rejects late previews',async({page})=>{
 await open(page);await page.locator('[data-st=new]').click();await expect(page.locator('[data-st=start]')).toBeEnabled();await expect(page.locator('.st-preview')).toContainText('4 separate cases');
 let delayed=false;await page.route('**/dispatch/studies',async route=>{const b=route.request().postDataJSON(),response=await route.fetch();if(b.operation==='preview'&&b.protocol_id==='battery-reserves'&&!delayed){delayed=true;await new Promise(r=>setTimeout(r,500));}await route.fulfill({response});});
 await page.locator('[data-st=protocol-choice]').selectOption('battery-reserves');await page.locator('[data-st=protocol-choice]').selectOption('field-recovery');await expect(page.locator('[data-st=start]')).toBeEnabled();await page.waitForTimeout(600);await expect(page.locator('.st-preview')).toContainText('4 separate cases');await expect(page.locator('.st-preview')).toContainText('3 matched comparisons');
});
test('field editions cancel, resume, retain publications and return from playback',async({page})=>{
 test.setTimeout(120000);await open(page);await page.locator('[data-st=new]').click();await expect(page.locator('[data-st=start]')).toBeEnabled();await page.locator('[data-st=tier]').selectOption('smoke');await expect(page.locator('[data-st=start]')).toBeEnabled();await page.locator('[data-st=start]').click();await expect(page.locator('[data-st=cancel]')).toBeVisible();await page.locator('[data-st=cancel]').click();await expect(page.locator('[data-st=cancel]')).toBeHidden({timeout:60000});await page.locator('[data-st=resume]').click();await expect(page.locator('.st-status')).toHaveText('Study write-up saved',{timeout:60000});await expect(page.locator('.st-article')).toContainText('4/4 complete cases');
 await page.locator('[data-st=history]').click();await expect(page.locator('[data-publication]').first()).toBeVisible();await page.locator('[data-publication]').last().click();await expect(page.locator('.st-article')).toContainText('0/4 complete cases');await page.locator('button[data-case]').first().click();await expect(page.locator('[data-replay]')).toHaveCount(0);await page.keyboard.press('Escape');await page.locator('[data-st=history]').click();await page.locator('[data-publication]').first().click();await expect(page.locator('.st-article')).toContainText('4/4 complete cases');
 await page.locator('button[data-case]').first().click();const opening=performance.now();await page.locator('[data-replay]').click();await expect(page.locator('.st-status')).toHaveText('Opening recorded playback…');
 // Archive verification, export preparation and Gradio updates are a bounded import,
 // not the 200 ms simple-calculation gate. Retain latency separately from correctness.
 await expect(page.locator('.st-workspace')).toBeHidden({timeout:15000});
 const fs=require('node:fs');fs.mkdirSync('build/services/field-studies',{recursive:true});fs.writeFileSync('build/services/field-studies/replay-latency.json',JSON.stringify({observed_ms:performance.now()-opening,functional_timeout_ms:15000,sample_count:1,scope:'Single recorded archive import, including server verification and UI update; not a latency distribution or a passing instantaneous-UX claim.'},null,2));
 await expect(page.locator('[data-m=controller]')).toHaveValue('Greedy');await page.getByRole('button',{name:'Simulation menu',exact:true}).click();await page.locator('[data-do=study-origin]').click();await expect(page.locator('.st-article h1')).toContainText('restore production');
});
test('matched configurations remain accessible on narrow screens with a reviewed write-up',async({page})=>{
 await open(page);await page.locator('.st-workspace').screenshot({path:'build/services/field-studies/write-up.png'});await page.setViewportSize({width:390,height:844});await page.locator('[data-st=configuration]').click();await expect(page.locator('.st-panel-body')).toContainText('Every change from the selected basis');expect(await page.locator('.st-workspace').evaluate(n=>n.scrollWidth<=n.clientWidth+1)).toBeTruthy();await page.keyboard.press('Escape');await page.locator('.st-workspace').screenshot({path:'build/services/field-studies/write-up-narrow.png'});await page.keyboard.press('Escape');await expect(page.locator('.st-workspace')).toBeHidden();await expect(page.locator('[data-do=studies]')).toBeFocused();
});

test('loading another publication removes the previous report actions until the selected response arrives',async({page})=>{
 await open(page);await expect(page.locator('.st-status')).not.toContainText('Opening');
 await page.locator('[data-st=history]').click();
 let release,announced;const pending=new Promise(resolve=>release=resolve),started=new Promise(resolve=>announced=resolve);
 await page.route('**/dispatch/studies',async route=>{if(route.request().postDataJSON().operation==='view'){announced();await pending;}await route.continue();});
 await page.locator('[data-publication]').first().click();await started;
 await expect(page.locator('.st-article')).toBeHidden();await expect(page.locator('.st-panel')).toBeHidden();await expect(page.locator('.st-status')).toContainText('Opening');await expect(page.locator('[data-st=back]')).toBeFocused();
 release();await expect(page.locator('.st-article h1')).toContainText('restore production');await expect(page.locator('.st-status')).not.toContainText('Opening');await expect(page.locator('[data-st=back]')).toBeFocused();await page.keyboard.press('Escape');await expect(page.locator('.st-workspace')).toBeHidden();
});

test('service histories load on demand and late records cannot replace a different selection',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await open(page);
 await page.locator('button[data-case]').filter({hasText:'Arm'}).last().click();
 let release,announce,captured;const pending=new Promise(r=>release=r),started=new Promise(r=>announce=r);
 await page.route('**/dispatch/studies',async route=>{
  const body=route.request().postDataJSON();
  if(body.operation!=='service-record'){await route.continue();return;}
  captured=body;const response=await route.fetch();announce();await pending;await route.fulfill({response});
 });
 await page.getByRole('button',{name:'Inspect full service record',exact:true}).click();await started;
 expect(captured.report_id).toMatch(/^[a-f0-9]{32}$/);expect(captured.attempt_id).toBeTruthy();expect(captured.controller).toBe('Greedy');
 await expect(page.locator('.st-panel-body [role=status]')).toContainText('Loading this original service record');
 await page.getByRole('button',{name:'Return to this case',exact:true}).click();
 await expect(page.locator('[data-trace=crew_hours]')).toBeVisible();
 release();await page.waitForTimeout(250);
 await expect(page.locator('[data-trace=crew_hours]')).toBeVisible();
 await expect(page.locator('.st-panel-body')).not.toContainText('Original signed case-attempt service record');
 await page.unroute('**/dispatch/studies');
 await page.getByRole('button',{name:'Inspect full service record',exact:true}).click();
 await expect(page.locator('.st-panel-body')).toContainText('Original signed case-attempt service record');
 await expect(page.locator('.st-panel-body')).toContainText('executive');
 await page.keyboard.press('Escape');await page.keyboard.press('Escape');
 await expect(page.locator('[data-do=studies]')).toBeFocused();expect(errors).toEqual([]);
});

test('unavailable service history preserves navigation and never shows another record',async({page})=>{
 await open(page);await page.locator('button[data-case]').filter({hasText:'Arm'}).last().click();
 await page.route('**/dispatch/studies',async route=>{
  const body=route.request().postDataJSON();
  if(body.operation==='service-record')await route.fulfill({json:{key:body.key,error:'Selected original attempt is unavailable'}});
  else await route.continue();
 });
 await page.getByRole('button',{name:'Inspect full service record',exact:true}).click();
 await expect(page.locator('.st-panel-body [role=status]')).toHaveText('Selected original attempt is unavailable');
 await expect(page.locator('.st-panel-body pre')).toHaveCount(0);
 await page.getByRole('button',{name:'Return to this case',exact:true}).click();
 await expect(page.locator('[data-trace=crew_hours]')).toBeVisible();
});
