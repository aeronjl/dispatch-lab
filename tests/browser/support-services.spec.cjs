const {test,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),z=require('node:zlib');
const fixture=JSON.parse(z.gunzipSync(fs.readFileSync('tests/fixtures/support-services.json.gz'))).retrieval;
const read=name=>fs.readFileSync(path.resolve('assets',name),'utf8');
const preview=path.resolve('build/services/support/browser.html');
const seek=(page,h)=>page.locator('[data-m="scrubber"]').evaluate((n,h)=>{n.value=h;n.dispatchEvent(new Event('input',{bubbles:true}));},h);
test.beforeAll(()=>{
  const css=['app.css','plant-motion.css','plant-scene.css','methane.css','solar.css','field-scene.css'].map(read).join('\n');
  const font=fs.readFileSync('assets/fonts/DepartureMono-Regular.woff2').toString('base64');
  const script=read('playback.js').split('function frameAt')[0]+read('field-operations.js')+read('field-scene.js')+read('methane.js')+read('solar.js');
  const props=JSON.stringify(fixture).replaceAll('<','\\u003c');
  const html=`<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1"><style>${css}@font-face{font-family:'Departure Mono';src:url(data:font/woff2;base64,${font})}body{margin:0;background:#202020}</style><main id="preview">${read('methane.html').replace('<!-- SOLAR WORKSPACE -->',read('solar.html'))}</main><script>${script}\nconst props=${props};mountMethane(document.querySelector('#preview'),props,()=>{},()=>{});</script>`;
  fs.mkdirSync(path.dirname(preview),{recursive:true});fs.writeFileSync(preview,html);
});

test('support inspector retains failed work, separate acceptance and unpriced quantities offline',async({page})=>{
  const errors=[],network=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{if(/^https?:/.test(route.request().url())){network.push(route.request().url());route.abort();}else route.continue();});
  await page.goto('file://'+preview);await page.evaluate(()=>document.fonts.ready);
  await seek(page,6);await page.locator('.f-cleaner').focus();await page.keyboard.press('Enter');
  const inspector=page.locator('[data-m="services"]');
  await expect(inspector).toContainText('awaiting drive test');
  await expect(inspector).toContainText('Hardware returned at H6');
  await expect(inspector).toContainText('Crew commitment');
  await page.keyboard.press('Escape');await expect(page.locator('.f-cleaner')).toBeFocused();
  await seek(page,7);await page.keyboard.press('Enter');
  await expect(inspector).toContainText('available');
  await expect(inspector).toContainText('Remote supervision');
  await expect(inspector).toContainText('Unpriced');
  await page.keyboard.press('Escape');
  await seek(page,8);await expect(page.locator('.f-cleaner')).toHaveAttribute('data-phase','stranded');
  await page.setViewportSize({width:390,height:844});
  await page.locator('[data-do="menu"]').click();await page.locator('[data-panel="services"]').click();
  await expect(inspector).toBeVisible();
  expect(errors).toEqual([]);expect(network).toEqual([]);
});

test('retrieval drawings show preparation, transport and dock testing; reduced motion uses boundaries',async({page})=>{
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.goto('file://'+preview);await page.evaluate(()=>document.fonts.ready);
  // Drive the same production renderer at exact recorded fractions for visual review.
  await page.evaluate(()=>{
    const root=document.querySelector('#preview');root.querySelector('.field-world').remove();
    window.review=createFieldScene({root,getResult:()=>props.value,getController:()=> 'Greedy',inspect:()=>{}});
  });
  for(const [name,h,f] of [['preparing',4,.25],['loading',4,.55],['transport',4,.85],['testing',6,.1]]){
    await seek(page,h);
    await page.evaluate(({h,f})=>window.review.render({hour:h,fraction:f,playing:true}),{h,f});
    await page.locator('.m-plant').screenshot({path:`build/services/support/${name}.png`});
    if(name==='transport'){
      await expect(page.locator('.f-cleaner')).toHaveAttribute('data-phase','retrieval');
      await expect(page.locator('.f-recovery-trailer')).toBeVisible();
    }
    if(name==='testing')await expect(page.locator('.f-cleaner')).toHaveAttribute('data-working','false');
  }
  await page.emulateMedia({reducedMotion:'reduce'});
  const poses=await page.evaluate(()=>{
    const poses=[];for(const fraction of [.2,.8]){window.review.render({hour:4,fraction,playing:true});poses.push(document.querySelector('.f-human').getAttribute('transform'));}return poses;
  });
  expect(poses[0]).toBe(poses[1]);
});
