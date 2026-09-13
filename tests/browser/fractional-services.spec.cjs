const {test,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib');
const read=name=>fs.readFileSync(path.resolve('assets',name),'utf8');
const fixture=JSON.parse(zlib.gunzipSync(fs.readFileSync('tests/fixtures/fractional-services.json.gz'))).fixed;
const preview=path.resolve('build/services/coupled/browser-preview.html');
test.beforeAll(()=>{
  const css=['app.css','plant-motion.css','plant-scene.css','methane.css','solar.css','field-scene.css'].map(read).join('\n');
  const font=fs.readFileSync('assets/fonts/DepartureMono-Regular.woff2').toString('base64');
  const script=read('playback.js').split('function frameAt')[0]+read('field-operations.js')+read('field-scene.js')+read('methane.js')+read('solar.js');
  const props=JSON.stringify(fixture).replaceAll('<','\\u003c');
  const html=`<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1"><style>${css}@font-face{font-family:'Departure Mono';src:url(data:font/woff2;base64,${font})}body{margin:0;background:#202020}</style><main id="preview">${read('methane.html').replace('<!-- SOLAR WORKSPACE -->',read('solar.html'))}</main><script>${script}\nconst props=${props};mountMethane(document.querySelector('#preview'),props,()=>{},()=>{});</script>`;
  fs.mkdirSync(path.dirname(preview),{recursive:true});fs.writeFileSync(preview,html);
});
const seek=(page,h)=>page.locator('[data-m="scrubber"]').evaluate((n,h)=>{n.value=h;n.dispatchEvent(new Event('input',{bubbles:true}));},h);
test('fixed reader uses recorded evidence and returns inspection focus offline',async({page})=>{
  const errors=[],network=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>{if(/^https?:/.test(r.request().url())){network.push(r.request().url());r.abort();}else r.continue();});
  await page.goto('file://'+preview);await page.evaluate(()=>document.fonts.ready);
  await seek(page,5);
  await expect(page.locator('.f-rover')).toBeHidden();
  await expect(page.locator('.f-fixed_reader')).toBeVisible();
  await page.locator('.f-fixed_reader').focus();await page.keyboard.press('Enter');
  const panel=page.locator('[data-m="services"]');await expect(panel).toContainText('Fixed service electricity');
  await expect(panel).toContainText('Trip contact read');
  await page.keyboard.press('Escape');await expect(page.locator('.f-fixed_reader')).toBeFocused();
  await page.setViewportSize({width:390,height:844});
  await page.locator('[data-do="menu"]').click();await page.locator('[data-panel="services"]').click();
  await page.locator('[data-field-locate="fixed_reader"]').click();await expect(page.locator('.f-fixed_reader')).toBeFocused();
  expect(errors).toEqual([]);expect(network).toEqual([]);
});
test('fractional overlay follows supplied subhour spans and freezes under reduced motion',async({page})=>{
  await page.goto('file://'+preview);await page.emulateMedia({reducedMotion:'no-preference'});
  const phases=await page.evaluate(()=>{
    const host=document.createElement('div');host.innerHTML='<svg class="m-plant"></svg>';document.body.append(host);
    const scene=createFieldScene({root:host,getResult:()=>props.value,getController:()=> 'Greedy',inspect:()=>{}});
    const result=[];
    for(const [hour,fraction] of [[0,.25],[0,.75],[2,.6],[2,.9],[3,.5]]){
      scene.render({hour,fraction,playing:true});result.push(host.querySelector('.f-cleaner').dataset.phase);
    }
    scene.destroy();host.remove();return result;
  });
  expect(phases).toEqual(['travel','perform','verify','return','docked']);
  await page.emulateMedia({reducedMotion:'reduce'});await seek(page,5);
  const pose=await page.locator('.f-fixed_reader').getAttribute('transform');
  await page.locator('[data-do="play"]').click();await page.waitForTimeout(100);await page.locator('[data-do="play"]').click();
  expect(await page.locator('.f-fixed_reader').getAttribute('transform')).toBe(pose);
  await page.setViewportSize({width:1440,height:1000});await seek(page,5);
  await page.locator('.m-plant').screenshot({path:'build/services/coupled/fixed-reader-scene.png'});
});
