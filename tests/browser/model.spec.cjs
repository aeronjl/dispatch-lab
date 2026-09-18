const {revealTool}=require('./navigation.cjs');
const {test,expect}=require('@playwright/test');
const fs=require('node:fs');
async function open(page,topic='battery'){
 await page.goto('/');await page.locator('.m-plant').waitFor();await page.evaluate(()=>document.fonts.ready);
 await page.getByRole('button',{name:'Simulation menu',exact:true}).click();await revealTool(page,'.m-utility [data-model-topic=battery]');await page.locator('.m-utility [data-model-topic=battery]').click();
 await expect(page.locator('.d-essay h1')).toBeVisible();
 if(topic!=='battery'){await page.locator('[data-d=index]').click();await page.locator(`[data-topic=${topic}]`).click();}
 await expect(page.locator('.d-result-status')).not.toHaveText('');
}
async function complete(page){await expect(page.locator('.d-result-status')).toContainText('Learning example');}
async function change(page,key,value){await page.locator(`[data-input=${key}]`).evaluate((n,value)=>{n.value=String(value);n.dispatchEvent(new Event('input',{bubbles:true}));},value);}

test('model essay reconciles battery, resets, and returns to the same inspector',async({page})=>{
 await page.goto('/');await page.locator('[data-component=battery]').click();
 await page.getByRole('button',{name:'How it is modelled',exact:true}).click();await complete(page);
 await expect(page.locator('.d-metrics')).toContainText('294.868');await change(page,'efficiency',.81);await complete(page);
 await expect(page.locator('.d-metrics')).toContainText('290');await expect(page.locator('.d-reading-result')).toContainText('81.0');
 await page.locator('[data-d=reset]').click();await complete(page);await expect(page.locator('[data-input=efficiency]')).toHaveValue('0.9');
 await page.keyboard.press('Escape');await expect(page.locator('.d-workspace')).toBeHidden();await expect(page.locator('.m-inspector')).toBeVisible();
 await expect(page.getByRole('button',{name:'How it is modelled',exact:true})).toBeFocused();
});

test('all twelve model topics calculate and expose their assumptions and evidence',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await open(page);await complete(page);
 const changes={solar:['tilt',45],battery:['charge',110],electrolyser:['run_hours',2],hydrogen:['inflow',9],co2:['arrival',1],reactor:['ambient',15],bus:['pv',350],weather:['hour',12],diagnosis:['noise',.01],controllers:['horizon',6],economics:['price',2],experiments:['window',4]};
 for(const [topic,[key,val]] of Object.entries(changes)){
  await page.locator('[data-d=index]').click();await page.locator(`[data-topic=${topic}]`).click();await expect(page.locator(`[data-input=${key}]`)).toBeVisible();
  await change(page,key,val);if(['bus','controllers'].includes(topic))await page.locator('[data-d=calculate]').click();await complete(page);
  await expect(page.locator('.d-chart svg').first()).toBeVisible();await expect(page.locator('.d-reading-result')).not.toHaveText('');
  await page.locator('[data-ref=assumptions]').click();await expect(page.locator('.d-reference-body')).toContainText('Assumptions and sources');
  await page.locator('[data-d=close-reference]').click();await page.locator('[data-ref=evidence]').click();await expect(page.locator('.d-reference-body')).toContainText('Calibrated against an operating plant');await page.locator('[data-d=close-reference]').click();
 }
 expect(errors).toEqual([]);
});

test('model missing data and infeasible inputs retain labelled previous values',async({page})=>{
 await open(page);await complete(page);await change(page,'energy',800);await expect(page.locator('.d-result-status')).toContainText('Previous valid inputs');await expect(page.locator('.d-metrics')).toContainText('294.868');
 await page.locator('[data-d=index]').click();await page.locator('[data-topic=weather]').click();await complete(page);await change(page,'missing','yes');await expect(page.locator('.d-result-status')).toContainText('missing interval');
});

test('choosing a model topic keeps focus inside the workspace for immediate Escape',async({page})=>{
 await open(page);await complete(page);
 await page.locator('[data-d=index]').click();await page.locator('[data-topic=controllers]').click();
 await expect(page.locator('[data-d=back]')).toBeFocused();
 await page.keyboard.press('Escape');await expect(page.locator('.d-workspace')).toBeHidden();
 await expect(page.locator('.m-utility [data-model-topic=battery]')).toBeFocused();
});

test('model reading on narrow screens keeps example inline and controls accessible',async({page})=>{
 await page.setViewportSize({width:390,height:844});await open(page);await complete(page);
 await expect(page.locator('.d-essay .d-companion')).toHaveCount(1);await change(page,'efficiency',.8);await complete(page);await expect(page.locator('.d-metrics')).toContainText('80');
 expect(await page.locator('.d-workspace').evaluate(n=>n.scrollWidth<=n.clientWidth+1)).toBeTruthy();
 await page.locator('[data-d=index]').click();await page.locator('[data-d=search]').fill('forecast');await expect(page.locator('[data-d=topics] button')).toHaveCount(1);
 await page.keyboard.press('Escape');await page.keyboard.press('Escape');await expect(page.locator('.d-workspace')).toBeHidden();
});

