const {test,expect}=require('@playwright/test');

async function setup(page){
  await page.goto('/');await page.locator('.m-plant').waitFor();
  await page.locator('[data-do="menu"]').click();
  await page.locator('[data-do="setup"]').first().click();
  await page.getByText('Autonomy stress / injected faults and diagnostic assumptions',{exact:true}).click();
}

test('scheduled tests are opt-in and reveal their assumptions only in setup',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await setup(page);
  const enabled=page.getByRole('checkbox',{name:'Schedule recovery tests (experimental)',exact:true});
  const reserve=page.getByRole('spinbutton',{name:'Ending battery reserve / fraction',exact:true});
  await expect(enabled).not.toBeChecked();await expect(reserve).toBeHidden();
  await enabled.focus();await page.keyboard.press('Space');
  await expect(reserve).toBeVisible();await expect(reserve).toHaveValue('0.1');
  const coordination=page.getByRole('combobox',{name:'Recovery test coordination',exact:true});
  await expect(coordination).toHaveValue('After service selection (version 1)');
  await coordination.focus();await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');
  await expect(coordination).toHaveValue('Joint work, charging and tests for MPC (version 2)');
  await expect(page.getByText(/Greedy keeps the independent test scheduler and local service rule/)).toBeVisible();
  await expect(page.getByText(/Greedy uses an MPC subplanner during test episodes/)).toBeVisible();
  await reserve.fill('0.2');
  await page.setViewportSize({width:390,height:844});
  await expect(reserve).toBeVisible();await reserve.scrollIntoViewIfNeeded();
  await expect(reserve).toHaveValue('0.2');
  await enabled.uncheck();await expect(reserve).toBeHidden();
  await enabled.check();await expect(reserve).toHaveValue('0.2');
  await expect(coordination).toHaveValue('Joint work, charging and tests for MPC (version 2)');
  await page.getByRole('spinbutton',{name:'maximum wait hours',exact:true}).fill('1.5');
  await page.getByRole('button',{name:'RUN EXPERIMENT →',exact:true}).click();
  await expect(page.getByText(/INCOMPLETE \/ NOT RUN: maximum wait hours must be a whole number/)).toBeVisible();
  await expect(page.locator('#setup-screen')).toBeVisible();
  await page.getByRole('button',{name:'← Simulation',exact:true}).click();
  await expect(page.locator('.m-plant')).toBeVisible();
  await expect(enabled).toBeHidden();
  expect(await page.locator('.methane-console button:visible').count()).toBe(5);
  expect(errors).toEqual([]);
});
