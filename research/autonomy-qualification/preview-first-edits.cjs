// First edit after each fresh page/context; the local server is already loaded.
// No plant execution or dispatch mutation. Run against the disposable 240h server.
const {chromium}=require('@playwright/test');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true}),samples=[];
 try{
  for(let i=0;i<5;i++){
   const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
   const page=await context.newPage();await page.goto(process.env.DISPATCH_TEST_URL||'http://127.0.0.1:7861');await page.locator('.m-plant').waitFor();await page.evaluate(()=>document.fonts.ready);
   await page.locator('[data-m="scrubber"]').evaluate(s=>{if(Number(s.max)!==240)throw Error('Expected the 240-hour reference fixture');s.value=12;s.dispatchEvent(new Event('input',{bubbles:true}));});
   await page.locator('.solar-component').click();
   const result=await page.evaluate(tilt=>new Promise((resolve,reject)=>{
    const started=performance.now(),status=document.querySelector('[data-s="status"]');const timer=setTimeout(()=>{observer.disconnect();reject(Error('No matching preview after 10 seconds'));},10000);
    const observer=new MutationObserver(()=>{if(status.textContent==='DESIGN PREVIEW'){observer.disconnect();clearTimeout(timer);const r=performance.getEntriesByType('resource').filter(x=>x.name.includes('/dispatch/preview-solar')).at(-1);resolve({tilt,input_ms:performance.now()-started,request_ms:r?.duration,server_timing:r?.serverTiming.map(x=>({name:x.name,duration_ms:x.duration}))});}});
    observer.observe(status,{childList:true,subtree:true,characterData:true});const input=document.querySelector('[data-setting="tilt"]');input.value=tilt;input.dispatchEvent(new Event('input',{bubbles:true}));
   }),61+i);samples.push(result);await context.close();
  }
  const output={scope:'Five fresh browser contexts; first edit after the page and fonts are ready. Already-loaded local server; distinct tilt inputs. No CPU/network throttling. Not a process-cold or field percentile.',fixture_hours:240,browser:browser.version(),samples};
  const path=process.argv[2];if(!path)throw Error('Provide a new output path');fs.writeFileSync(path,JSON.stringify(output,null,2),{flag:'wx'});console.log(JSON.stringify(output));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