test('model response generation rejects late calculations after reset and topic changes',async({page})=>{
 await open(page);await complete(page);let calls=0;
 await page.route('**/dispatch/learning-example',async route=>{const response=await route.fetch();if(++calls===1)await new Promise(r=>setTimeout(r,500));await route.fulfill({response});});
 await change(page,'charge',120);await page.waitForTimeout(100);await page.locator('[data-d=reset]').click();await complete(page);await page.waitForTimeout(600);await expect(page.locator('.d-metrics')).toContainText('294.868');await expect(page.locator('[data-input=charge]')).toHaveValue('100');
});

test('isolated model comparison cancels and can calculate again',async({page})=>{
 await open(page,'controllers');await page.locator('[data-d=calculate]').click();await page.locator('[data-d=cancel]').click();await expect(page.locator('.d-result-status')).toContainText('cancelled');
 await change(page,'horizon',6);await page.locator('[data-d=calculate]').click();await complete(page);await expect(page.locator('.d-step')).toContainText('solver');
});

test('model recorded trace distinguishes legacy explanation from current model',async({page})=>{
 await open(page);await complete(page);await page.locator('[data-d=context]').selectOption('This run');await expect(page.locator('.d-reference-body')).toContainText('Trace calculation');await expect(page.locator('.d-reference-body')).toContainText('Requested and applied');
 await page.locator('[data-d=context]').selectOption('Current model');await complete(page);await expect(page.locator('.d-essay h1')).toContainText('Keeping energy');
});

test('model simple examples meet the interaction budget',async({page})=>{
 await open(page);await complete(page);const samples=[];
 for(let i=0;i<24;i++){
  const started=Date.now();await change(page,'charge',100+i*5);await complete(page);samples.push(Date.now()-started);
 }
 const render=await page.evaluate(()=>performance.getEntriesByName('model-render').map(x=>x.duration));const p95=x=>[...x].sort((a,b)=>a-b)[Math.floor(x.length*.95)];
 fs.mkdirSync('build/model',{recursive:true});fs.writeFileSync('build/model/browser-performance.json',JSON.stringify({preview_p95_ms:p95(samples),render_p95_ms:p95(render),samples,render},null,2));
 expect(p95(render)).toBeLessThanOrEqual(10);if(process.env.DISPATCH_MODEL_PERFORMANCE_GATE)expect(p95(samples)).toBeLessThanOrEqual(200);
});

test('model essay artwork remains stable',async({page})=>{
 test.skip(process.platform!=='darwin','Visual reference reviewed on the macOS reference machine.');
 await open(page);await complete(page);await expect(page.locator('.d-workspace')).toHaveScreenshot('model-essay.png',{animations:'disabled',maxDiffPixelRatio:.001});
});

test('model learning stays responsive while a comparative batch runs',async({page})=>{
 test.skip(!process.env.DISPATCH_MODEL_BATCH,'Dedicated reference-machine workload.');
 await page.goto('/');await page.locator('.m-plant').waitFor();await page.getByRole('button',{name:'Simulation menu',exact:true}).click();await revealTool(page,'[data-do=analysis]');await page.locator('[data-do=analysis]').click();await page.getByRole('tab',{name:'Experiments',exact:true}).click();await page.getByRole('button',{name:'Run / resume suite',exact:true}).click();await page.waitForTimeout(700);
 await page.getByRole('button',{name:'← Simulation',exact:true}).click();await page.getByRole('button',{name:'Simulation menu',exact:true}).click();await revealTool(page,'.m-utility [data-model-topic=battery]');await page.locator('.m-utility [data-model-topic=battery]').click();await complete(page);
 const samples=[];
 for(let i=0;i<30;i++){
  const elapsed=await page.evaluate(i=>new Promise(resolve=>{const status=document.querySelector('.d-result-status');const started=performance.now();const observer=new MutationObserver(()=>{if(status.textContent.startsWith('Learning example')){observer.disconnect();resolve(performance.now()-started);}});observer.observe(status,{subtree:true,childList:true,characterData:true});const input=document.querySelector('[data-input=charge]');input.value=String(100+i*5);input.dispatchEvent(new Event('input',{bubbles:true}));}),i);samples.push(elapsed);
 }
 const render=await page.evaluate(()=>performance.getEntriesByName('model-render').map(x=>x.duration));const p95=x=>[...x].sort((a,b)=>a-b)[Math.floor(x.length*.95)];
 fs.writeFileSync('build/model/active-batch-performance.json',JSON.stringify({fixture_hours:Number(await page.locator('[data-m=scrubber]').getAttribute('max')),batch_requested:true,preview_p95_ms:p95(samples),render_p95_ms:p95(render),samples},null,2));
 await page.locator('[data-d=back]').click();await revealTool(page,'[data-do=analysis]');await page.locator('[data-do=analysis]').click();await page.getByRole('tab',{name:'Experiments',exact:true}).click();await page.getByRole('button',{name:'Cancel suite',exact:true}).click();await expect(page.getByText('Cancellation requested.',{exact:false})).toBeVisible();
 expect(p95(samples)).toBeLessThanOrEqual(200);expect(p95(render)).toBeLessThanOrEqual(10);
});

