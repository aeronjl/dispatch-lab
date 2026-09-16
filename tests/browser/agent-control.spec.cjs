const {test,expect}=require('@playwright/test');
const fs=require('node:fs');
const execFile=require('node:util').promisify(require('node:child_process').execFile);
async function open(page){await page.goto('/');await page.locator('.m-plant').waitFor();await page.getByRole('button',{name:'Simulation menu',exact:true}).click();await page.locator('[data-do=agent-control]').click();await expect(page.locator('.ac-workspace')).toBeVisible();}
async function start(page,hours=2){await open(page);await page.locator('[data-ac=controller]').selectOption('Greedy');await page.locator('[data-ac=hours]').fill(String(hours));await page.locator('[data-ac=create]').click();await expect(page.locator('[data-ac-state]')).toContainText('waiting',{timeout:30000});}
test('operator preview, agent delivery, revoke, immutable recording and return',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await start(page);
 await page.locator('[data-ac=preview]').click();await expect(page.locator('.ac-prediction')).toContainText('Prediction only');
 await expect(page.locator('[data-ac-state]')).toContainText('0 / 2 h');
 await page.locator('[data-ac=reason]').fill('Reserve energy while the reactor warms');await page.locator('[data-ac=advance]').click();
 await expect(page.locator('[data-ac-state]')).toContainText('1 / 2 h');await expect(page.locator('[data-ac-state]')).toContainText('waiting');
 await page.locator('[data-ac-tab=Connection]').click();await page.locator('[data-ac=permission]').selectOption('advance');await page.locator('[data-ac=grant]').click();await expect(page.locator('[data-ac-config]')).toContainText('DISPATCH_AGENT_TOKEN');
 const config=JSON.parse(await page.locator('[data-ac-config]').textContent()).mcpServers['dispatch-lab'];
 const context={session_id:config.env.DISPATCH_CONTROL_SESSION,credential:config.env.DISPATCH_AGENT_TOKEN};
 const response=await execFile('.venv/bin/python',['tests/mcp_client.py'],{env:{...process.env,...config.env}});const witness=JSON.parse(response.stdout);expect(witness.observed_hour).toBe(1);expect(witness.accepted.status).toBe('accepted');
 await expect(page.locator('[data-ac-state]')).toContainText('complete');await page.locator('[data-ac=revoke]').click();
 expect((await page.request.post('/dispatch/agent-control',{data:{...context,operation:'observe'}})).status()).toBe(403);
 await page.locator('[data-ac-tab=Trace]').click();await expect(page.locator('.ac-trace')).toContainText('H1 · agent');await expect(page.locator('.ac-trace')).toContainText('balance checks passed');expect(await page.locator('.ac-trace script').count()).toBe(0);
 fs.mkdirSync('build/agent-control',{recursive:true});await page.screenshot({path:'build/agent-control/desktop.png'});
 await page.locator('[data-ac=close]').click();await expect(page.locator('[data-do=agent-control]')).toBeFocused();await expect(page.locator('.m-plant')).toBeVisible();
 await page.locator('[data-do=agent-control]').click();await expect(page.locator('[data-ac-state]')).toContainText('complete');await page.locator('[data-ac=recording]').click();
 await expect(page.locator('.ac-workspace')).toBeHidden();await expect(page.locator('[data-m=scrubber]')).toHaveAttribute('max','2',{timeout:30000});
 await page.getByRole('button',{name:'Step forward',exact:true}).click();await page.getByRole('button',{name:'Simulation menu',exact:true}).click();await page.locator('[data-do=control]').click();await page.locator('[data-cv-tab=Evidence]').click();await expect(page.locator('.cv-evidence')).toContainText('External control · operator');
 expect(errors).toEqual([]);
});
test('explicit requests invalidate previews; pause, stop and narrow keyboard access',async({page})=>{
 await page.setViewportSize({width:390,height:844});await start(page,3);
 await page.locator('[data-ac=mode]').selectOption('manual');await page.locator('[data-ac-action=heater_kw]').fill('999');await page.locator('[data-ac=preview]').click();await expect(page.locator('.ac-status')).toContainText('equipment limit');
 await page.locator('[data-ac-action=heater_kw]').fill('0');await page.locator('[data-ac=preview]').click();await expect(page.locator('.ac-prediction')).toContainText('Prediction only');await page.locator('[data-ac-action=heater_kw]').fill('1');await expect(page.locator('[data-ac=advance]')).toBeDisabled();
 await page.locator('[data-ac=pause]').click();await expect(page.locator('.ac-authority')).toContainText('Paused');await expect(page.locator('[data-ac=preview]')).toBeDisabled();await page.locator('[data-ac=pause]').click();await expect(page.locator('[data-ac=preview]')).toBeEnabled();
 await page.locator('[data-ac=stop]').click();await expect(page.locator('[data-ac=new]')).toBeVisible();
 expect(await page.locator('.ac-workspace').evaluate(el=>el.scrollWidth<=el.clientWidth)).toBeTruthy();fs.mkdirSync('build/agent-control',{recursive:true});await page.screenshot({path:'build/agent-control/mobile.png'});
 await page.keyboard.press('Escape');await expect(page.locator('.ac-workspace')).toBeHidden();await expect(page.locator('[data-do=agent-control]')).toBeFocused();
});
