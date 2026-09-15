/* Video direction and a single editorial heading. Physical readouts stay in the app. */
const productionClock = createPlaybackClock;
let filmNow=0, filmTick=null, filmClock;
createPlaybackClock = options => {
    filmClock=productionClock({...options,now:()=>filmNow,request:fn=>{filmTick=fn;return 1;},cancel:()=>{filmTick=null;}});
    return filmClock;
};
mountMethane(document.querySelector('#preview'),props,()=>{},()=>{});
const source=props.value, svg=document.querySelector('.m-plant'), consoleRoot=document.querySelector('.methane-console');
consoleRoot.dataset.costs='false';
const q=s=>document.querySelector(s);
const clamp=n=>Math.max(0,Math.min(1,n));
const ease=n=>{n=clamp(n);return n*n*(3-2*n);};
const mix=(a,b,t)=>a.map((v,i)=>v+(b[i]-v)*t);
const full=[0,0,1280,550];
let priorScene=null, priorController=null;
function selectPolicy(controller) {
    if(controller===priorController)return;
    const selector=q('[data-m=controller]');selector.value=controller;selector.dispatchEvent(new Event('change',{bubbles:true}));
    priorController=controller;
}
window.renderFilm = seconds => {
    const scene=story.scenes.find(s=>seconds>=s.start&&seconds<s.end)||story.scenes.at(-1);
    const local=seconds-scene.start, progress=clamp(local/(scene.end-scene.start));
    const controller=scene.id==='comparison'?['Greedy','MPC · methane','MPC · economics'][Math.min(2,Math.floor(local/2))]:story.controller;
    selectPolicy(controller);
    if(priorScene!==scene.id){
        filmNow=0;filmClock.seek(Math.floor(scene.hours[0]));if(scene.id!=='comparison')filmClock.play();priorScene=scene.id;
    }
    const segment=scene.segments?.find(s=>local>=s.seconds[0]&&local<s.seconds[1]);
    const at=segment?segment.hours[0]+(segment.hours[1]-segment.hours[0])*(local-segment.seconds[0])/(segment.seconds[1]-segment.seconds[0]):scene.hours[0]+(scene.hours[1]-scene.hours[0])*progress;
    filmNow=(at-scene.hours[0])*1000;
    if(filmTick)filmTick(filmNow);
    const hour=filmClock.snapshot().hour, row=source.records[controller][Math.max(0,hour-1)];
    let heading=scene.heading;
    let camera=full;
    if(scene.id==='plant')camera=mix([18,4,1244,535],full,ease(progress));
    if(scene.id==='power')camera=mix(full,[-18,20,910,550],ease(local/.9));
    if(scene.id==='cleaning'){
        // Full departure path first, then an intentional camera move to the array.
        camera=mix(full,[-80,28,750,295],ease((local-1)/2.1));
    }
    if(scene.id==='inspection')camera=mix(full,[335,28,850,335],ease((local-1.8)/3.5));
    if(scene.id==='repair'){
        camera=local<2?mix([390,20,1010,398],[330,20,1010,398],ease(local/2)):mix([330,20,1010,398],[300,25,760,300],ease((local-2)/2.5));
        const job=row.field_operations.state.orders.findLast(o=>o.kind==='human-service');
        if(job?.status==='awaiting verification')heading='Awaiting verification';
    }
    if(scene.id==='comparison')heading={'Greedy':'Greedy control','MPC · methane':'Methane-first MPC','MPC · economics':'Economic MPC'}[controller];
    if(scene.id==='outro')camera=mix([18,4,1244,535],full,ease(progress));
    svg.setAttribute('viewBox',camera.map(x=>x.toFixed(4)).join(' '));
    q('.film-heading').textContent=heading;
    q('.film-heading').style.opacity=String(scene.id==='plant'?1:ease(local/.25));
    q('.film-heading').style.transform=`translateY(${scene.id==='plant'?0:(1-ease(local/.3))*8}px)`;
    // Seek CSS poses deterministically too; plant/robot state still comes from production renderers.
    for(const animation of document.getAnimations()){
        const target=animation.effect?.target;
        const active=target&&getComputedStyle(target).animationPlayState!=='paused';
        animation.pause();
        if(active)animation.currentTime=seconds*1000;
    }
    return {scene:scene.id,heading,controller,hour,fraction:filmClock.visualSnapshot().fraction,at,actors:fieldVisualState(source,controller,filmClock.visualSnapshot()).actors.map(a=>({asset:a.asset,phase:a.phase,x:a.x,y:a.y,working:a.working})),capacity_kw:row.diagnosis_after.capacity_kw};
};
