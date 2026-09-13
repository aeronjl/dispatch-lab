const {test,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib');
const read=name=>fs.readFileSync(path.resolve('assets',name),'utf8');
const fixture=JSON.parse(zlib.gunzipSync(fs.readFileSync('tests/fixtures/field-motion.json.gz')));
const preview=path.resolve('build/field-operations/renderer-test.html');

test.beforeAll(()=>{
  // Actual recorded service rows, with current production renderer and clock.
  const css=['app.css','plant-motion.css','plant-scene.css','methane.css','solar.css','field-scene.css'].map(read).join('\n');
  const font=fs.readFileSync('assets/fonts/DepartureMono-Regular.woff2').toString('base64');
  const script=read('playback.js').split('function frameAt')[0]+read('field-operations.js')+read('field-scene.js')+read('methane.js')+read('solar.js');
  const props=JSON.stringify(fixture.props).replaceAll('<','\\u003c');
  const html=`<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1"><style>${css}@font-face{font-family:'Departure Mono';src:url(data:font/woff2;base64,${font})}body{margin:0;background:#202020}</style><main id="preview">${read('methane.html').replace('<!-- SOLAR WORKSPACE -->',read('solar.html'))}</main><script>${script}\nconst props=${props};mountMethane(document.querySelector('#preview'),props,()=>{},()=>{});</script>`;
  fs.mkdirSync(path.dirname(preview),{recursive:true});fs.writeFileSync(preview,html);
});
async function ready(page){
  await page.goto('file://'+preview);await page.evaluate(()=>document.fonts.ready);
  await page.locator('[data-do="menu"]').click();await page.locator('[data-m="controller"]').selectOption('Greedy');
  await page.keyboard.press('Escape');
}
async function seek(page,h){await page.locator('[data-m="scrubber"]').evaluate((n,h)=>{n.value=h;n.dispatchEvent(new Event('input',{bubbles:true}));},h);}
const pose=(page,asset)=>page.locator('.f-'+asset).getAttribute('transform');
test('motion follows playback speed, pause, seek and controller without network requests',async({page})=>{
  const errors=[],network=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>{if(/^https?:/.test(r.request().url())){network.push(r.request().url());r.abort();}else r.continue();});
  await page.emulateMedia({reducedMotion:'no-preference'});await ready(page);
  await page.locator('[data-do="timeline"]').click();await page.locator('[data-m="speed"]').selectOption('0.25');
  const docked=await pose(page,'cleaner');await page.locator('[data-do="play"]').click();
  await expect.poll(()=>pose(page,'cleaner')).not.toBe(docked);
  await page.locator('[data-do="play"]').click();const frozen=await pose(page,'cleaner');
  await page.waitForTimeout(180);expect(await pose(page,'cleaner')).toBe(frozen);
  await page.locator('.f-cleaner').focus();await page.keyboard.press('Enter');
  await expect(page.locator('[data-m="services"]')).toContainText('In progress during H0 → H1');
  await page.keyboard.press('Escape');await page.locator('[data-do="timeline"]').click();
  await seek(page,13);await expect(page.locator('.f-rover')).toHaveAttribute('data-phase','perform');
  await page.locator('[data-m="speed"]').selectOption('2');await page.locator('[data-do="play"]').click();
  // Browser polling may miss a particular half-second playback frame.
  await expect.poll(async()=>Number(await page.locator('[data-m="scrubber"]').inputValue())).toBeGreaterThanOrEqual(14);await page.locator('[data-do="play"]').click();
  await seek(page,0);expect(await pose(page,'cleaner')).toBe(docked);
  await page.locator('[data-do="menu"]').click();
  for(const controller of ['MPC · methane','MPC · economics','Greedy']){
    await page.locator('[data-m="controller"]').selectOption(controller);await seek(page,15);
    const expected=fixture.props.value.records[controller][14].field_operations.state.orders;
    const rover=expected.findLast(o=>o.kind==='inspection');
    await expect(page.locator('.f-rover')).toHaveAttribute('data-order',rover?.id||'');
  }
  expect(errors).toEqual([]);expect(network).toEqual([]);
});
test('hardware inspection pauses, returns keyboard focus and is reachable on narrow screens',async({page})=>{
  await ready(page);await seek(page,14);
  await page.locator('.f-rover').focus();await page.keyboard.press('Enter');
  await expect(page.locator('[data-m="services"]')).toBeVisible();
  await expect(page.locator('.methane-console')).toHaveAttribute('data-playing','false');
  await page.keyboard.press('Escape');await expect(page.locator('.f-rover')).toBeFocused();
  await expect(page.locator('[data-m="scrubber"]')).toHaveValue('14');
  await page.setViewportSize({width:390,height:844});
  await page.locator('[data-do="menu"]').click();await page.locator('[data-panel="services"]').click();
  await page.locator('[data-field-locate="rover"]').click();await expect(page.locator('.f-rover')).toBeFocused();
  const bounds=await page.locator('.f-rover').boundingBox();expect(bounds.x).toBeGreaterThanOrEqual(0);expect(bounds.x+bounds.width).toBeLessThanOrEqual(390);
  await page.keyboard.press('Space');await expect(page.locator('[data-m="services"]')).toBeVisible();
  await page.keyboard.press('Escape');await expect(page.locator('.f-rover')).toBeFocused();
  await page.screenshot({path:'build/field-operations/scene-mobile.png'});
});
test('reduced motion changes poses only at hourly boundaries',async({page})=>{
  await ready(page);await seek(page,13);
  await page.locator('[data-do="timeline"]').click();await page.locator('[data-m="speed"]').selectOption('0.25');
  const before=await pose(page,'rover');await page.locator('[data-do="play"]').click();
  await page.waitForTimeout(220);expect(await pose(page,'rover')).toBe(before);
  await page.locator('[data-do="play"]').click();expect(await pose(page,'rover')).toBe(before);
  await seek(page,16);await expect(page.locator('.f-rover')).toHaveAttribute('data-phase','docked');
});
test('reviewed dock, cleaning, inspection and repair poses preserve the equipment composition',async({page})=>{
  test.skip(process.platform!=='darwin','Reviewed PNG reference uses Apple Silicon font rendering.');
  await ready(page);
  for(const [hour,name] of [[0,'dock'],[2,'cleaning'],[14,'inspection'],[17,'repair']]){
    await seek(page,hour);
    await expect(page.locator('.m-plant')).toHaveScreenshot('field-'+name+'.png',{animations:'disabled',maxDiffPixelRatio:.001});
  }
});
test('service renderer stays within the frame budget',async({page})=>{
  await ready(page);await page.emulateMedia({reducedMotion:'no-preference'});
  const timings=await page.evaluate(()=>{
    const host=document.createElement('div');host.innerHTML='<svg class="m-plant"></svg>';document.body.append(host);
    const scene=createFieldScene({root:host,getResult:()=>props.value,getController:()=> 'Greedy',inspect:()=>{}});
    const samples=[];
    for(let i=0;i<120;i++){const start=performance.now();scene.render({hour:13,fraction:i/120,playing:true});samples.push(performance.now()-start);}
    scene.destroy();host.remove();return samples.sort((a,b)=>a-b);
  });
  fs.writeFileSync('build/field-operations/render-performance.json',JSON.stringify({samples_ms:timings,p95_ms:timings[Math.floor(timings.length*.95)]},null,2));
  expect(timings[Math.floor(timings.length*.95)]).toBeLessThan(10);
});
