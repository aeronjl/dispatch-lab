const {revealTool}=require('./navigation.cjs');
const {test,expect}=require('@playwright/test');
test.beforeEach(async()=>{test.skip(!process.env.DISPATCH_SERVICE_COSTS,'Requires a recorded complete-service-accounting fixture.');});
async function ready(page){await page.goto('/');await page.locator('.m-plant').waitFor();await page.locator('[data-m="scrubber"]').evaluate(n=>{n.value=36;n.dispatchEvent(new Event('input',{bubbles:true}))});}
async function services(page){await page.locator('[data-do="menu"]').click();await page.locator('[data-panel="services"]').click();}
async function setup(page){await page.locator('[data-do="menu"]').click();await revealTool(page,'[data-do="setup"]');await page.locator('[data-do="setup"]').first().click();if(!await page.getByRole('checkbox',{name:'Use complete service accounting',exact:true}).isVisible())await page.getByText('Economic assumptions / component costs and decision value',{exact:true}).click();}
test('service cost views reveal original prices and return to the same service context',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await ready(page);await services(page);
 const costs=page.locator('[data-m="services"] .m-cost');await expect(costs).toContainText('Modelled expenditure');await expect(costs).toContainText('Crew hours');await expect(costs).toContainText('Remote hours');
 await costs.getByRole('button',{name:'Trace service costs',exact:true}).click();await expect(page.locator('.d-reference')).toContainText('report_service_price_version');await expect(page.locator('.d-reference')).toContainText('parts_consumed_eur');
 await page.keyboard.press('Escape');await expect(costs).toBeVisible();await expect(costs.getByRole('button',{name:'Trace service costs',exact:true})).toBeFocused();await expect(page.locator('[data-m="scrubber"]')).toHaveValue('36');
 await costs.screenshot({path:'build/services/economics-integration/inspector.png'});expect(errors).toEqual([]);
});
test('repricing keeps actions and original service identity; blank rates stay unpriced',async({page})=>{
 await ready(page);await setup(page);const editor=page.locator('.service-economic-assumptions').first();
 await expect(editor.getByRole('checkbox',{name:'Use complete service accounting',exact:true})).toBeChecked();
 const rate=editor.getByRole('spinbutton',{name:'rates / remote eur per hour',exact:true});await rate.fill('180');await page.getByRole('button',{name:'Reprice completed run',exact:true}).click();await expect(page.getByText('Cost report repriced.',{exact:false})).toBeVisible();
 await page.getByRole('button',{name:'← Simulation',exact:true}).click();await expect(page.locator('[data-m="scrubber"]')).toHaveValue('36');await services(page);
 await page.getByRole('button',{name:'Trace service costs',exact:true}).click();await expect(page.locator('.d-reference')).toContainText('180');await expect(page.locator('.d-reference')).toContainText('dispatch_service_price_version');await page.keyboard.press('Escape');await page.keyboard.press('Escape');
 await setup(page);await rate.fill('');await page.getByRole('button',{name:'Reprice completed run',exact:true}).click();await expect(page.getByText('Cost report repriced.',{exact:false})).toBeVisible();await page.getByRole('button',{name:'← Simulation',exact:true}).click();await services(page);await expect(page.locator('[data-m="services"] .m-cost')).toContainText('Unpriced');
});
test('price editor reveals one asset at a time and provision excludes duplicate ownership',async({page})=>{
 await ready(page);await setup(page);const editor=page.locator('.service-economic-assumptions').first();await editor.getByRole('tab',{name:'Cleaner',exact:true}).click();
 const provision=editor.getByRole('combobox',{name:'assets / cleaner / provision',exact:true});await provision.click();await page.getByRole('option',{name:'contracted',exact:true}).click();
 const capital=editor.getByRole('spinbutton',{name:'assets / cleaner / capital eur',exact:true});await expect(capital).toHaveValue('0');await expect(capital).toBeDisabled();
 await provision.click();await page.getByRole('option',{name:'owned',exact:true}).click();await expect(capital).toHaveValue('');await expect(capital).toBeEnabled();
 await page.setViewportSize({width:390,height:844});
 const toggle=editor.getByRole('checkbox',{name:'Use complete service accounting',exact:true});
 await toggle.uncheck();await expect(provision).toBeHidden();await toggle.check();
 await expect(provision).toBeVisible();
 await editor.getByRole('button',{name:'More tabs',exact:true}).click();await editor.getByRole('button',{name:'Rover',exact:true}).click();
 await expect(editor.getByRole('spinbutton',{name:'assets / rover / capital eur',exact:true})).toBeVisible();
 await editor.getByRole('button',{name:'More tabs',exact:true}).click();await editor.getByRole('button',{name:'Cleaner',exact:true}).click();await expect(provision).toBeVisible();
 await expect(capital).toHaveValue('');await expect(capital).toBeEnabled();
 await provision.evaluate(n=>n.scrollIntoView({block:'center'}));await page.screenshot({path:'build/services/economics-integration/editor-narrow.png'});
 await capital.fill('-1');await page.getByRole('button',{name:'Reprice completed run',exact:true}).click();await expect(page.getByText(/capital_eur.*non-negative|capital_eur.*negative/)).toBeVisible();
});
