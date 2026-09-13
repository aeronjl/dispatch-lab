const {test,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),z=require('node:zlib');
const fixtures=JSON.parse(z.gunzipSync(fs.readFileSync('tests/fixtures/visit-services.json.gz')));
const read=name=>fs.readFileSync(path.resolve('assets',name),'utf8');
const preview=name=>path.resolve(`build/services/visits/${name}-browser.html`);
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
test('visit evidence stays behind inspection and separates planned jobs from return offline',async({page})=>{
 const errors=[],network=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',r=>{if(/^https?:/.test(r.request().url())){network.push(r.request().url());r.abort();}else r.continue();});
 await page.goto('file://'+preview('supplies'));await page.evaluate(()=>document.fonts.ready);await seek(page,4);
 await expect(page.locator('.m-visit-evidence')).toBeHidden();
 await page.locator('.f-human').focus();await page.keyboard.press('Enter');
 const panel=page.locator('.m-visit-evidence');
 await expect(panel).toContainText('Return not established');await expect(panel.locator('li')).toHaveCount(3);
 await panel.scrollIntoViewIfNeeded();await panel.screenshot({path:'build/services/visits/visit-evidence.png'});
 await page.keyboard.press('Escape');await expect(page.locator('.f-human')).toBeFocused();
 await seek(page,6);await page.locator('[data-do="menu"]').click();await page.locator('[data-panel="services"]').click();
 await expect(panel).toContainText('Returned H5.5');
 await page.setViewportSize({width:390,height:844});await expect(panel).toContainText('3.5 crew-hours');
 expect(errors).toEqual([]);expect(network).toEqual([]);
});
test('visit transfers and interrupted work retain recorded poses and reduced-motion boundaries',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.emulateMedia({reducedMotion:'no-preference'});
 for(const [name,h,f,label] of [['interventions',9,.625,'transfer'],['interventions',10,.4,'module-work'],['portable-transfer',5,.55,'tool-transfer'],['interrupted-portable',12,0,'stranded']]){
  await page.goto('file://'+preview(name));await page.evaluate(()=>document.fonts.ready);await seek(page,h);
  await page.evaluate(({h,f})=>{
   const root=document.querySelector('#preview');root.querySelector('.field-world').remove();
   window.review=createFieldScene({root,getResult:()=>props.value,getController:()=> 'Greedy',inspect:()=>{}});
   window.review.render({hour:h,fraction:f,playing:f>0});
  },{h,f});
  await expect(page.locator('.f-human')).toBeVisible();
  await page.locator('.m-plant').screenshot({path:`build/services/visits/${label}.png`});
  if(label==='stranded'){
   await expect(page.locator('.f-human')).toHaveAttribute('data-phase','stranded');
   await expect(page.locator('.f-portable-spray')).toBeHidden();
  }
 }
 await page.emulateMedia({reducedMotion:'reduce'});
 const poses=await page.evaluate(()=>[.2,.8].map(f=>{window.review.render({hour:12,fraction:f,playing:true});return document.querySelector('.f-human').getAttribute('transform');}));
 expect(poses[0]).toBe(poses[1]);expect(errors).toEqual([]);
});
test('combined-visit setup exposes the limit and declared on-site transfer time',async({page})=>{
 await page.goto('/');await page.locator('.m-plant').waitFor();
 await page.locator('[data-do="menu"]').click();await page.locator('[data-do="setup"]').first().click();
 await page.getByText('Field operations / robots, recovery and human service',{exact:true}).click();
 await expect(page.getByRole('checkbox',{name:'visit bundling enabled',exact:true})).toBeVisible();
 await expect(page.getByRole('spinbutton',{name:'visit max jobs',exact:true})).toHaveValue('4');
 await expect(page.getByRole('spinbutton',{name:'crew transfer hours',exact:true})).toHaveValue('0.25');
});
