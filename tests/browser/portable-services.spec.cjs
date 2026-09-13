const {test,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),z=require('node:zlib');
const fixtures=JSON.parse(z.gunzipSync(fs.readFileSync('tests/fixtures/portable-services.json.gz')));
const read=name=>fs.readFileSync(path.resolve('assets',name),'utf8');
const preview=name=>path.resolve(`build/services/portable/${name}-browser.html`);
const seek=(page,h)=>page.locator('[data-m="scrubber"]').evaluate((n,h)=>{n.value=h;n.dispatchEvent(new Event('input',{bubbles:true}));},h);
test.beforeAll(()=>{
  const css=['app.css','plant-motion.css','plant-scene.css','methane.css','solar.css','field-scene.css'].map(read).join('\n');
  const font=fs.readFileSync('assets/fonts/DepartureMono-Regular.woff2').toString('base64');
  const script=read('playback.js').split('function frameAt')[0]+read('field-operations.js')+read('field-scene.js')+read('methane.js')+read('solar.js');
  for(const [name,fixture] of Object.entries(fixtures)){
    const props=JSON.stringify(fixture).replaceAll('<','\\u003c');
    const html=`<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1"><style>${css}@font-face{font-family:'Departure Mono';src:url(data:font/woff2;base64,${font})}body{margin:0;background:#202020}</style><main id="preview">${read('methane.html').replace('<!-- SOLAR WORKSPACE -->',read('solar.html'))}</main><script>${script}\nconst props=${props};mountMethane(document.querySelector('#preview'),props,()=>{},()=>{});</script>`;
    fs.mkdirSync(path.dirname(preview(name)),{recursive:true});fs.writeFileSync(preview(name),html);
  }
});
test('portable tool is keyboard inspectable and water remains separate from kit stock offline',async({page})=>{
  const errors=[],network=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>{if(/^https?:/.test(r.request().url())){network.push(r.request().url());r.abort();}else r.continue();});
  await page.goto('file://'+preview('wet'));await page.evaluate(()=>document.fonts.ready);
  await seek(page,4);await expect(page.locator('.f-portable')).toBeVisible();
  await page.locator('.f-portable').focus();await page.keyboard.press('Enter');
  const panel=page.locator('[data-m="services"]');
  await expect(panel).toContainText('Portable wet cleaner');await expect(panel).toContainText('260 L');
  await expect(panel).toContainText('Unpriced');
  await page.keyboard.press('Escape');await expect(page.locator('.f-portable')).toBeFocused();
  await page.setViewportSize({width:390,height:844});await page.locator('[data-do="menu"]').click();
  await page.locator('[data-panel="services"]').click();await page.locator('[data-field-locate="portable"]').click();
  await expect(page.locator('.f-portable')).toBeFocused();
  expect(errors).toEqual([]);expect(network).toEqual([]);
});
test('wet spray follows treatment only; dry, failed and reduced-motion examples stay static',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.emulateMedia({reducedMotion:'no-preference'});
  for(const method of ['wet','dry','interrupted']){
    await page.goto('file://'+preview(method));await page.evaluate(()=>document.fonts.ready);
    await seek(page,4);
    await page.evaluate(()=>{
      const root=document.querySelector('#preview');root.querySelector('.field-world').remove();
      window.review=createFieldScene({root,getResult:()=>props.value,getController:()=> 'Greedy',inspect:()=>{}});
      window.review.render({hour:4,fraction:.5,playing:true});
    });
    if(method==='wet')await expect(page.locator('.f-portable-spray')).toBeVisible();
    else await expect(page.locator('.f-portable-spray')).toBeHidden();
    await page.locator('.m-plant').screenshot({path:`build/services/portable/${method}.png`});
    if(method==='wet'){
      await page.evaluate(()=>window.review.render({hour:3,fraction:.25,playing:true}));
      await expect(page.locator('.f-portable-spray')).toBeHidden();
      await page.evaluate(()=>window.review.render({hour:5,fraction:.2,playing:true}));
      await expect(page.locator('.f-portable-spray')).toBeHidden();
    }
  }
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.evaluate(()=>window.review.render({hour:4,fraction:.9,playing:true}));
  await expect(page.locator('.f-portable-spray')).toBeHidden();expect(errors).toEqual([]);
});
