const {revealTool}=require('./navigation.cjs');
const {test,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),z=require('node:zlib');
const fixtures=JSON.parse(z.gunzipSync(fs.readFileSync('tests/fixtures/local-policy.json.gz')));
const read=name=>fs.readFileSync(path.resolve('assets',name),'utf8');
const preview=name=>path.resolve('build/services/local-policy/'+name+'-browser.html');
const seek=(page,h)=>page.locator('[data-m="scrubber"]').evaluate((n,h)=>{n.value=h;n.dispatchEvent(new Event('input',{bubbles:true}));},h);
test.beforeAll(()=>{
 const css=['app.css','plant-motion.css','plant-scene.css','methane.css','solar.css','field-scene.css'].map(read).join('\n');
 const font=fs.readFileSync('assets/fonts/DepartureMono-Regular.woff2').toString('base64');
 const script=read('playback.js').split('function frameAt')[0]+read('field-operations.js')+read('field-scene.js')+read('methane.js')+read('solar.js');
 fs.mkdirSync(path.dirname(preview('periodic')),{recursive:true});
 for(const [name,fixture] of Object.entries(fixtures)){
  const props=JSON.stringify(fixture).replaceAll('<','\\u003c');
  fs.writeFileSync(preview(name),`<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1"><style>${css}@font-face{font-family:'Departure Mono';src:url(data:font/woff2;base64,${font})}body{margin:0;background:#202020}</style><main id="preview">${read('methane.html').replace('<!-- SOLAR WORKSPACE -->',read('solar.html'))}</main><script>${script}\nconst props=${props};mountMethane(document.querySelector('#preview'),props,()=>{},()=>{});</script>`);
 }
});
test('periodic inspector records cadence and interrupted treatment offline',async({page})=>{
 for(const name of ['periodic','partial']){
  await page.goto('file://'+preview(name));await page.evaluate(()=>document.fonts.ready);await seek(page,18);
  await page.locator('.f-cleaner').focus();await page.keyboard.press('Enter');
  const panel=page.locator('[data-m="services"]');await expect(panel).toContainText('Local cleaning rule');await expect(panel).toContainText('full passes');
  await expect(panel).toContainText(name==='partial'?'0 full passes':/[1-9] full passes/);
  await panel.screenshot({path:'build/services/local-policy/'+name+'-inspector.png'});
  await page.keyboard.press('Escape');await expect(page.locator('.f-cleaner')).toBeFocused();
 }
});
test('prepared and enclosed fittings preserve keyboard inspection and narrow access',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 for(const name of ['prepared','enclosed']){
  await page.goto('file://'+preview(name));await page.evaluate(()=>document.fonts.ready);await seek(page,7);
  const port=page.locator('.f-contact-interface');await expect(port).toBeVisible();
  await expect(port).toHaveAccessibleName(name==='prepared'?/Prepared contact test port/:/Enclosed contact/);
  await expect(page.locator('.f-contact-prepared')).toBeVisible({visible:name==='prepared'});
  await page.locator('.m-plant').screenshot({path:'build/services/local-policy/'+name+'-plant.png'});
  await port.focus();await page.keyboard.press('Enter');const panel=page.locator('[data-m="services"]');
  await expect(panel).toContainText('Contact inspection access');
  await page.keyboard.press('Escape');await expect(port).toBeFocused();
  await page.setViewportSize({width:390,height:844});await port.focus();await page.keyboard.press('Enter');await expect(panel).toBeVisible();
  await panel.screenshot({path:'build/services/local-policy/'+name+'-narrow.png'});
  await page.setViewportSize({width:1440,height:1000});
 }
 expect(errors).toEqual([]);
});
test('setup exposes explicit rules and fractional recurrence',async({page})=>{
 await page.goto('/');await page.locator('.m-plant').waitFor();await page.locator('[data-do="menu"]').click();await revealTool(page,'[data-do="setup"]');await page.locator('[data-do="setup"]').first().click();
 await page.getByText('Field operations / robots, recovery and human service',{exact:true}).click();
 const response=await page.request.get('/config');const components=(await response.json()).components;
 for(const label of ['Local cleaning rule','Contact inspection access'])expect(components.some(c=>c.props?.label===label)).toBeTruthy();
 const period=page.getByRole('spinbutton',{name:'cleaning period hours',exact:true});await period.fill('4.5');await expect(period).toHaveValue('4.5');
 await expect(page.locator('.f-contact-interface')).toBeHidden();
});
