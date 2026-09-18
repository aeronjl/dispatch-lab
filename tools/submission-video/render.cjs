/* Deterministic editorial assembly. All operating graphics use production renderers. */
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),crypto=require('node:crypto');
const {spawn}=require('node:child_process');const {once}=require('node:events');const {chromium}=require('playwright');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'build/submission-video');fs.mkdirSync(out,{recursive:true});
const read=p=>fs.readFileSync(path.join(root,p),'utf8'),hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const filehash=p=>hash(fs.readFileSync(path.join(root,p)));
const story=JSON.parse(read('tools/submission-video/storyboard.json'));let elapsed=0;story.scenes.forEach(s=>{s.start=elapsed;elapsed+=s.duration;s.end=elapsed;});story.duration=elapsed;
const cssAssets=['app.css','plant-motion.css','plant-scene.css','methane.css','solar.css','field-scene.css','control-view.css'];
const jsAssets=['playback.js','field-operations.js','field-scene.js','control-view.js','methane.js','solar.js'];
const sourceHashes={'assets/fonts/DepartureMono-Regular.woff2':filehash('assets/fonts/DepartureMono-Regular.woff2')};
function source(p){sourceHashes[p]=filehash(p);return read(p);}
function makeSource(name){
 const files=story.sources[name];const data=JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(root,files.motion))));const control=JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(root,files.control))));
 if(data.source_run_id!==control.source_run_id||data.source_integrity!==control.source_integrity)throw Error('Mismatched input sources');
 const scenes=story.scenes.filter(s=>s.kind===name);const localStory={...story,scenes};
 const script=source('assets/playback.js').split('function frameAt')[0]+jsAssets.slice(1).map(p=>source('assets/'+p)).join('\n');
 const css=cssAssets.map(p=>source('assets/'+p)).join('\n');const font=fs.readFileSync(path.join(root,'assets/fonts/DepartureMono-Regular.woff2')).toString('base64');
 const json=x=>JSON.stringify(x).replaceAll('<','\\u003c');
 const html=`<!doctype html><html lang="en"><meta charset="utf-8"><style>${css}@font-face{font-family:'Departure Mono';src:url(data:font/woff2;base64,${font})}${source('tools/demo-video/film.css')}${source('tools/submission-video/operation.css')}</style><main id="preview">${source('assets/methane.html').replace('<!-- SOLAR WORKSPACE -->',source('assets/solar.html'))}</main><div class="film"><p class="film-heading"></p></div><script>${script}\nconst props=${json(data.props)};const story=${json(localStory)};const controlFixture=${json(control)};${source('tools/demo-video/film.js')}\nconst baseRender=window.renderFilm;window.renderFilm=async t=>{const v=await baseRender(t);if(v.scene==='recovery')document.querySelector('.m-plant').setAttribute('viewBox','320 20 620 360');if(v.scene==='comparison')document.body.dataset.filmPolicy=String(Math.min(2,Math.floor((t-story.scenes.find(s=>s.id==='comparison').start)/6)));return v;};</script></html>`;
 fs.writeFileSync(path.join(out,name+'.html'),html);
 return {motion:{path:files.motion,sha256:filehash(files.motion),run_id:data.source_run_id,integrity:data.source_integrity,note:data.note},control:{path:files.control,sha256:filehash(files.control),note:control.note}};
}
async function main(){
 const sources=Object.fromEntries(Object.keys(story.sources).map(name=>[name,makeSource(name)]));
 const capture=JSON.parse(read('build/submission-video/capture-manifest.json'));
 for(const s of capture.shots)if(filehash(s.file)!==s.sha256)throw Error('Changed app capture: '+s.name);
 const markup=source('tools/submission-video/player-template.html').replace('STORY_JSON',JSON.stringify(story));
 fs.writeFileSync(path.join(out,'film.html'),markup);
 const browser=await chromium.launch({args:['--allow-file-access-from-files']});let encoder;
 try{
  const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});page.setDefaultTimeout(30000);const errors=[],network=[];page.on('pageerror',e=>{errors.push(e.message);console.error(e.message);});
  await page.route('**/*',route=>{if(/^https?:/.test(route.request().url())){network.push(route.request().url());route.abort();}else route.continue();});
  await page.goto('file://'+path.join(out,'film.html'));await page.waitForFunction(()=>window.ready===true);
  const preview=process.argv.includes('--preview');
  const samples=story.scenes.flatMap(s=>s.kind==='card'?[s.start+1]:s.kind==='screens'?s.screens.map((_,i)=>s.start+(i+.5)*s.duration/s.screens.length):[s.start+1,s.start+s.duration*.55,s.end-.5]);
  const seconds=preview?samples:Array.from({length:story.duration*story.fps},(_,i)=>i/story.fps);const ledger=[];let closed;
  if(!preview){encoder=spawn('ffmpeg',['-y','-loglevel','warning','-f','image2pipe','-framerate','30','-vcodec','mjpeg','-i','pipe:0','-an','-vf','scale=in_range=pc:out_range=tv:out_color_matrix=bt709,format=yuv420p','-c:v','libx264','-preset','fast','-crf','18','-g','60','-pix_fmt','yuv420p','-movflags','+faststart','-color_range','tv','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709',path.join(out,story.output+'.mp4')],{stdio:['pipe','ignore',fs.openSync(path.join(out,'encoder.log'),'w')]});closed=once(encoder,'close');encoder.stdin.on('error',()=>{});}
  for(let i=0;i<seconds.length;i++){
   const t=seconds[i],state=await page.evaluate(t=>window.renderSubmission(t),t);
   if(preview||i%story.fps===0)ledger.push({second:t,...state});
   if(preview)await page.screenshot({path:path.join(out,`preview-${String(i).padStart(2,'0')}.png`)});
   else{if(i===story.fps)await page.screenshot({path:path.join(out,'poster.png')});const bytes=await page.screenshot({type:'jpeg',quality:96});if(!encoder.stdin.write(bytes))await once(encoder.stdin,'drain');if(i%300===0)console.log(`${i}/${seconds.length} frames · ${state.id}`);}
   if(errors.length)throw Error(JSON.stringify(errors));
  }
  if(encoder){encoder.stdin.end();const [code]=await closed;if(code!==0)throw Error('Encoding failed');}
  if(network.length)throw Error('Unexpected external requests: '+network.join(','));
  const manifest={schema:story.schema,story,sources,capture,sourceHashes,browser:browser.version(),errors,network,ledger,limitations:['Edited selection of recorded examples, not a continuous live run.','Site/design exploration does not produce the subsequent operating recordings.','Recovery is a separate controlled release-1 example with original model and assumptions.','Inspection rover inspects; the shown replacement is performed by a human.','Comparison is predicted process dispatch from shared information; service schedule fixed; no policy superiority claim.','No plant calibration, field robot qualification or whole-system safety guarantee.']};
  for(const p of ['tools/submission-video/render.cjs','tools/submission-video/storyboard.json','tools/submission-video/capture.cjs','tools/submission-video/prepare.py'])manifest.sourceHashes[p]=filehash(p);
  fs.writeFileSync(path.join(out,preview?'preview-manifest.json':'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
  if(!preview){const player=`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dispatch Lab · submission film</title><style>body{margin:0;background:#181818;color:#eee;font:15px system-ui;min-height:100vh;display:grid;place-items:center}main{width:min(100%,1600px)}video{display:block;width:100%;max-height:90vh}p{padding:0 20px;display:flex;justify-content:space-between}a{color:inherit}</style><main><video controls playsinline preload="metadata" poster="poster.png" src="${story.output}.mp4"></video><p><span>2:48 · silent · recorded simulation examples</span><a href="${story.output}.mp4" download>Download MP4</a></p></main></html>`;fs.writeFileSync(path.join(out,'index.html'),player);}
  console.log(preview?'Preview ready':'Movie ready');
 }finally{if(encoder&&encoder.exitCode===null)encoder.kill();await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
