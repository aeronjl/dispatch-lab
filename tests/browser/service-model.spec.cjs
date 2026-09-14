const {test,expect}=require('@playwright/test');
const fs=require('node:fs');
async function enter(page,topic){
 await page.goto('/');await page.locator('.m-plant').waitFor();await page.evaluate(()=>document.fonts.ready);
 await page.getByRole('button',{name:'Simulation menu',exact:true}).click();await page.locator('.m-utility [data-model-topic=battery]').click();
 await expect(page.locator('.d-essay h1')).toBeVisible();await page.locator('[data-d=index]').click();await page.locator(`[data-topic=${topic}]`).click();
}
async function complete(page){await expect(page.locator('.d-result-status')).toContainText('Learning example',{timeout:45000});}
async function change(page,key,value){await page.locator(`[data-input=${key}]`).evaluate((n,v)=>{n.value=String(v);n.dispatchEvent(new Event('input',{bubbles:true}));},value);}
const examples={cleaning:['coverage',.8],inspection:['offset',5],recovery:['deadline',12],charging:['initial',2],logistics:['duration',3],service_costs:['crew_price',100],service_uncertainty:['duration',1.3]};
for(const [topic,[key,value]] of Object.entries(examples))test(`service essay ${topic} calculates, changes, resets and traces`,async({page})=>{
 test.setTimeout(120000);const errors=[];page.on('pageerror',e=>errors.push(e.message));await enter(page,topic);
 if(['charging','recovery'].includes(topic))await page.locator('[data-d=calculate]').click();await complete(page);
 await change(page,key,value);if(['charging','recovery'].includes(topic))await page.locator('[data-d=calculate]').click();await complete(page);
 await expect(page.locator(`[data-input=${key}]`).locator('..')).toHaveAttribute('data-changed','true');
 await expect(page.locator('.d-figure svg')).toHaveAttribute('aria-label',/calculated mechanism/);
 await page.locator('[data-ref=assumptions]').click();await expect(page.locator('.d-reference-body')).toContainText('Assumptions and sources');await page.keyboard.press('Escape');
 await page.locator('[data-d=reset]').click();if(['charging','recovery'].includes(topic))await page.locator('[data-d=calculate]').click();await complete(page);
 await page.locator('.d-workspace').evaluate(n=>n.scrollTop=0);fs.mkdirSync('build/release-1/screenshots',{recursive:true});await page.locator('.d-workspace').screenshot({path:`build/release-1/screenshots/${topic}.png`,animations:'disabled'});
 await page.locator('[data-d=context]').selectOption('This run');await expect(page.locator('.d-reference-body')).toContainText('Original recorded service work');
 await page.keyboard.press('Escape');await expect(page.locator('.d-workspace')).toBeHidden();expect(errors).toEqual([]);
});
test('service essays are accessible on narrow screens and reset supersedes late input',async({page})=>{
 await page.setViewportSize({width:390,height:844});await enter(page,'cleaning');await complete(page);
 await page.route('**/dispatch/learning-example',async route=>{const r=await route.fetch();await new Promise(r=>setTimeout(r,300));await route.fulfill({response:r});});
 await change(page,'coverage',.1);await page.waitForTimeout(100);await page.locator('[data-d=reset]').click();await complete(page);await page.waitForTimeout(350);
 await expect(page.locator('[data-input=coverage]')).toHaveValue('0.6');expect(await page.locator('.d-workspace').evaluate(n=>n.scrollWidth<=n.clientWidth+1)).toBeTruthy();
 await page.locator('.d-workspace').screenshot({path:'build/release-1/screenshots/cleaning-narrow.png',animations:'disabled'});
 await page.keyboard.press('Escape');await expect(page.locator('.m-utility [data-model-topic=battery]')).toBeFocused();
});
