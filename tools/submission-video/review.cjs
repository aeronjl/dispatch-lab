/* Decode and seek the delivered local MP4 in the browser; retain review frames. */
const fs=require('node:fs'),path=require('node:path');const {chromium}=require('playwright');
const out=path.resolve(__dirname,'../../build/submission-video');
async function main(){
 const browser=await chromium.launch();
 try{
  const page=await browser.newPage({viewport:{width:1920,height:1080}});page.setDefaultTimeout(30000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('file://'+path.join(out,'index.html'));await page.waitForFunction(()=>document.querySelector('video').readyState>=2);
  const video=await page.evaluate(async()=>{const v=document.querySelector('video');await v.play();return {width:v.videoWidth,height:v.videoHeight,duration:v.duration};});
  await page.waitForTimeout(800);const advanced=await page.evaluate(()=>{const v=document.querySelector('video');v.pause();v.controls=false;return v.currentTime>0;});
  if(!advanced||video.duration!==168)throw Error('Video did not play as expected');
  const times=[1,18,38,55,71,96,115,121,136,154,165];const frames=[];
  for(const second of times){await page.evaluate(t=>new Promise((resolve,reject)=>{const v=document.querySelector('video');v.addEventListener('seeked',()=>resolve(),{once:true});v.addEventListener('error',()=>reject(v.error),{once:true});v.currentTime=t;}),second);await page.waitForTimeout(100);const file=`encoded-${second}.png`;await page.locator('video').screenshot({path:path.join(out,file)});frames.push({second,file});}
  if(errors.length)throw Error(errors.join('\n'));fs.writeFileSync(path.join(out,'playback-review.json'),JSON.stringify({passed:true,browser:browser.version(),video,advanced,frames,errors},null,2)+'\n');console.log('Browser playback and eleven seeks passed.');
 }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
