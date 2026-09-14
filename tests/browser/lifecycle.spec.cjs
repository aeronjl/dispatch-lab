const {test,expect}=require('@playwright/test');
async function open(page){await page.goto('/');await page.locator('.m-plant').waitFor();await page.locator('[data-do=menu]').click();await page.locator('.m-utility [data-model-topic=battery]').click();await expect(page.locator('.d-result-status')).toContainText('Learning example',{timeout:20000});}
async function topic(page,key){await page.locator('[data-d=index]').click();await page.locator(`[data-topic=${key}]`).click();await expect(page.locator('.d-layout')).not.toHaveAttribute('inert','');}
async function change(page,key,value){await page.locator(`[data-input=${key}]`).evaluate((n,v)=>{n.value=String(v);n.dispatchEvent(new Event('input',{bubbles:true}));},value);}
test('all lifecycle essays calculate their controls and restore navigation',async({page})=>{
 test.setTimeout(180000);const errors=[];page.on('pageerror',e=>errors.push(e.message));await open(page);
 for(const key of ['deployment','condition','hardware','maintenance']){
  await topic(page,key);if(key==='maintenance')await page.locator('[data-d=calculate]').click();await expect(page.locator('.d-result-status')).toContainText('Learning example',{timeout:20000});
  const controls=await page.locator('[data-input]').evaluateAll(nodes=>nodes.map(n=>({key:n.dataset.input,value:n.value,next:n.tagName==='SELECT'?[...n.options].find(o=>o.value!==n.value).value:Number(n.value)<Number(n.max)?Number(n.value)+Number(n.step):Number(n.value)-Number(n.step)})));
  for(const c of controls){await change(page,c.key,c.next);if(key==='maintenance')await page.locator('[data-d=calculate]').click();await expect(page.locator('.d-workspace')).toHaveAttribute('data-pending','false',{timeout:20000});await expect(page.locator('.d-result-status')).toContainText('Learning example',{timeout:20000});await expect(page.locator('.lc-diagram')).toBeVisible();}
  await page.locator('[data-d=reset]').click();if(key==='maintenance')await page.locator('[data-d=calculate]').click();await expect(page.locator('.d-result-status')).toContainText('Learning example',{timeout:20000});
  for(const c of controls)await expect(page.locator(`[data-input=${c.key}]`)).toHaveValue(c.value);
 }
 await page.keyboard.press('Escape');await expect(page.locator('.d-workspace')).toBeHidden();expect(errors).toEqual([]);
});
test('restricted family remains unavailable with declared prerequisites and narrow-screen access',async({page})=>{
 await page.setViewportSize({width:390,height:844});await open(page);await topic(page,'hardware');await change(page,'family','manipulator');await expect(page.locator('.d-metrics')).toContainText('evidence restricted');await expect(page.locator('.lc-diagram')).toContainText('NO EXECUTABLE MECHANISM');expect(await page.locator('.d-workspace').evaluate(n=>n.scrollWidth<=n.clientWidth+1)).toBeTruthy();
});
test('maintenance worker reports cancellation and accepts a new comparison',async({page})=>{
 await open(page);await topic(page,'maintenance');await page.locator('[data-d=calculate]').click();await page.locator('[data-d=cancel]').click();await expect(page.locator('.d-result-status')).toContainText('cancelled');await change(page,'hours',24);await page.locator('[data-d=calculate]').click();await expect(page.locator('.d-result-status')).toContainText('Learning example',{timeout:20000});await expect(page.locator('.d-metrics')).toContainText('forecast-window');
});
test('Sites lifecycle controls preserve drafts and full-configuration edits',async({page})=>{
 await page.goto('/');await page.locator('.m-plant').waitFor();const original=await page.locator('.m-plant').innerHTML();await page.locator('[data-do=menu]').click();await page.locator('[data-do=sites]').click();await page.locator('.si-site-list button').filter({hasText:'London regional anchor'}).click();await page.locator('[data-si=design]').click();await expect(page.locator('.lc-design')).toBeHidden();await page.locator('[data-si=lifecycle-design]').click();await page.locator('[data-si=lifecycle-preset]').click();await expect(page.locator('.lc-validation')).toContainText('5 work packages');
 await page.locator('[data-lc=policy]').selectOption('none');await page.locator('[data-si=lifecycle-validate]').click();await expect(page.locator('.lc-validation')).toContainText('Validated draft');await page.locator('[data-si=advanced-design]').click();const editor=page.locator('[data-design=config]');const config=JSON.parse(await editor.inputValue());expect(config.lifecycle.maintenance_policy).toBe('none');config.lifecycle.crew_eur_per_hour=123;await editor.fill(JSON.stringify(config));await page.locator('[data-si=lifecycle-validate]').click();await expect(page.locator('.lc-validation')).toContainText('Validated draft');expect(JSON.parse(await editor.inputValue()).lifecycle.crew_eur_per_hour).toBe(123);
 await page.locator('[data-si=lifecycle-model]').click();await expect(page.locator('.d-essay h1')).toContainText('Capacity arrives');await page.keyboard.press('Escape');await expect(page.locator('.lc-design')).toBeVisible();await page.locator('[data-design=name]').fill('Lifecycle browser design');await page.locator('[data-si=save-design]').click();await expect(page.locator('.si-status')).toContainText('Design saved');await page.keyboard.press('Escape');expect(await page.locator('.m-plant').innerHTML()).toBe(original);
});
test('reviewed lifecycle essay screenshots',async({page})=>{
 await open(page);for(const key of ['deployment','condition','hardware','maintenance']){await topic(page,key);if(key==='maintenance')await page.locator('[data-d=calculate]').click();await expect(page.locator('.d-result-status')).toContainText('Learning example',{timeout:20000});await expect(page).toHaveScreenshot(`lifecycle-${key}.png`,{animations:'disabled',maxDiffPixelRatio:.001});}
});
