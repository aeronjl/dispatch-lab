const {test,expect}=require('@playwright/test');
const fs=require('node:fs');
async function ready(page){
  await page.goto('/');await page.locator('.m-plant').waitFor();await page.evaluate(()=>document.fonts.ready);
  await page.getByRole('button',{name:'Playback details',exact:true}).click();
  await page.locator('[data-m="scrubber"]').evaluate(s=>{s.value=12;s.dispatchEvent(new Event('input',{bubbles:true}));});
  await page.getByRole('button',{name:'Playback details',exact:true}).click();
}
async function menu(page,panel){
  await page.getByRole('button',{name:'Simulation menu',exact:true}).click();
  if(panel)await page.locator(`[data-panel="${panel}"]`).click();
}
async function analysis(page){
  await menu(page);await page.locator('[data-do="analysis"]').click();
}
test('plant and solar artwork match the pre-refactor reference',async({page})=>{
  test.skip(process.platform!=='darwin','PNG reference captured on the Apple Silicon reference environment; functional checks run on all platforms.');
  await ready(page);
  await page.locator('.m-plant').evaluate(n=>n.style.cssText='position:fixed;left:35.03125px;top:360.390625px;width:1369.9375px;min-width:0;height:470px');
  await expect(page.locator('.m-plant')).toHaveScreenshot('plant.png',{animations:'disabled',maxDiffPixelRatio:.001});
  await page.locator('.m-plant').evaluate(n=>n.style.cssText='');
  await page.locator('.solar-component').click();
  await page.locator('.s-circuit').evaluate(n=>n.style.cssText='position:fixed;left:35.03125px;top:391.78125px;width:1035.9375px;min-width:0;height:435px');
  await expect(page.locator('.s-circuit')).toHaveScreenshot('solar.png',{animations:'disabled',maxDiffPixelRatio:.001});
});
test('keyboard inspection, lazy plans and evidence remain usable',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));await ready(page);
  await page.locator('[data-component="reactor"]').focus();await page.keyboard.press('Enter');
  await expect(page.locator('.m-inspector')).toBeVisible();
  await page.getByRole('button',{name:'NEXT',exact:true}).click();
  await expect(page.locator('.m-prediction table')).toBeVisible();
  await page.locator('.m-model-evidence summary').click();
  if(process.env.DISPATCH_BROWSER_ARCHIVE){
    await expect(page.locator('.m-model-evidence')).toContainText('RECORDED MODEL');
    await expect(page.locator('.m-model-evidence')).toContainText('thermal_residual_kwh');
  }else{
    await expect(page.locator('.m-model-evidence')).toContainText('unavailable');
    await expect(page.locator('.m-model-evidence')).toContainText('legacy');
  }
  const download=await page.request.get('/gradio_api/file=docs/components.md');expect(download.ok()).toBeTruthy();
  await page.keyboard.press('Escape');
  await page.locator('.solar-component').focus();await page.keyboard.press('Enter');
  await expect(page.locator('.s-workspace')).toBeVisible();
  await page.getByRole('button',{name:'← PLANT OVERVIEW',exact:true}).click();
  await expect(page.locator('.solar-component')).toBeFocused();expect(errors).toEqual([]);
});
test('narrow-screen solar access and changed geometry',async({page})=>{
  await page.setViewportSize({width:390,height:844});await ready(page);
  await menu(page);await page.locator('[data-mobile-component="solar"]').click();
  await expect(page.locator('.s-workspace')).toBeVisible();
  const before=await page.locator('.s-panel-face').first().getAttribute('points');
  await page.locator('[data-setting="tilt"]').evaluate(s=>{s.value=60;s.dispatchEvent(new Event('input',{bubbles:true}));});
  await expect(page.locator('.s-panel-face').first()).not.toHaveAttribute('points',before);
  await expect(page.locator('[data-s="status"]')).toHaveText('DESIGN PREVIEW');
});
test('preview latency, render cost and immutable restored design',async({page})=>{
  await ready(page);
  if(process.env.DISPATCH_BATCH_ACTIVE){
    await analysis(page);await page.getByRole('tab',{name:'Experiments',exact:true}).click();
    await page.getByRole('button',{name:'Run / resume suite',exact:true}).click();
    await page.waitForTimeout(500);await page.getByRole('button',{name:'← Simulation',exact:true}).click();
  }
  await page.locator('.solar-component').click();const samples=[];
  for(let i=0;i<30;i++){
    const duration=await page.evaluate(i=>new Promise(resolve=>{
      const started=performance.now(),status=document.querySelector('[data-s="status"]');
      const observer=new MutationObserver(()=>{if(status.textContent==='DESIGN PREVIEW'){observer.disconnect();resolve(performance.now()-started);}});
      observer.observe(status,{childList:true,subtree:true,characterData:true});
      const s=document.querySelector('[data-setting="tilt"]');s.value=31+i;s.dispatchEvent(new Event('input',{bubbles:true}));
    }),i);samples.push(duration);
  }
  await page.locator('[data-s="restore"]').click();await expect(page.locator('[data-s="status"]')).toHaveText('RECORDED DESIGN');
  await page.locator('[data-s="back"]').click();
  const timings=await page.evaluate(()=>performance.getEntriesByName('dispatch-render').map(e=>e.duration));
  const solarTimings=await page.evaluate(()=>performance.getEntriesByName('dispatch-solar-render').map(e=>e.duration));
  const hours=Number(await page.locator('[data-m="scrubber"]').getAttribute('max'));
  const p95=x=>[...x].sort((a,b)=>a-b)[Math.floor(x.length*.95)];
  fs.mkdirSync('build/engineering',{recursive:true});fs.writeFileSync(`build/engineering/browser-performance${process.env.DISPATCH_BATCH_ACTIVE?`-${hours}h-batch`:''}.json`,JSON.stringify({environment:process.platform,preview_samples_ms:samples,first_input_ms:samples[0],preview_p95_ms:p95(samples),render_p95_ms:Math.max(p95(timings),p95(solarTimings)),plant_render_p95_ms:p95(timings),solar_render_p95_ms:p95(solarTimings),render_sample_counts:{plant:timings.length,solar:solarTimings.length},fixture:process.env.DISPATCH_BROWSER_ARCHIVE||process.env.DISPATCH_BROWSER_HOURS||'archived demo',fixture_hours:hours,batch_active:!!process.env.DISPATCH_BATCH_ACTIVE},null,2));
  if(process.env.DISPATCH_BATCH_ACTIVE){
    await analysis(page);await page.getByRole('tab',{name:'Experiments',exact:true}).click();
    await page.getByRole('button',{name:'Cancel suite',exact:true}).click();
    await expect(page.getByText('Cancellation requested.',{exact:false})).toBeVisible();
  }
  expect(p95(timings)).toBeLessThanOrEqual(10);
  expect(p95(solarTimings)).toBeLessThanOrEqual(10);
  if(process.env.DISPATCH_PERFORMANCE_GATE)expect(p95(samples)).toBeLessThanOrEqual(200);
});

