/* Video direction only. All displayed physical numbers come from the saved fixture. */
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
const fmt=(v,d=0)=>Math.abs(v)<1e-7?'0':Number(v).toLocaleString('en-GB',{minimumFractionDigits:d,maximumFractionDigits:d});
function selectPolicy(controller) {
    if(controller===priorController)return;
    const selector=q('[data-m=controller]');selector.value=controller;selector.dispatchEvent(new Event('change',{bubbles:true}));
    priorController=controller;
}
function detail(title,value,note,extra='') {
    q('.film-detail').innerHTML=`<div class="film-detail-label">${title}</div><div class="film-number">${value}</div><div class="film-detail-note">${note}</div>${extra}`;
}
function batteryPlot(hour) {
    const points=source.frames[story.controller].slice(0,hour+1).map((v,i)=>`${i/24*395},${88-v.battery_kwh/800*80}`).join(' ');
    return `<svg viewBox="0 0 395 92"><path d="M0 8V88H395" fill="none" stroke="#685032"/><polyline points="${points}" fill="none" stroke="#ffa32d" stroke-width="2"/></svg><div class="legend"><span>Battery · recorded history</span><span>H0 → H${hour}</span></div>`;
}
function comparison(controller) {
    const names=['Greedy','MPC · methane','MPC · economics'];
    const objectives=['Local operating rules','Plan for methane output','Plan for assumed contribution'];
    q('.film-comparison').innerHTML=names.map((name,i)=>{
        const f=source.frames[name][18];
        return `<div class="film-policy" data-selected="${name===controller}"><h2>${name}</h2><div class="objective">${objectives[i]}</div><div class="film-detail-label">Methane produced by H18</div><div class="output">${fmt(f.methane_kg,1)} <small>kg CH₄</small></div><div class="row"><span>Battery remaining</span><b>${fmt(f.battery_kwh)} kWh</b></div><div class="row"><span>Hydrogen remaining</span><b>${fmt(f.h2_kg,1)} kg</b></div><div class="row"><span>CO₂ remaining</span><b>${fmt(f.co2_kg,1)} kg</b></div></div>`;
    }).join('');
}
window.renderFilm = seconds => {
    const scene=story.scenes.find(s=>seconds>=s.start&&seconds<s.end)||story.scenes.at(-1);
    const local=seconds-scene.start, progress=clamp(local/(scene.end-scene.start));
    const controller=scene.id==='comparison'?['Greedy','MPC · methane','MPC · economics'][Math.min(2,Math.floor(local/2))]:story.controller;
    selectPolicy(controller);
    if(priorScene!==scene.id){
        filmNow=0;filmClock.seek(Math.floor(scene.hours[0]));if(scene.id!=='comparison')filmClock.play();priorScene=scene.id;
        q('.film-chapter').textContent=scene.chapter;
        q('.film-title').textContent=scene.title;
        q('.film-subtitle').textContent=scene.subtitle;
    }
    const segment=scene.segments?.find(s=>local>=s.seconds[0]&&local<s.seconds[1]);
    const at=segment?segment.hours[0]+(segment.hours[1]-segment.hours[0])*(local-segment.seconds[0])/(segment.seconds[1]-segment.seconds[0]):scene.hours[0]+(scene.hours[1]-scene.hours[0])*progress;
    filmNow=(at-scene.hours[0])*1000;
    if(filmTick)filmTick(filmNow);
    const hour=filmClock.snapshot().hour, row=source.records[controller][Math.max(0,hour-1)];
    q('.film-clock').textContent=scene.id==='comparison'?`Recorded H18 · ${controller}`:`H${String(hour).padStart(2,'0')} → H${String(hour+1).padStart(2,'0')} · ${controller}`;
    q('.film-section').innerHTML=scene.id==='cleaning'?'<strong>Solar-cleaning mission</strong> / earlier in the same run':scene.id==='comparison'?'<strong>Matched boundary</strong> / H18':scene.id==='outro'?'<strong>Explore autonomous operation</strong> / selected recorded moments':'<strong>1 MW solar</strong> / 800 kWh battery / methane plant';
    q('.film-detail').innerHTML='';q('.film-comparison').hidden=scene.id!=='comparison';
    let camera=full;
    if(scene.id==='plant')camera=mix([18,4,1244,535],full,ease(progress));
    if(scene.id==='power'){
        camera=mix(full,[-18,20,910,550],ease(local/.9));
        const energy=row.observations_after.battery_kwh, demand=row.decision.evidence.battery;
        detail('BATTERY / STORED ENERGY',`${fmt(energy)} <small>kWh</small>`,demand.planned_discharge_offsets.length?`This decision plans discharge at ${demand.planned_discharge_offsets.map(h=>'+'+h+'h').join(', ')}.`:'No discharge is planned in this decision.',batteryPlot(hour));
    }
    if(scene.id==='cleaning'){
        // Full departure path first, then an intentional camera move to the array.
        camera=mix(full,[-80,28,750,295],ease((local-1)/2.1));
        if(local>2.5)detail('SOLAR CLEANER','Routine work','A docked robot becomes a working asset.');
    }
    if(scene.id==='inspection'){
        camera=mix(full,[335,28,850,335],ease((local-1.8)/3.5));
        const diag=row.diagnosis_after;
        detail('ELECTROLYSER / ESTIMATED CAPACITY',`${fmt(diag.capacity_kw)} <small>kW</small>`,diag.status==='capacity loss'?'Capacity loss confirmed.<br>The rover checks a status contact.':'Tracking discrepancy.<br>Diagnosis still uncertain.');
    }
    if(scene.id==='repair'){
        camera=local<2?mix([390,20,1010,398],[330,20,1010,398],ease(local/2)):mix([330,20,1010,398],[300,25,760,300],ease((local-2)/2.5));
        const job=row.field_operations.state.orders.findLast(o=>o.kind==='human-service');
        detail('HUMAN SERVICE',job?.status==='awaiting verification'?'Verify next':at<18?'On the way':'Repair visit',job?.status==='awaiting verification'?'Work reported complete.<br>Recovery is still unverified.':at<18?'A specialist visit is dispatched.<br>This repair needs hands-on work.':'A technician performs the repair.<br>The observer must re-test capacity.');
    }
    if(scene.id==='comparison'){camera=full;comparison(controller);}
    if(scene.id==='outro')camera=mix([18,4,1244,535],full,ease(progress));
    svg.setAttribute('viewBox',camera.map(x=>x.toFixed(4)).join(' '));
    svg.style.opacity=scene.id==='comparison'?'.2':'1';
    q('.film-caption').style.opacity=String(scene.id==='plant'?1:ease(local/.32));
    q('.film-caption').style.transform=`translateY(${scene.id==='plant'?0:(1-ease(local/.4))*12}px)`;
    q('.film-progress i').style.transform=`scaleX(${seconds/story.duration})`;
    q('.film-counter').textContent=`${String(story.scenes.indexOf(scene)+1).padStart(2,'0')} / 07`;
    // Seek CSS poses deterministically too; plant/robot state still comes from production renderers.
    for(const animation of document.getAnimations()){
        const target=animation.effect?.target;
        const active=target&&getComputedStyle(target).animationPlayState!=='paused';
        animation.pause();
        if(active)animation.currentTime=seconds*1000;
    }
    return {scene:scene.id,controller,hour,fraction:filmClock.visualSnapshot().fraction,at,actors:fieldVisualState(source,controller,filmClock.visualSnapshot()).actors.map(a=>({asset:a.asset,phase:a.phase,x:a.x,y:a.y,working:a.working})),capacity_kw:row.diagnosis_after.capacity_kw};
};
