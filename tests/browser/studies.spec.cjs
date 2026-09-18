const {revealTool}=require('./navigation.cjs');
const {test,expect}=require('@playwright/test');
async function open(page){await page.goto('/');await page.locator('.m-plant').waitFor();await page.getByRole('button',{name:'Simulation menu',exact:true}).click();await revealTool(page,'[data-do=studies]');await page.locator('[data-do=studies]').click();await expect(page.locator('.st-article h1')).toContainText('tomorrow');}

test('study write-up traces a metric and returns to its originating hour and focus',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('/');await page.locator('.m-plant').waitFor();await page.getByRole('button',{name:'Step forward',exact:true}).click();await page.getByRole('button',{name:'Simulation menu',exact:true}).click();await revealTool(page,'[data-do=studies]');await page.locator('[data-do=studies]').click();await expect(page.locator('.st-article h1')).toContainText('tomorrow');
 await page.locator('.st-article button[data-case]').first().click();await page.locator('[data-trace=methane_kg]').first().click();await expect(page.locator('.st-panel-body')).toContainText('Terminal battery credit is excluded');await expect(page.locator('.st-panel-body')).toContainText('original_decision_cost_version');
 await page.keyboard.press('Escape');await page.keyboard.press('Escape');await expect(page.locator('.st-workspace')).toBeHidden();await expect(page.locator('[data-m=scrubber]')).toHaveValue('1');await expect(page.locator('[data-do=studies]')).toBeFocused();expect(errors).toEqual([]);
});

test('study resolves parameter variants and rejects late selection responses',async({page})=>{
 await open(page);await page.locator('[data-st=repeat]').click();await expect(page.locator('[data-st=start]')).toBeEnabled();await expect(page.locator('[data-st=basis]')).toHaveValue('current-plant');await expect(page.locator('.st-preview')).toContainText('400.0');await expect(page.locator('.st-preview')).toContainText('1,600.0');
 let delayed=false;await page.route('**/dispatch/studies',async route=>{const body=route.request().postDataJSON();const response=await route.fetch();if(body.operation==='preview'&&body.tier==='smoke'&&!delayed){delayed=true;await new Promise(r=>setTimeout(r,500));}await route.fulfill({response});});
 await page.locator('[data-st=tier]').selectOption('smoke');await page.locator('[data-st=tier]').selectOption('reference');await expect(page.locator('[data-st=start]')).toBeEnabled();await page.waitForTimeout(600);await expect(page.locator('.st-preview')).toContainText('4 paired cases');await expect(page.locator('.st-preview')).toContainText('6 hours');
});

test('recorded study case opens the requested controller and returns to the same report',async({page})=>{
 await open(page);await page.locator('.st-article button[data-case]').first().click();const button=page.locator('[data-replay]').last();const controller=await button.getAttribute('data-controller');const hour=Number(await button.getAttribute('data-hour'));await button.click();await expect(page.locator('.st-workspace')).toBeHidden();await expect(page.locator('[data-m=controller]')).toHaveValue(controller);await expect(page.locator('[data-m=scrubber]')).toHaveValue(String(hour+1));await page.getByRole('button',{name:'Simulation menu',exact:true}).click();await page.locator('[data-do=study-origin]').click();await expect(page.locator('.st-article h1')).toContainText('tomorrow');
});

test('Model links to Studies and returns to the essay without changing its controls',async({page})=>{
 await page.goto('/');await page.locator('.m-plant').waitFor();await page.getByRole('button',{name:'Simulation menu',exact:true}).click();await revealTool(page,'.m-utility [data-model-topic=battery]');await page.locator('.m-utility [data-model-topic=battery]').click();await expect(page.locator('.d-workspace')).toHaveAttribute('data-pending','false');await page.locator('[data-d=studies]').click();await expect(page.locator('.st-workspace')).toBeVisible();await expect(page.locator('.st-article h1')).toContainText('tomorrow');await page.locator('[data-st=back]').click();await expect(page.locator('.d-workspace')).toBeVisible();await expect(page.locator('[data-d=studies]')).toBeFocused();
});

test('study index, configuration and keyboard charts remain usable on a narrow screen',async({page})=>{
 await page.setViewportSize({width:390,height:844});await open(page);expect(await page.locator('.st-workspace').evaluate(n=>n.scrollWidth<=n.clientWidth+1)).toBeTruthy();await page.locator('[data-st=index]').click();await page.locator('[data-st=search]').fill('does-not-exist');await expect(page.locator('.st-editions')).toContainText('No matching');await page.keyboard.press('Escape');await page.locator('[data-st=configuration]').click();await expect(page.locator('.st-panel-body')).toContainText('Starting energy / kWh');expect(await page.locator('.st-workspace').evaluate(n=>n.scrollWidth<=n.clientWidth+1)).toBeTruthy();await page.keyboard.press('Escape');await page.locator('circle[data-case]').first().focus();await page.keyboard.press('Enter');await expect(page.locator('.st-panel')).toBeVisible();
});

test('study worker can cancel, resume, publish and download its preserved evidence',async({page})=>{
 test.setTimeout(120000);await open(page);await page.locator('[data-st=fresh]').click();await expect(page.locator('[data-st=cancel]')).toBeVisible();await page.locator('[data-st=cancel]').click();await expect(page.locator('[data-st=cancel]')).toBeHidden({timeout:60000});await page.locator('[data-st=resume]').click();await expect(page.locator('.st-status')).toHaveText('Study write-up saved',{timeout:60000});await expect(page.locator('[data-st=cancel]')).toBeHidden();await page.locator('[data-st=history]').click();await expect(page.locator('[data-publication]').first()).toBeVisible();await page.locator('[data-publication]').last().click();await expect(page.locator('.st-article h1')).toContainText('tomorrow');await page.locator('[data-st=export]').click();await expect(page.locator('.st-download a')).toBeVisible({timeout:60000});await expect(page.locator('.st-download a')).toHaveAttribute('href',/report_id=[a-f0-9]{32}/);const downloaded=page.waitForEvent('download');await page.locator('.st-download a').click();expect(await (await downloaded).failure()).toBeNull();
});

test('study workspace has a reviewed visual reference',async({page})=>{
 test.skip(process.platform!=='darwin','Reviewed on the macOS reference machine.');await open(page);await expect(page.locator('.st-workspace')).toHaveScreenshot('study-workspace.png',{animations:'disabled',mask:[page.locator('.st-meta'),page.locator('.st-progress')],maxDiffPixelRatio:.001});
});