test('playback, controller views, costs and event navigation',async({page})=>{
  await ready(page);const scrubber=page.locator('[data-m="scrubber"]');
  await page.getByRole('button',{name:'Step forward',exact:true}).click();await expect(scrubber).toHaveValue('13');
  await page.getByRole('button',{name:'Step back',exact:true}).click();await expect(scrubber).toHaveValue('12');
  await page.locator('[data-do="timeline"]').click();await page.locator('[data-m="speed"]').selectOption('8');await page.locator('[data-do="play"]').click();
  await expect(scrubber).not.toHaveValue('12');await page.locator('[data-do="play"]').click();
  await menu(page);await page.locator('[data-do="costs"]').click();await expect(page.locator('[data-do="costs"]')).toHaveAttribute('aria-pressed','false');
  for(const value of await page.locator('[data-m="controller"] option').evaluateAll(xs=>xs.map(x=>x.value)))await page.locator('[data-m="controller"]').selectOption(value);
  await page.locator('[data-panel="events"]').click();const event=page.locator('.m-events button').first();if(await event.count()){await event.click();await expect(page.locator('.m-inspector')).toBeVisible();}
});

test('superseded preview responses cannot replace the latest design',async({page})=>{
  await ready(page);await page.locator('.solar-component').click();let requests=0;
  await page.route('**/dispatch/preview-solar',async route=>{
    const number=++requests;const response=await route.fetch();
    if(number===1)await new Promise(resolve=>setTimeout(resolve,450));
    await route.fulfill({response}).catch(()=>{});
  });
  const edit=value=>page.locator('[data-setting="tilt"]').evaluate((s,value)=>{s.value=value;s.dispatchEvent(new Event('input',{bubbles:true}));},value);
  await edit(41);await expect.poll(()=>requests).toBe(1);await edit(63);
  await expect(page.locator('[data-s="status"]')).toHaveText('DESIGN PREVIEW');
  const latest=await page.locator('.s-workspace').innerText();
  await page.waitForTimeout(600);await expect(page.locator('[data-setting="tilt"]')).toHaveValue('63');
  expect(await page.locator('.s-workspace').innerText()).toBe(latest);
});


