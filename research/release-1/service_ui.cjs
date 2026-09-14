// Execute against the disposable current-source browser server. No run is mutated.
const {chromium,expect}=require('@playwright/test');
const fs=require('node:fs');
const path=require('node:path');
const topics=['cleaning','inspection','recovery','charging','logistics','service_costs','service_uncertainty'];
const simple={cleaning:['coverage',.1,.03],inspection:['offset',0,.03],logistics:['duration',1,0],service_costs:['crew_price',60,1],service_uncertainty:['duration',1,.01]};
const p95=x=>[...x].sort((a,b)=>a-b)[Math.floor(x.length*.95)];
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const receipts={version:'release-service-interaction/1',scope:'All new service controls, followed by 20 simple interactions per topic; frozen numerical qualification and Python regression active separately.',controls:[],performance:{}};
 await page.goto('http://127.0.0.1:7861/');await page.locator('.m-plant').waitFor();
 await page.getByRole('button',{name:'Simulation menu',exact:true}).click();await page.locator('.m-utility [data-model-topic=battery]').click();
 async function done(){await expect(page.locator('.d-layout')).not.toHaveAttribute('inert','',{timeout:60000});await expect(page.locator('.d-workspace')).toHaveAttribute('data-pending','false',{timeout:60000});}
 for(const topic of topics){
  console.log('Checking',topic);await page.locator('[data-d=index]').click();await page.locator(`[data-topic=${topic}]`).click();await done();
  const controls=await page.locator('[data-input]').evaluateAll(nodes=>nodes.map(n=>({key:n.dataset.input,value:n.value,next:n.tagName==='SELECT'?[...n.options].find(o=>o.value!==n.value).value:Number(n.value)<Number(n.max)?Number(n.value)+Number(n.step):Number(n.value)-Number(n.step)})));
  for(const c of controls){
   const response=page.waitForResponse(r=>r.url().includes('/dispatch/learning-')&&r.request().method()==='POST');
   await page.locator(`[data-input=${c.key}]`).evaluate((n,v)=>{n.value=String(v);n.dispatchEvent(new Event('input',{bubbles:true}));},c.next);
   if(['charging','recovery'].includes(topic))await page.locator('[data-d=calculate]').click();
   await response;await done();await expect(page.locator(`[data-input=${c.key}]`).locator('..')).toHaveAttribute('data-changed','true');
   receipts.controls.push({topic,key:c.key,value:c.next,status:await page.locator('.d-result-status').innerText()});
  }
  const resetting=page.waitForResponse(r=>r.url().includes('/dispatch/learning-')&&r.request().method()==='POST');await page.locator('[data-d=reset]').click();if(['charging','recovery'].includes(topic))await page.locator('[data-d=calculate]').click();await resetting;await done();
  if(simple[topic]){
   const [key,first,step]=simple[topic],samples=[];
   await page.evaluate(()=>performance.clearMeasures('model-render'));
   for(let i=0;i<20;i++){
    const ms=await page.evaluate(({key,value})=>new Promise((resolve,reject)=>{
     const started=performance.now(),status=document.querySelector('.d-result-status');
     const timer=setTimeout(()=>{observer.disconnect();reject(Error('Learning interaction timed out'))},10000);
     const observer=new MutationObserver(()=>{if(status.textContent.startsWith('Learning example')){observer.disconnect();clearTimeout(timer);resolve(performance.now()-started)}});
     observer.observe(status,{subtree:true,childList:true,characterData:true});
     const input=document.querySelector(`[data-input="${key}"]`);input.value=String(value);input.dispatchEvent(new Event('input',{bubbles:true}));
    }),{key,value:topic==='logistics'?1+i%4:first+step*i});
    samples.push(ms);
   }
   const renders=await page.evaluate(()=>performance.getEntriesByName('model-render').map(e=>e.duration));
   receipts.performance[topic]={samples_ms:samples,input_p95_ms:p95(samples),render_p95_ms:p95(renders),render_samples_ms:renders,passes:p95(samples)<=200&&p95(renders)<=10};
  }
 }
 receipts.errors=errors;
 fs.mkdirSync('build/release-1/receipts',{recursive:true});fs.writeFileSync('build/release-1/receipts/service-interaction.json',JSON.stringify(receipts,null,2));
 await page.keyboard.press('Escape');await expect(page.locator('.d-workspace')).toBeHidden();
 await browser.close();
 console.log(JSON.stringify({controls:receipts.controls.length,performance:receipts.performance,errors},null,2));
 if(errors.length||Object.values(receipts.performance).some(x=>!x.passes))process.exitCode=1;
})().catch(e=>{console.error(e);process.exit(1)});