test('every essay control has a calculated or explicit invalid result and resets',async({page})=>{
 test.setTimeout(120000);await open(page);await complete(page);
 for(const topic of ['solar','battery','electrolyser','hydrogen','co2','reactor','bus','weather','diagnosis','controllers','economics','experiments']){
  await page.locator('[data-d=index]').click();await page.locator(`[data-topic=${topic}]`).click();await expect(page.locator('.d-layout')).not.toHaveAttribute('inert','');
  const controls=await page.locator('[data-input]').evaluateAll(nodes=>nodes.map(n=>({key:n.dataset.input,value:n.value,next:n.tagName==='SELECT'?[...n.options].find(o=>o.value!==n.value).value:Number(n.value)<Number(n.max)?Number(n.value)+Number(n.step):Number(n.value)-Number(n.step)})));
  for(const c of controls){
   const response=page.waitForResponse(r=>r.url().includes('/dispatch/learning-')&&r.request().method()==='POST');await change(page,c.key,c.next);if(['bus','controllers'].includes(topic))await page.locator('[data-d=calculate]').click();await response;
   await expect(page.locator('.d-workspace')).toHaveAttribute('data-pending','false');await expect(page.locator('.d-result-status')).not.toHaveText('');await expect(page.locator(`[data-input=${c.key}]`).locator('..')).toHaveAttribute('data-changed','true');
  }
  await page.locator('[data-d=reset]').click();if(['bus','controllers'].includes(topic))await page.locator('[data-d=calculate]').click();await complete(page);
  for(const c of controls)await expect(page.locator(`[data-input=${c.key}]`)).toHaveValue(c.value);
 }
});

test('keyboard learning preserves the originating hour and controller',async({page})=>{
 await page.goto('/');await page.locator('.m-plant').waitFor();await page.getByRole('button',{name:'Step forward',exact:true}).click();await page.getByRole('button',{name:'Step forward',exact:true}).click();const controller=await page.locator('[data-m=controller]').inputValue();await page.locator('[data-component=battery]').focus();await page.keyboard.press('Enter');await page.getByRole('button',{name:'How it is modelled',exact:true}).click();await complete(page);
 const response=page.waitForResponse('**/dispatch/learning-example');await page.locator('[data-input=charge]').focus();await page.keyboard.press('ArrowRight');await response;await complete(page);await expect(page.locator('[data-input=charge]')).toHaveValue('110');await page.keyboard.press('Escape');await expect(page.locator('[data-m=scrubber]')).toHaveValue('2');await expect(page.locator('[data-m=controller]')).toHaveValue(controller);await expect(page.getByRole('button',{name:'How it is modelled',exact:true})).toBeFocused();
});

test('new archive exposes original model assumptions and calculation identities',async({page})=>{
 test.skip(!process.env.DISPATCH_COMPONENT_TRACE,'Requires a new documentation snapshot.');
 await open(page);await complete(page);await page.locator('[data-d=context]').selectOption('This run');await expect(page.locator('.d-reference-body')).toContainText('Original assumptions');await expect(page.locator('.d-reference-body')).toContainText('Component model');await expect(page.locator('.d-reference-body')).toContainText('Evidence saved with this run');await expect(page.locator('.d-reference-body')).not.toContainText('no original documentation snapshot');
});

test('saved model report opens from portable playback with the network disabled',async({page})=>{
 test.skip(!process.env.DISPATCH_OFFLINE_PLAYER,'Requires a new extracted reproduction bundle.');
 const requests=[];page.on('request',r=>{if(/^https?:/.test(r.url()))requests.push(r.url());});await page.context().setOffline(true);await page.goto('file://'+process.env.DISPATCH_OFFLINE_PLAYER);await page.locator('.m-plant').waitFor();await page.getByRole('button',{name:'Simulation menu',exact:true}).click();await revealTool(page,'.m-utility [data-model-topic=battery]');await page.locator('.m-utility [data-model-topic=battery]').click();await expect(page).toHaveURL(/model-report.html#battery/);await expect(page.locator('body')).toContainText('saved learning output');await expect(page.locator('body')).toContainText('Original dispatch');expect(requests).toEqual([]);
});
