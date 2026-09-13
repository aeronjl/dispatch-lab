const {test,expect}=require('@playwright/test');
const fs=require('node:fs');
const path=require('node:path');
async function ready(page){
  await page.goto('/');
  await expect(page.locator('.methane-console')).toBeVisible();
  await page.locator('[data-do="menu"]').click();
}
test('site services are revealed, keyboard accessible and preserve the playhead',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));await ready(page);
  await page.locator('[data-panel="services"]').click();
  await expect(page.locator('[data-m="services"]')).toBeVisible();
  await expect(page.locator('[data-m="services"]')).toContainText(/Site services/);
  const hour=await page.locator('[data-m="scrubber"]').inputValue();
  await page.keyboard.press('Escape');await expect(page.locator('.m-utility')).toBeHidden();
  await expect(page.locator('[data-do="menu"]')).toBeFocused();
  await expect(page.locator('[data-m="scrubber"]')).toHaveValue(hour);
  expect(errors).toEqual([]);
});
test('matched field presets keep environment enabled and select intervention capability',async({page})=>{
  await ready(page);await page.locator('[data-do="setup"]').first().click();
  await page.getByLabel('Start from a scenario').click();
  await page.getByRole('option',{name:'Field services / human only',exact:true}).click();
  await page.getByText('Field operations / robots, recovery and human service',{exact:true}).click();
  const panel=page.locator('#setup-screen');
  await expect(panel.getByLabel('rover enabled',{exact:true})).not.toBeChecked();
  await expect(panel.getByLabel('human fallback',{exact:true})).toBeChecked();
  await page.getByLabel('Start from a scenario').click();
  await page.getByRole('option',{name:'Field services / no intervention',exact:true}).click();
  await expect(panel.getByLabel('human fallback',{exact:true})).not.toBeChecked();
  await expect(panel.getByLabel('cleaner enabled',{exact:true})).not.toBeChecked();
  // Field layer and diagnosis both have an enabled checkbox; field layer is in this group.
  await expect(panel.getByLabel('enabled',{exact:true}).last()).toBeChecked();
});
test('saved field playback shows executed work, costs and calculation offline',async({page})=>{
  const artifact=path.resolve('build/field-operations/playback.html');
  test.skip(!fs.existsSync(artifact),'Generate the field validation fixture first');
  const errors=[], network=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{if(/^https?:/.test(route.request().url())){network.push(route.request().url());route.abort();}else route.continue();});
  await page.goto('file://'+artifact);
  await expect(page.locator('.methane-console')).toBeVisible();
  await page.locator('[data-do="timeline"]').click();
  await page.locator('[data-m="scrubber"]').evaluate(n=>{n.value=32;n.dispatchEvent(new Event('input',{bubbles:true}));});
  await page.locator('[data-do="menu"]').click();await page.locator('[data-panel="services"]').click();
  const pane=page.locator('[data-m="services"]');
  await expect(pane).toContainText('Work orders');await expect(pane).toContainText('human-service');
  await expect(pane).toContainText('Service costs');
  await pane.locator('summary').click();await expect(pane.locator('details')).toHaveAttribute('open','');
  await expect(pane.locator('pre')).toContainText('field_energy_balance');
  await pane.locator('summary').click();
  await page.screenshot({path:'build/field-operations/services-desktop.png'});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:'build/field-operations/services-mobile.png'});
  const sizes=await page.locator('.m-utility').evaluate(n=>[n.scrollWidth,n.clientWidth]);expect(sizes[0]).toBeLessThanOrEqual(sizes[1]);
  await page.keyboard.press('Escape');await expect(page.locator('[data-m="scrubber"]')).toHaveValue('32');
  expect(network).toEqual([]);expect(errors).toEqual([]);
});