test('quiet full viewport, retreat controls and discoverable recovery',async({page})=>{
  await ready(page);
  for(const selector of ['.m-score','[data-m="time"]','.m-events','.m-timeline','.m-inspector','.m-utility','#workspace-tabs > .tab-wrapper'])await expect(page.locator(selector)).toBeHidden();
  expect(await page.locator('.methane-console button:visible').count()).toBe(5);
  const bounds=await page.locator('.methane-console').boundingBox();expect(bounds).toEqual({x:0,y:0,width:1440,height:1000});
  expect(await page.evaluate(()=>document.documentElement.scrollHeight)).toBeLessThanOrEqual(1000);
  await page.setViewportSize({width:1112,height:987});
  const fits=await page.locator('.m-plant-wrap').evaluate(n=>n.scrollWidth<=n.clientWidth);
  expect(fits).toBe(true);
  await page.setViewportSize({width:1440,height:1000});
  await menu(page);await page.locator('[data-do="hide-ui"]').click();await expect(page.locator('.m-dock')).toBeHidden();
  await page.keyboard.press('Space');await expect(page.locator('.methane-console')).toHaveAttribute('data-playing','true');
  await page.keyboard.press('Space');await page.keyboard.press('h');await expect(page.locator('.m-dock')).toBeVisible();
  await menu(page,'events');await expect(page.locator('.m-events')).toBeVisible();await page.keyboard.press('Escape');await expect(page.locator('.m-utility')).toBeHidden();
});

test('separate analysis and setup return to the same playhead',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));await ready(page);
  await analysis(page);await expect(page.locator('#analysis-screen')).toBeVisible();await expect(page.locator('.m-plant')).toBeHidden();
  for(const name of ['Experiments','Saved runs','Guide','Run report']){await page.getByRole('tab',{name,exact:true}).click();}
  await page.getByRole('button',{name:'← Simulation',exact:true}).click();await expect(page.locator('.m-plant')).toBeVisible();await expect(page.locator('[data-m="scrubber"]')).toHaveValue('12');
  await menu(page);await page.locator('[data-do="setup"]').first().click();await expect(page.locator('#setup-screen')).toBeVisible();await expect(page.locator('.m-plant')).toBeHidden();
  await page.getByRole('button',{name:'← Simulation',exact:true}).click();await expect(page.locator('[data-m="scrubber"]')).toHaveValue('12');expect(errors).toEqual([]);
});

test('battery trace is revealed on demand and follows the selected interval',async({page})=>{
  await ready(page);
  await expect(page.locator('.m-battery-trace')).toHaveCount(0);
  await page.locator('[data-component="battery"]').click();
  // Wait for the lazy decision response before opening its evidence disclosure.
  await expect(page.locator('.m-battery-trace')).not.toContainText('Loading recorded');
  await expect(page.locator('.m-battery-trace')).not.toHaveAttribute('open','');
  await page.locator('.m-battery-trace summary').first().click();
  if(process.env.DISPATCH_BATTERY_TRACE){
    await expect(page.locator('.m-battery-trace')).toContainText('dispatch-lab/dc-battery / 1');
    await expect(page.locator('.m-battery-trace')).toContainText('interval 11');
    await expect(page.locator('.m-battery-trace')).toContainText('battery_energy_balance');
    await expect(page.locator('.m-battery-trace')).toContainText('Displayed SOC (before rounding)');
    await page.getByRole('button',{name:'Step forward',exact:true}).click();
    await expect(page.locator('.m-battery-trace')).not.toContainText('Loading recorded');
    await page.locator('.m-battery-trace summary').first().click();
    await expect(page.locator('.m-battery-trace')).toContainText('interval 12');
    await expect(page.locator('.m-battery-trace')).not.toContainText('interval 11');
  }else{
    await expect(page.locator('.m-battery-trace')).toContainText('predates battery component records');
    await expect(page.locator('.m-battery-trace')).not.toContainText('RECORDED MODEL');
  }
  await page.keyboard.press('Escape');
  expect(await page.locator('.methane-console button:visible').count()).toBe(5);
  await menu(page);await page.locator('[data-do="setup"]').click();
  await page.getByText('Operating dynamics / storage, reactor and solar conversion',{exact:true}).click();
  await expect(page.getByText('Battery implementation',{exact:true})).toBeVisible();
});

