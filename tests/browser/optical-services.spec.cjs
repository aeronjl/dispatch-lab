const {test,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib');
const fixtures=JSON.parse(zlib.gunzipSync(fs.readFileSync('tests/fixtures/optical-services.json.gz')));
const read=name=>fs.readFileSync(path.resolve('assets',name),'utf8');
const preview=name=>path.resolve(`build/services/cleaning/${name}-browser.html`);
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

test('recorded optical results and surface inventory stay separate from design editing offline',async({page})=>{
  const errors=[],network=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>{if(/^https?:/.test(r.request().url())){network.push(r.request().url());r.abort();}else r.continue();});
  await page.goto('file://'+preview('dry-brush'));await page.evaluate(()=>document.fonts.ready);
  const initial=await page.locator('.f-surface').innerHTML();expect(initial).not.toBe('');
  await seek(page,2);expect(await page.locator('.f-surface').innerHTML()).not.toBe(initial);
  await page.locator('.solar-component').focus();await page.keyboard.press('Enter');
  await expect(page.locator('[data-s="status"]')).toHaveText('RECORDED SURFACE');
  await expect(page.locator('[data-s="output"]')).toHaveText('691.6 kW');
  await expect(page.locator('[data-s="delta"]')).toHaveText('STATIC DESIGN ONLY');
  const recorded=await page.locator('[data-s="banks"]').innerHTML();
  // Editing is visible even without a calculation server; restoring always returns recorded optics.
  await page.locator('[data-setting="tilt"]').evaluate(n=>{n.value=60;n.dispatchEvent(new Event('input',{bubbles:true}));});
  await expect(page.locator('.s-workspace')).toHaveAttribute('data-dirty','true');
  await page.locator('[data-s="restore"]').click();
  await expect(page.locator('[data-s="status"]')).toHaveText('RECORDED SURFACE');
  expect(await page.locator('[data-s="banks"]').innerHTML()).toBe(recorded);
  await page.locator('.s-circuit').screenshot({path:'build/services/cleaning/recorded-surface.png'});
  await page.keyboard.press('Escape');await expect(page.locator('.solar-component')).toBeFocused();
  await expect(page.locator('[data-m="scrubber"]')).toHaveValue('2');
  await page.locator('.f-cleaner').focus();await page.keyboard.press('Enter');
  await expect(page.locator('[data-m="services"]')).toContainText('Brush');
  await expect(page.locator('[data-m="services"]')).toContainText('Adhered');
  await page.keyboard.press('Escape');await expect(page.locator('.f-cleaner')).toBeFocused();
  await page.setViewportSize({width:390,height:844});await page.locator('[data-do="menu"]').click();
  await page.locator('[data-mobile-component="solar"]').click();
  await expect(page.locator('[data-s="status"]')).toHaveText('RECORDED SURFACE');
  await expect(page.locator('[data-s="back"]')).toBeInViewport();
  expect(errors).toEqual([]);expect(network).toEqual([]);
});

test('failed brushing retains its partial effect and working position without animation',async({page})=>{
  await page.goto('file://'+preview('interrupted'));await page.evaluate(()=>document.fonts.ready);
  await seek(page,2);
  const pose=await page.locator('.f-cleaner').getAttribute('transform'),surface=await page.locator('.f-surface').innerHTML();
  await expect(page.locator('.f-cleaner')).toHaveAttribute('data-phase','stranded');
  await expect(page.locator('.f-cleaner')).toHaveAttribute('data-working','false');
  await seek(page,8);expect(await page.locator('.f-cleaner').getAttribute('transform')).toBe(pose);
  expect(await page.locator('.f-surface').innerHTML()).toBe(surface);
  await page.locator('.m-plant').screenshot({path:'build/services/cleaning/interrupted-scene.png'});
  await page.emulateMedia({reducedMotion:'no-preference'});
  const fixed=await page.evaluate(()=>{
    const host=document.createElement('div');host.innerHTML='<svg class="m-plant"></svg>';document.body.append(host);
    const scene=createFieldScene({root:host,getResult:()=>props.value,getController:()=> 'Greedy',inspect:()=>{}});
    const positions=[];
    for(const fraction of [.1,.9]){scene.render({hour:2,fraction,playing:true});positions.push(host.querySelector('.f-cleaner').getAttribute('transform'));}
    scene.destroy();host.remove();return positions;
  });
  expect(fixed[0]).toBe(fixed[1]);
});
