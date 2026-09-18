const {revealTool}=require('./navigation.cjs');
const {test,expect}=require('@playwright/test');

test('shared visit planning is opt-in, keyboard selectable and retreats from the simulation',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');await page.locator('.m-plant').waitFor();
  await page.locator('[data-do="menu"]').click();
  await revealTool(page,'[data-do="setup"]');await page.locator('[data-do="setup"]').first().click();
  await page.getByText('Field operations / robots, recovery and human service',{exact:true}).click();
  const enabled=page.getByRole('checkbox',{name:'Coordinate service work with MPC (experimental)',exact:true});
  const choices=page.getByRole('combobox',{name:'Service scheduling alternatives',exact:true});
  await expect(enabled).not.toBeChecked();await expect(choices).toBeHidden();
  await enabled.focus();await page.keyboard.press('Space');
  await expect(choices).toHaveValue('Individual jobs (version 1)');
  await choices.focus();await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');
  await expect(choices).toHaveValue('Individual and shared crew visits (version 2)');
  await expect(page.getByText(/an interrupted visit can prevent later jobs/)).toBeVisible();
  await page.setViewportSize({width:390,height:844});
  await choices.scrollIntoViewIfNeeded();await expect(choices).toBeVisible();
  await enabled.uncheck();await expect(choices).toBeHidden();
  await enabled.check();await expect(choices).toHaveValue('Individual and shared crew visits (version 2)');
  await page.getByRole('button',{name:'← Simulation',exact:true}).click();
  await expect(page.locator('.m-plant')).toBeVisible();await expect(enabled).toBeHidden();
  expect(await page.locator('.methane-console button:visible').count()).toBe(5);
  expect(errors).toEqual([]);
});
