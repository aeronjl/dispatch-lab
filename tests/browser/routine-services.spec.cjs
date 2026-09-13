const {test,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),z=require('node:zlib');
const fixtures=JSON.parse(z.gunzipSync(fs.readFileSync('tests/fixtures/routine-services.json.gz')));
const read=name=>fs.readFileSync(path.resolve('assets',name),'utf8');
const preview=name=>path.resolve('build/services/routine/'+name+'-browser.html');
const seek=(page,h)=>page.locator('[data-m="scrubber"]').evaluate((n,h)=>{n.value=h;n.dispatchEvent(new Event('input',{bubbles:true}));},h);
test.beforeAll(()=>{
 const css=['app.css','plant-motion.css','plant-scene.css','methane.css','solar.css','field-scene.css'].map(read).join('\n');
 const font=fs.readFileSync('assets/fonts/DepartureMono-Regular.woff2').toString('base64');
 const script=read('playback.js').split('function frameAt')[0]+read('field-operations.js')+read('field-scene.js')+read('methane.js')+read('solar.js');
 fs.mkdirSync(path.dirname(preview('routine')),{recursive:true});
 for(const [name,fixture] of Object.entries(fixtures)){
  const props=JSON.stringify(fixture).replaceAll('<','\\u003c');
  fs.writeFileSync(preview(name),`<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1"><style>${css}@font-face{font-family:'Departure Mono';src:url(data:font/woff2;base64,${font})}body{margin:0;background:#202020}</style><main id="preview">${read('methane.html').replace('<!-- SOLAR WORKSPACE -->',read('solar.html'))}</main><script>${script}\nconst props=${props};mountMethane(document.querySelector('#preview'),props,()=>{},()=>{});</script>`);
 }
});
test('routine inspector exposes completed work and unserved dock power offline, then restores focus',async({page})=>{
 const errors=[],network=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>{if(/^https?:/.test(route.request().url())){network.push(route.request().url());route.abort();}else route.continue();});
 await page.goto('file://'+preview('night-reserve'));await page.evaluate(()=>document.fonts.ready);
 await seek(page,12);await page.locator('.f-dock').focus();await page.keyboard.press('Enter');
 const panel=page.locator('[data-m="services"]');
 await expect(panel).toContainText('Scheduled routine work');await expect(panel).toContainText('unserved');await expect(panel).toContainText('Modelled expenditure');
 await expect(page.locator('.f-dock .f-light')).toHaveCSS('opacity','0.15');
 await panel.screenshot({path:'build/services/routine/inspector.png'});
 await page.keyboard.press('Escape');await expect(page.locator('.f-dock')).toBeFocused();
 await page.setViewportSize({width:390,height:844});await page.keyboard.press('Enter');await expect(panel).toBeVisible();
 await expect(panel.getByText('Scheduled routine work',{exact:true})).toBeVisible();
 await panel.getByText('Scheduled routine work',{exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:'build/services/routine/inspector-narrow.png'});
 expect(errors).toEqual([]);expect(network).toEqual([]);
});
test('routine technician phases and reduced motion keep the same recorded completion',async({page})=>{
 await page.emulateMedia({reducedMotion:'no-preference'});await page.goto('file://'+preview('routine'));await page.evaluate(()=>document.fonts.ready);
 await page.evaluate(()=>{const root=document.querySelector('#preview');root.querySelector('.field-world').remove();window.review=createFieldScene({root,getResult:()=>props.value,getController:()=> 'Greedy',inspect:()=>{}});});
 for(const [label,h,f] of [['travel',1,.1],['procedure',1,.6],['later-work',3,.5]]){
  await seek(page,h);await page.evaluate(({h,f})=>window.review.render({hour:h,fraction:f,playing:true}),{h,f});
  await page.locator('.m-plant').screenshot({path:`build/services/routine/${label}.png`});
 }
 await page.emulateMedia({reducedMotion:'reduce'});await page.reload();await seek(page,12);await page.locator('.f-dock').focus();await page.keyboard.press('Enter');
 await expect(page.locator('[data-m="services"]')).toContainText('Scheduled routine work');
});
test('setup retains fractional routine durations and dock rates',async({page})=>{
 await page.goto('/');await page.locator('.m-plant').waitFor();
 await page.locator('[data-do="menu"]').click();await page.locator('[data-do="setup"]').first().click();
 await page.getByText('Field operations / robots, recovery and human service',{exact:true}).click();
 const duration=page.getByRole('spinbutton',{name:'maintenance work hours',exact:true});
 const standby=page.getByRole('spinbutton',{name:'dock standby kw',exact:true});
 await duration.fill('0.5');await standby.fill('0.25');await duration.focus();
 await expect(duration).toHaveValue('0.5');await expect(standby).toHaveValue('0.25');
 const config=await page.request.get('/config');const components=(await config.json()).components;
 for(const label of ['maintenance work hours','dock standby kw'])expect(components.find(c=>c.props?.label===label).props.precision??null).toBeNull();
});
