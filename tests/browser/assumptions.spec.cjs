const {test,expect}=require('@playwright/test');
async function openReview(page){await page.goto('/');await page.locator('.m-plant .battery-component').click();await page.getByRole('button',{name:'Explore component',exact:true}).click();await page.locator('[data-x=context]').selectOption('Current catalogue');await expect(page.locator('.x-main h1')).toHaveText('Battery');await page.locator('[data-x-view=Assumptions]').click();}
test('parameter evidence reveals basis and uncertainty without changing playback',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await openReview(page);
 await expect(page.locator('.x-content')).toContainText('no matched plant');
 await page.locator('[data-x-group=battery]').click();await page.locator('[data-x-assumption="parameter:plant.roundtrip_efficiency"]').click();
 await expect(page.locator('.x-content')).toContainText('Unmeasured assumption');await expect(page.locator('.x-content')).toContainText('not a confidence interval');await expect(page.locator('.x-content')).toContainText('Not established');
 await page.screenshot({path:'research/model-assumptions/ui-parameter.png'});await page.keyboard.press('Escape');await expect(page.locator('.x-workspace')).toBeHidden();await expect(page.getByRole('button',{name:'Explore component',exact:true})).toBeFocused();expect(errors).toEqual([]);
});
test('assumption catalogue supports keyboard navigation and narrow screens',async({page})=>{
 await page.setViewportSize({width:390,height:844});await openReview(page);await page.locator('[data-x-group=battery]').focus();await page.keyboard.press('Enter');await page.locator('[data-x-assumption="parameter:plant.battery_c_rate"]').focus();await page.keyboard.press('Enter');
 await expect(page.locator('.x-content')).toContainText('Equipment performance assumption');expect(await page.locator('.x-workspace').evaluate(n=>n.scrollWidth<=n.clientWidth+1)).toBeTruthy();await page.screenshot({path:'research/model-assumptions/ui-mobile.png'});
});
test('current Model essay includes scoped parameter review',async({page})=>{
 await openReview(page);await page.locator('[data-x-view="Model & evidence"]').click();await page.locator('.x-content [data-model-topic=battery]').first().click();await expect(page.locator('.d-workspace')).toBeVisible();await page.locator('[data-ref=assumptions]').click();await expect(page.locator('.d-reference')).toContainText('Parameter evidence');await expect(page.locator('.d-reference')).toContainText('DC-to-DC');
});
test('review report reads offline on desktop and narrow screens',async({page})=>{
 await page.route('http://**/*',r=>r.abort());await page.route('https://**/*',r=>r.abort());await page.goto('file://'+require('path').resolve('research/model-assumptions/report.html'));
 await expect(page.locator('h1')).toContainText('credibly');await expect(page.locator('#experiments')).toContainText('The ranking reverses');await page.screenshot({path:'research/model-assumptions/report-desktop.png'});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'research/model-assumptions/report-mobile.png'});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
});
test('new offline archive retains its original review without network access',async({page})=>{
 const file=require('path').resolve('build/assumptions/offline/playback.html');test.skip(!require('fs').existsSync(file),'Requires the generated current review reproduction fixture.');
 await page.route('http://**/*',r=>r.abort());await page.route('https://**/*',r=>r.abort());await page.goto('file://'+file);await page.locator('.m-plant .battery-component').click();await page.getByRole('button',{name:'Explore component',exact:true}).click();await expect(page.locator('[data-x=context]')).toBeDisabled();await page.locator('[data-x-view=Assumptions]').click();await expect(page.locator('.x-content')).toContainText('Evidence gap');await page.locator('[data-x-group=battery]').click();await page.locator('[data-x-assumption="parameter:plant.roundtrip_efficiency"]').click();await expect(page.locator('.x-content')).toContainText('Not established');
});
