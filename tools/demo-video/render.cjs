#!/usr/bin/env node
/* Reproducible, offline screen capture of production renderers and saved quantities. */
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'../..');
const local=n=>fs.readFileSync(path.join(__dirname,n),'utf8');
const read=n=>fs.readFileSync(path.join(root,'assets',n),'utf8');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const story=JSON.parse(local('storyboard.json'));
const out=path.join(root,'build/demo-video');fs.mkdirSync(out,{recursive:true});
const input=fs.readFileSync(path.join(root,story.fixture));
const fixture=JSON.parse(zlib.gunzipSync(input));
const cssAssets=['app.css','plant-motion.css','plant-scene.css','methane.css','solar.css','field-scene.css'];
const jsAssets=['playback.js','field-operations.js','field-scene.js','methane.js','solar.js'];
const font=fs.readFileSync(path.join(root,'assets/fonts/DepartureMono-Regular.woff2')).toString('base64');
const script=read('playback.js').split('function frameAt')[0]+jsAssets.slice(1).map(read).join('\n');
const markup=`<div class="film"><header class="film-top"><div class="film-brand"><i class="film-mark"></i>DISPATCH LAB</div><div class="film-label">RECORDED SIMULATION · ILLUSTRATIVE SCENARIO</div></header><div class="film-divider"></div><div class="film-context"><span class="film-section"></span><span class="film-clock"></span></div><aside class="film-detail"></aside><div class="film-comparison" hidden></div><div class="film-caption"><div class="film-chapter"></div><h1 class="film-title"></h1><p class="film-subtitle"></p></div><div class="film-counter"></div><div class="film-progress"><i></i></div></div>`;
const html=`<!doctype html><html lang="en"><meta charset="utf-8"><title>Dispatch Lab · demo film</title><style>${cssAssets.map(read).join('\n')}@font-face{font-family:'Departure Mono';src:url(data:font/woff2;base64,${font})}${local('film.css')}</style><main id="preview">${read('methane.html').replace('<!-- SOLAR WORKSPACE -->',read('solar.html'))}</main>${markup}<script>${script}\nconst props=${JSON.stringify(fixture.props).replaceAll('<','\\u003c')};const story=${JSON.stringify(story)};${local('film.js')}</script></html>`;
fs.writeFileSync(path.join(out,'film.html'),html);
async function main(){
    const browser=await chromium.launch();
    let encoder=null;
    try{
        const page=await browser.newPage({viewport:{width:story.width,height:story.height},deviceScaleFactor:1,reducedMotion:'no-preference'});
        const errors=[],requests=[];
        page.on('pageerror',e=>errors.push(e.message));
        await page.route('**/*',route=>{if(/^https?:/.test(route.request().url())){requests.push(route.request().url());route.abort();}else route.continue();});
        await page.goto('file://'+path.join(out,'film.html'));await page.evaluate(()=>document.fonts.ready);
        const preview=process.argv.includes('--preview');
        const seconds=preview?[1,6.5,11.5,13.7,18,21.5,26,28.5,30.5,33.5,39]:Array.from({length:story.fps*story.duration},(_,i)=>i/story.fps);
        const ledger=[];
        let closed;
        if(!preview){
            encoder=spawn('ffmpeg',['-y','-loglevel','warning','-f','image2pipe','-framerate',String(story.fps),'-vcodec','mjpeg','-i','pipe:0','-an','-vf','scale=in_range=pc:out_range=tv:out_color_matrix=bt709,format=yuv420p','-c:v','libx264','-preset','slow','-crf','17','-g','60','-pix_fmt','yuv420p','-movflags','+faststart','-color_range','tv','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709',path.join(out,'dispatch-lab-demo.mp4')],{stdio:['pipe','ignore',fs.openSync(path.join(out,'encoder.log'),'w')]});
            closed=once(encoder,'close');
            encoder.stdin.on('error',()=>{});
        }
        for(let i=0;i<seconds.length;i++){
            const second=seconds[i];
            const state=await page.evaluate(t=>window.renderFilm(t),second);
            if(state.hour!==Math.floor(state.at+1e-8))throw new Error(`Playback selection mismatch at video second ${second}`);
            // Every encoded second retains its recorded selection and sprite phase for review.
            if(preview||i%story.fps===0)ledger.push({video_second:second,...state});
            if(preview)await page.screenshot({path:path.join(out,`preview-${String(i).padStart(2,'0')}.png`)});
            else{
                if(i===0)await page.screenshot({path:path.join(out,'poster.png')});
                const frame=await page.screenshot({type:'jpeg',quality:96});
                if(!encoder.stdin.write(frame))await once(encoder.stdin,'drain');
                if(i%150===0)console.log(`Captured ${i}/${seconds.length} frames · ${state.scene}`);
            }
        }
        if(encoder){encoder.stdin.end();const [code]=await closed;if(code!==0)throw new Error('Video encoding failed; see encoder.log');}
        if(errors.length||requests.length)throw new Error(JSON.stringify({errors,requests}));
        const inputs=[...new Set([...cssAssets,...jsAssets,'methane.html','solar.html','fonts/DepartureMono-Regular.woff2'])];
        const manifest={schema:'dispatch-demo-film/1',storyboard:story,source:{fixture:story.fixture,sha256:hash(input),run_id:fixture.source_run_id,integrity:fixture.source_integrity,note:fixture.note},presentation_source_sha256:Object.fromEntries(inputs.map(n=>['assets/'+n,hash(fs.readFileSync(path.join(root,'assets',n)))])),film_source_sha256:Object.fromEntries(['render.cjs','film.css','film.js','storyboard.json'].map(n=>[n,hash(local(n))])),browser:browser.version(),network_requests:requests,errors,ledger,limitations:['Selected recorded moments, not a continuous real-time recording.','Synthetic weather and illustrative equipment/service assumptions.','Schematic travel, cleaning and inspection poses do not model navigation or repair kinematics.','Human service performs the repair shown; recovery is not verified in the excerpt.','H18 comparisons are illustrative, not a ranking of policy performance.','Current rendering code displays archived model results; this is not numerical validation of the current model.']};
        fs.writeFileSync(path.join(out,preview?'preview-manifest.json':'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
        if(!preview)fs.writeFileSync(path.join(out,'index.html'),`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dispatch Lab · demo</title><style>body{margin:0;background:#181818;color:#ffa32d;font:14px monospace;display:grid;place-items:center;min-height:100vh}main{width:min(100%,1600px)}video{display:block;width:100%;max-height:90vh}a{color:inherit}p{padding:0 20px}</style><main><video controls playsinline preload="metadata" poster="poster.png" src="dispatch-lab-demo.mp4"></video><p>41 seconds · silent · recorded simulation &nbsp; <a href="dispatch-lab-demo.mp4" download>Download MP4</a></p></main></html>`);
        console.log(preview?'Preview frames ready.':'Video and manifest ready.');
    } finally {if(encoder&&!encoder.killed&&encoder.exitCode===null)encoder.kill();await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
