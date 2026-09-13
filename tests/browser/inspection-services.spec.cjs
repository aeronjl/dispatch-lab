const {test,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),z=require('node:zlib');
const fixtures=JSON.parse(z.gunzipSync(fs.readFileSync('tests/fixtures/inspection-services.json.gz')));
const read=name=>fs.readFileSync(path.resolve('assets',name),'utf8');
const preview=name=>path.resolve(`build/services/inspection/${name}-browser.html`);
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
test('paired inspection reveals reference failures and preserves keyboard return offline',async({page})=>{
 const errors=[],network=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',r=>{if(/^https?:/.test(r.request().url())){network.push(r.request().url());r.abort();}else r.continue();});
 await page.goto('file://'+preview('reader-drift'));await page.evaluate(()=>document.fonts.ready);await seek(page,6);
 await expect(page.locator('.f-fixed_reader')).toBeVisible();await expect(page.locator('.f-rover')).toBeVisible();
 await expect(page.locator('.m-inspection-evidence')).toBeHidden();
 await page.locator('.f-fixed_reader').focus();await page.keyboard.press('Enter');
 const panel=page.locator('.m-inspection-evidence');
  await expect(panel).toContainText('channel isolated');await expect(panel).toContainText('share one contact');
 await expect(panel.locator('tbody tr')).toHaveCount(2);
 await expect(panel).toContainText('measured H5, available H5');
 await expect(panel).toContainText('measured H5.5, available H6');
  await panel.scrollIntoViewIfNeeded();await panel.screenshot({path:'build/services/inspection/reader-evidence.png'});
 await page.keyboard.press('Escape');await expect(page.locator('.f-fixed_reader')).toBeFocused();
 await page.locator('.m-plant').screenshot({path:'build/services/inspection/paired-readers.png'});
 await page.setViewportSize({width:390,height:844});await page.locator('[data-do="menu"]').click();await page.locator('[data-panel="services"]').click();
 await expect(panel).toBeVisible();await page.locator('[data-field-locate="rover"]').click();await expect(page.locator('.f-rover')).toBeFocused();
 expect(errors).toEqual([]);expect(network).toEqual([]);
});
test('late acquisition remains unavailable and shared-contact agreement keeps its limits',async({page})=>{
 for(const name of ['late-evidence','shared-contact']){
  await page.goto('file://'+preview(name));await seek(page,6);await page.locator('.f-fixed_reader').click();
  const panel=page.locator('.m-inspection-evidence');
  await expect(panel).toContainText(name==='late-evidence'?'Awaiting eligible measurement':'Contact evidence supported by fixed, mobile');
  await expect(panel).toContainText('agreement cannot exclude a common stuck contact');
  if(name==='late-evidence'){
   await page.keyboard.press('Escape');await seek(page,18);await page.locator('.f-fixed_reader').click();
   await expect(panel).toContainText('stale');await expect(panel).toContainText('measured H5, available H17');
  }
 }
});
test('inspection scenario exposes numeric reader faults separately from contact-state choices',async({page})=>{
 await page.goto('/');await page.locator('.m-plant').waitFor();
 await page.locator('[data-do="menu"]').click();await page.locator('[data-do="setup"]').first().click();
 await page.getByText('Field operations / robots, recovery and human service',{exact:true}).click();
 const drift=page.getByRole('spinbutton',{name:'fixed reader drift vph',exact:true});
 await expect(drift).toBeVisible();await drift.fill('-0.25');await expect(drift).toHaveValue('-0.25');
 await expect(page.getByRole('spinbutton',{name:'inspection fault start hour',exact:true})).toHaveValue('0');
 await expect(page.getByRole('checkbox',{name:'fixed reader dropout',exact:true})).toBeVisible();
 await expect(page.getByText('Shared contact fault / retrospective scenario',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'← Simulation',exact:true}).click();await expect(page.locator('.m-plant')).toBeVisible();
});
