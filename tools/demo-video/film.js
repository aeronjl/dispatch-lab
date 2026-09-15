/* Movie direction only. Production renderers display saved quantities and plans. */
const productionClock=createPlaybackClock;
let filmNow=0,filmTick=null,filmClock,filmControl;
createPlaybackClock=options=>{
    filmClock=productionClock({...options,now:()=>filmNow,request:fn=>{filmTick=fn;return 1;},cancel:()=>{filmTick=null;}});
    return filmClock;
};
// Offline transport of saved API responses. It never calls a running application.
const productionControl=createControlView;
let controlLoads=[];
createControlView=options=>{
    filmControl=productionControl({...options,fetcher:async(url,init)=>{
        const request=JSON.parse(init.body),selection=`${request.controller}|${request.hour}`;
        if(url!=='/dispatch/control-view')throw Error('Unexpected film transport');
        let saved;
        if(request.operation==='describe')saved=controlFixture?.views[selection];
        else if(request.operation==='start'&&request.controller===controlFixture.comparison_selection.controller&&request.hour===controlFixture.comparison_selection.hour)saved=controlFixture.comparison;
        else if(request.operation==='cancel')saved={status:'cancelled'};
        if(!saved)throw Error(`No saved control response for ${selection} / ${request.operation}`);
        controlLoads.push({operation:request.operation,selection,information_id:saved.information_id||saved.comparison?.information_id||null});
        return {ok:true,json:async()=>({...structuredClone(saved),key:request.key})};
    }});
    return filmControl;
};
if(controlFixture){props.value.model_token='offline-film-fixture';props.value.offline_mode=false;} // Enable only the saved-response transport above.
mountMethane(document.querySelector('#preview'),props,()=>{},()=>{});
const source=props.value,svg=document.querySelector('.m-plant'),consoleRoot=document.querySelector('.methane-console');
consoleRoot.dataset.costs='false';
const q=s=>document.querySelector(s);
const clamp=n=>Math.max(0,Math.min(1,n));
const ease=n=>{n=clamp(n);return n*n*(3-2*n);};
const mix=(a,b,t)=>a.map((v,i)=>v+(b[i]-v)*t);
const full=[0,0,1280,550];
let priorScene=null,priorController=null,priorTab=null,priorOffset=null,comparisonLoaded=false;
function selectPolicy(controller){
    if(controller===priorController)return;
    const selector=q('[data-m=controller]');selector.value=controller;selector.dispatchEvent(new Event('change',{bubbles:true}));priorController=controller;
}
async function settleControls(){
    // Two nested await boundaries in the production read-only transport.
    for(let i=0;i<8;i++)await Promise.resolve();
    if(q('[data-cv=status]')?.textContent?.includes('Loading recorded'))throw Error('Saved controls did not settle');
}
window.renderFilm=async seconds=>{
    const scene=story.scenes.find(s=>seconds>=s.start&&seconds<s.end)||story.scenes.at(-1);
    const local=seconds-scene.start,progress=clamp(local/(scene.end-scene.start));
    const controller=scene.id==='comparison'&&!scene.control?['Greedy','MPC · methane','MPC · economics'][Math.min(2,Math.floor(local/2))]:story.controller;
    selectPolicy(controller);
    const segment=scene.segments?.find(s=>local>=s.seconds[0]&&local<s.seconds[1]);
    const at=segment?segment.hours[0]+(segment.hours[1]-segment.hours[0])*(local-segment.seconds[0])/(segment.seconds[1]-segment.seconds[0]):scene.hours[0]+(scene.hours[1]-scene.hours[0])*progress;
    if(priorScene!==scene.id){
        filmControl?.close(false);filmNow=0;filmClock.seek(Math.floor(scene.hours[0]));
        if(scene.control){filmControl.open(scene.component);await settleControls();}
        else if(scene.id!=='comparison')filmClock.play();
        priorScene=scene.id;priorTab=null;priorOffset=null;comparisonLoaded=false;
        q('.cv-content').scrollTop=0;
    }
    if(scene.control){
        if(filmClock.snapshot().hour!==Math.floor(at)){filmClock.seek(Math.floor(at));await settleControls();}
        const tab=scene.tabs?.findLast(t=>local>=t.at)?.tab||scene.control;
        if(tab!==priorTab){q(`[data-cv-tab="${tab}"]`).click();priorTab=tab;}
        if(scene.comparison&&!comparisonLoaded){q('[data-cv=calculate]').click();await settleControls();comparisonLoaded=true;}
        const offset=scene.forecast_offsets?.findLast(o=>local>=o.at)?.offset??Math.min(5,Math.floor(local/1.5));
        if(offset!==priorOffset&&['Plan','Compare'].includes(tab)){const slider=q('[data-cv=offset]');slider.value=offset;slider.dispatchEvent(new Event('input',{bubbles:true}));priorOffset=offset;}
        q('.cv-content').scrollTop=0;
    }else{
        filmNow=(at-scene.hours[0])*1000;
        if(filmTick)filmTick(filmNow);
    }
    const hour=filmClock.snapshot().hour,row=source.records[controller][Math.max(0,hour-1)];
    let heading=scene.heading,camera=full;
    if(scene.id==='plant'||scene.id==='outro')camera=mix([18,4,1244,535],full,ease(progress));
    if(scene.id==='power')camera=mix(full,[-18,20,910,550],ease(local/.9));
    if(scene.id==='cleaning')camera=mix(full,[-80,28,750,295],ease((local-1)/2.1));
    if(scene.id==='inspection')camera=mix(full,[335,28,850,335],ease((local-1.8)/3.5));
    if(scene.id==='repair'){
        camera=local<2?mix([390,20,1010,398],[330,20,1010,398],ease(local/2)):mix([330,20,1010,398],[300,25,760,300],ease((local-2)/2.5));
        const job=row.field_operations.state.orders.findLast(o=>o.kind==='human-service');
        if(job?.status==='awaiting verification')heading='Awaiting verification';
    }
    if(scene.id==='comparison'&&!scene.control)heading={'Greedy':'Greedy control','MPC · methane':'Methane-first MPC','MPC · economics':'Economic MPC'}[controller];
    if(scene.id==='plan')camera=[-20,70,760,455];
    if(scene.id==='adapt')camera=[320,20,620,360];
    svg.setAttribute('viewBox',camera.map(x=>x.toFixed(4)).join(' '));
    document.body.dataset.filmScene=scene.id;
    document.body.dataset.filmControl=String(!!scene.control);
    document.body.dataset.filmPolicy=String(scene.comparison?Math.min(2,Math.floor(local/3)):-1);
    q('.film-heading').textContent=heading;
    q('.film-heading').style.opacity=String(scene.id==='plant'?1:ease(local/.25));
    q('.film-heading').style.transform=`translateY(${scene.id==='plant'?0:(1-ease(local/.3))*8}px)`;
    if(scene.control){const panel=q('.cv-panel');panel.style.opacity=String(ease(local/.3));panel.style.transform=`translateY(${(1-ease(local/.4))*24}px)`;}
    for(const animation of document.getAnimations()){
        const target=animation.effect?.target,active=target&&getComputedStyle(target).animationPlayState!=='paused';animation.pause();if(active)animation.currentTime=seconds*1000;
    }
    const error=q('[data-cv=status]')?.textContent||'';
    if(scene.control&&/unavailable|failed|did not|requires the restored/i.test(error))throw Error(error);
    return {scene:scene.id,heading,controller,hour,fraction:filmClock.visualSnapshot().fraction,at,control:scene.control?{tab:priorTab,component:scene.component,decision_hour:Math.max(0,hour-1),forecast_offset:priorOffset,comparison:comparisonLoaded,information_id:comparisonLoaded?controlFixture.comparison.information_id:null}:null,actors:fieldVisualState(source,controller,filmClock.visualSnapshot()).actors.map(a=>({asset:a.asset,phase:a.phase,x:a.x,y:a.y,working:a.working})),capacity_kw:row.diagnosis_after.capacity_kw};
};
