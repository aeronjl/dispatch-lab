const {test,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),z=require('node:zlib');
const fixtures=JSON.parse(z.gunzipSync(fs.readFileSync('tests/fixtures/hardware-services.json.gz')));
const read=name=>fs.readFileSync(path.resolve('assets',name),'utf8');
const preview=name=>path.resolve(`build/services/hardware/${name}-browser.html`);
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
test('hardware evidence is revealed on demand and retains failed release after repair offline',async({page})=>{
 const errors=[],network=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',r=>{if(/^https?:/.test(r.request().url())){network.push(r.request().url());r.abort();}else r.continue();});
 await page.goto('file://'+preview('drive-power-loss'));await page.evaluate(()=>document.fonts.ready);await seek(page,36);
 await expect(page.locator('.m-hardware-evidence')).toBeHidden();
 await page.locator('.f-cleaner').focus();await page.keyboard.press('Enter');
 const evidence=page.locator('.m-hardware-evidence');await expect(evidence).toContainText('Post-replacement function test tracked');
 const release=page.locator('.m-service-order').filter({hasText:'remote-release'});await expect(release).toContainText('awaiting verification');
 await evidence.scrollIntoViewIfNeeded();await evidence.screenshot({path:'build/services/hardware/evidence.png'});
 await page.keyboard.press('Escape');await expect(page.locator('.f-cleaner')).toBeFocused();
 await page.setViewportSize({width:390,height:844});await page.locator('[data-do="menu"]').click();await page.locator('[data-panel="services"]').click();await expect(evidence).toContainText('Compatible spares');
 expect(errors).toEqual([]);expect(network).toEqual([]);
});
test('recorded assistance, return, packing and module work preserve illustrated poses',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.emulateMedia({reducedMotion:'no-preference'});
 for(const [name,h,f,label] of [['control-hold',2,.125,'release'],['control-hold',5,.25,'guided-return'],['drive-power-loss',16,.4,'drive-module'],['pump-power-loss',4,.25,'packing'],['pump-power-loss',13,.5,'pump-module'],['interrupted-return',8,0,'interrupted-return'],['charger-power-loss',11,0,'failed-dock']]){
  await page.goto('file://'+preview(name));await page.evaluate(()=>document.fonts.ready);await seek(page,h);
  await page.evaluate(({h,f})=>{const root=document.querySelector('#preview');root.querySelector('.field-world').remove();window.review=createFieldScene({root,getResult:()=>props.value,getController:()=> 'Greedy',inspect:()=>{}});window.review.render({hour:h,fraction:f,playing:f>0});},{h,f});
  await page.locator('.m-plant').screenshot({path:`build/services/hardware/${label}.png`});
  if(label==='packing'||label==='pump-module'){await expect(page.locator('.f-portable')).toBeVisible();await expect(page.locator('.f-portable-lines')).toBeHidden();}
  if(label==='failed-dock')await expect(page.locator('.f-dock')).toHaveAttribute('data-failed','true');
 }
 await page.emulateMedia({reducedMotion:'reduce'});
 const poses=await page.evaluate(()=>[.2,.8].map(f=>{window.review.render({hour:11,fraction:f,playing:true});return document.querySelector('.field-world').innerHTML;}));expect(poses[0]).toBe(poses[1]);expect(errors).toEqual([]);
});
test('hardware setup exposes bounded persistent faults and finite remote support',async({page})=>{
 await page.goto('/');await page.locator('.m-plant').waitFor();await page.locator('[data-do="menu"]').click();await page.locator('[data-do="setup"]').first().click();
 await page.getByText('Field operations / robots, recovery and human service',{exact:true}).click();
 await expect(page.getByRole('checkbox',{name:'equipment recovery enabled',exact:true})).toBeVisible();
 await expect(page.getByRole('spinbutton',{name:'hardware spares',exact:true})).toHaveValue('2');
 await expect(page.getByRole('spinbutton',{name:'remote shift duration hours',exact:true})).toHaveValue('12');
 await expect(page.getByRole('combobox',{name:'cleaner service fault',exact:true})).toBeVisible();
});