test('legacy archive restores editable setup without inventing battery lineage',async({page})=>{
  await ready(page);await analysis(page);
  await page.getByRole('tab',{name:'Saved runs',exact:true}).click();
  await page.locator('#analysis-screen input[type="file"]').setInputFiles('tests/fixtures/browser-demo-v2.json.gz');
  await expect(page.getByRole('cell',{name:'browser-demo-v2.json.gz',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Load saved run',exact:true}).click();
  await page.getByRole('button',{name:'← Simulation',exact:true}).click();
  await expect(page.locator('[data-m="scrubber"]')).toHaveValue('0');
  await page.getByRole('button',{name:'Step forward',exact:true}).click();
  await page.locator('[data-component="battery"]').click();
  await expect(page.locator('.m-battery-trace')).not.toContainText('Loading recorded');
  await page.locator('.m-battery-trace summary').first().click();
  await expect(page.locator('.m-battery-trace')).toContainText('predates battery component records');
});

test('component and repriced cost lineage stay behind disclosures',async({page})=>{
  test.skip(!process.env.DISPATCH_COMPONENT_TRACE,'Requires a new component-record archive.');
  await ready(page);
  for(const component of ['electrolyser','hydrogen','co2','reactor']){
    await page.locator(`[data-component="${component}"]`).click();
    const disclosure=page.locator('.m-component-trace');
    await expect(disclosure).not.toContainText('Loading recorded');
    await expect(disclosure).not.toHaveAttribute('open','');
    await disclosure.locator('summary').first().click();
    await expect(disclosure).toContainText('dispatch-lab/');
    await expect(disclosure).toContainText('Observed channels');
    await page.getByRole('button',{name:'COSTS',exact:true}).click();
    await page.locator('.m-cost-trace summary').click();
    await expect(page.locator('.m-cost-trace')).toContainText('dispatch_price_version');
    await expect(page.locator('.m-cost-trace')).toContainText('report_price_version');
    await page.keyboard.press('Escape');
  }
  await page.locator('.solar-component').click();
  await page.locator('.s-assumptions summary').filter({hasText:'MODEL AND EVIDENCE'}).click();
  await page.getByText('TRACE RECORDED GENERATION',{exact:true}).click();
  await expect(page.locator('[data-s="lineage"]')).toContainText(process.env.DISPATCH_OPTICAL_TRACE?'dispatch-lab/solar-sections':'dispatch-lab/reference-pv');
  if(process.env.DISPATCH_OPTICAL_TRACE){
    await expect(page.locator('[data-s="lineage"]')).toContainText(process.env.DISPATCH_SURFACE_MODEL||'array-surface/1');
    await expect(page.locator('[data-s="status"]')).toHaveText('RECORDED SURFACE');
  }
});

test('portable offline bundle plays without network access',async({page})=>{
  test.skip(!process.env.DISPATCH_OFFLINE_PLAYER,'Requires an extracted reproduction bundle.');
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const requests=[];page.on('request',r=>{if(/^https?:/.test(r.url()))requests.push(r.url());});
  await page.context().setOffline(true);
  await page.goto('file://'+process.env.DISPATCH_OFFLINE_PLAYER);
  await page.locator('.m-plant').waitFor();
  await page.getByRole('button',{name:'Step forward',exact:true}).click();
  await expect(page.locator('[data-m="scrubber"]')).toHaveValue('1');
  await page.locator('[data-component="reactor"]').click();
  await page.getByRole('button',{name:'NEXT',exact:true}).click();
  await expect(page.locator('.m-prediction table')).toBeVisible();
  expect(errors).toEqual([]);expect(requests).toEqual([]);
});

test('solar defers recorded lineage until its disclosure is opened',async({page})=>{
  await ready(page);await page.locator('.solar-component').click();
  const lineage=page.locator('[data-s="lineage"]');
  await expect(lineage).toContainText('Select an executed interval');
  await page.locator('.s-workspace').getByText('MODEL AND EVIDENCE',{exact:true}).click();
  await expect(lineage).toContainText('Select an executed interval');
  await page.locator('.s-workspace').getByText('TRACE RECORDED GENERATION',{exact:true}).click();
  await expect(lineage).toContainText('PLANT-01/PV-01');
  await page.keyboard.press('Escape');await expect(page.locator('.s-workspace')).toBeHidden();
});
