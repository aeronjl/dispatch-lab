/* Capture real app interactions in an isolated workspace. No production UI changes. */
const fs=require('node:fs'),path=require('node:path'),net=require('node:net'),crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'build/submission-video');
fs.mkdirSync(path.join(out,'screens'),{recursive:true});
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
async function main(){
 const socket=net.createServer();await new Promise(r=>socket.listen(0,'127.0.0.1',r));const port=socket.address().port;await new Promise(r=>socket.close(r));
 const workspace=fs.mkdtempSync(path.join(out,'capture-workspace-'));
 const archive='build/release-1/release-example/offline/recorded-run.json.gz';
 const log=fs.openSync(path.join(out,'capture-server.log'),'w');
 const server=spawn(path.join(root,'.venv/bin/python'),['app.py','--archive',archive,'--port',String(port)],{cwd:root,env:{...process.env,DISPATCH_DATA_ROOT:workspace,GRADIO_TEMP_DIR:path.join(workspace,'gradio')},stdio:['ignore',log,log]});
 let browser;
 try{
  let ready=false;for(let i=0;i<120;i++){try{const r=await fetch(`http://127.0.0.1:${port}/`);if(r.ok){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,500));}if(!ready)throw Error('Capture server not ready');
  browser=await chromium.launch();const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
  const errors=[],shots=[];page.on('pageerror',e=>errors.push(e.message));
  async function shot(name,note){await page.evaluate(()=>document.fonts.ready);await page.mouse.move(1850,1040);await page.waitForTimeout(500);const file=path.join(out,'screens',name+'.png');await page.screenshot({path:file});shots.push({name,file:path.relative(root,file),sha256:sha(fs.readFileSync(file)),note});console.log('Captured',name);}
  await page.goto(`http://127.0.0.1:${port}/`);await page.locator('.m-plant').waitFor();
  await page.locator('[data-do=menu]').click();await page.locator('[data-do=project]').click();await page.locator('.pj-sites button').first().waitFor();
  await shot('site','Actual Site screen; saved regional reference points, not approved parcels.');
  const seville=page.locator('.pj-sites button').filter({hasText:/Seville/i});await seville.click();await page.locator('[data-pj=create]').waitFor();await shot('seville','Seville reference selected. No plant performance claim.');
  await page.locator('[data-pj=create]').click();await page.locator('.pj-build').waitFor();await shot('build','New reference plant design created in isolated capture workspace.');
  await page.locator('.pj-drawing [data-pj-component=battery]').click();await page.locator('[data-pj-field="plant.battery_kwh"]').fill('1200');await page.waitForFunction(()=>document.querySelector('.pj-drawing [data-pj-svg=battery]')?.textContent==='1200 kWh');await shot('battery','Uncommitted design exploration: battery capacity changed to 1200 kWh. Subsequent recorded operating examples are separate.');
  await page.keyboard.press('Escape');await page.locator('[data-pj=close]').click();
  await page.locator('[data-m=scrubber]').evaluate(n=>{n.value='17';n.dispatchEvent(new Event('input',{bubbles:true}));});
  await page.locator('[data-component=battery]').click();await page.getByRole('button',{name:'How it is modelled',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.d-result-status')?.textContent.includes('Learning example'));await shot('model','Current-model battery teaching fixture, separate from the recording.');
  await page.locator('[data-input=efficiency]').evaluate(n=>{n.value='0.81';n.dispatchEvent(new Event('input',{bubbles:true}));});await page.waitForFunction(()=>document.querySelector('.d-metrics')?.textContent.includes('290'));await shot('model-change','Teaching efficiency changed; numerical result recomputed by the real Python adapter.');
  await page.locator('[data-d=context]').selectOption('This run');await page.locator('.d-reference-body h2').waitFor();await shot('trace','Original recorded operands and information categories.');
  const heading=page.getByRole('heading',{name:'Identity and decision assumptions',exact:true});await heading.scrollIntoViewIfNeeded();await shot('identity','Original source and dispatch assumptions remain identified.');
  if(errors.length)throw Error(JSON.stringify(errors));
  fs.writeFileSync(path.join(out,'capture-manifest.json'),JSON.stringify({schema:'dispatch-submission-capture/1',archive,archive_sha256:sha(fs.readFileSync(path.join(root,archive))),browser:browser.version(),viewport:{width:1920,height:1080},shots,errors},null,2)+'\n');
 }finally{if(browser)await browser.close();server.kill('SIGTERM');await new Promise(resolve=>{if(server.exitCode!==null)return resolve();server.once('exit',resolve);setTimeout(()=>{server.kill('SIGKILL');resolve();},5000).unref();});}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
