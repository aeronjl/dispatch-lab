/* Recorded work → schematic motion. No simulation, random paths or wall-clock timers. */
const FIELD_ROUTES = {
    rover: [[654,452],[620,416],[663,364],[678,310],[678,242],[651,213]],
    cleaner: [[705,471],[721,521],[263,521],[263,324],[234,266],[225,217],[156,181]],
    human: [[1318,379],[1190,379],[988,379],[928,377],[716,379]],
    inspection: [[651,213],[674,206],[677,180],[659,174],[651,213]],
    brush: [[156,181],[72,181],[86,159],[170,159],[179,142],[99,142],[156,181]],
    technician: [[695,379],[661,355],[396,355],[395,225],[414,207]],
};
function fieldPoint(points, progress) {
    if(progress>=1){const p=points.at(-1),a=points.at(-2)||p;return {x:p[0],y:p[1],heading:p[0]<a[0]?-1:1};}
    const lengths=points.slice(1).map((p,i)=>Math.hypot(p[0]-points[i][0],p[1]-points[i][1]));
    let distance=Math.max(0,Math.min(1,progress))*lengths.reduce((a,b)=>a+b,0);
    for(let i=0;i<lengths.length;i++){
        if(distance<=lengths[i]||i===lengths.length-1){
            const t=lengths[i]?distance/lengths[i]:0,a=points[i],b=points[i+1];
            return {x:a[0]+(b[0]-a[0])*t,y:a[1]+(b[1]-a[1])*t,heading:b[0]<a[0]?-1:1};
        }
        distance-=lengths[i];
    }
    return {x:points[0][0],y:points[0][1],heading:1};
}
function fieldBegin(row){return row?.decision?.field_operations || row?.field_operations?.decision;}
function fieldVisualState(result, controller, clock) {
    const config=result.config?.field_operations, rows=result.records?.[controller]||[];
    if(!config?.enabled||!rows[0]?.field_operations)return {enabled:false,actors:[]};
    const hour=Math.max(0,Math.min(rows.length,clock.hour)),fraction=Math.max(0,Math.min(.999999,clock.fraction||0));
    const underway=(clock.playing||fraction>0)&&hour<rows.length;
    const after=hour?rows[hour-1]?.field_operations?.state:null;
    // Only the current interval's *beginning* work orders may animate before completion.
    const state=(underway?fieldBegin(rows[hour]):after)||{orders:[],robots:{},surface:fieldBegin(rows[0])?.surface};
    if(state.implementation_id==='plant-service-contracts/1'||result.config?.service_system?.implementation==='plant-service-contracts/1')
        return fractionalFieldVisualState(result,state,{hour,fraction,underway});
    const actors=[];
    for(const [asset,kind] of [['rover','inspection'],['cleaner','cleaning'],['human','human-service'],['reset','reset']]){
        const orders=state.orders?.filter(o=>o.kind===kind)||[];
        const order=orders.findLast(o=>o.status==='active')||orders.at(-1);
        if(asset==='rover'&&!config.rover_enabled||asset==='cleaner'&&!config.cleaner_enabled)continue;
        if((asset==='human'||asset==='reset')&&!order)continue;
        let progress=0;
        if(order?.status==='active'){
            let duration=order.remaining;
            for(let i=hour-1;i>=0;i--){
                const prior=fieldBegin(rows[i])?.orders?.find(o=>o.id===order.id);
                if(prior?.status!=='active'||prior.phase!==order.phase)break;
                duration=prior.remaining;
            }
            progress=duration>0?1-(order.remaining-(underway?fraction:0))/duration:0;
        }
        const active=order?.status==='active', failed=order?.status==='failed';
        const phase=failed?(asset==='rover'||asset==='cleaner'?'stranded':'failed'):active?order.phase:order?.status==='awaiting verification'?'awaiting verification':order?.status==='verified'?'verified':order?.status==='queued'||order?.status==='blocked'?'queued':'docked';
        let route=FIELD_ROUTES[asset], pose=route?fieldPoint(route,0):{x:622,y:194,heading:1};
        let working=false,walking=false, visible=true;
        if(asset==='rover'||asset==='cleaner'){
            if(phase==='travel')pose=fieldPoint(route,progress);
            else if(phase==='return')pose=fieldPoint([...route].reverse(),progress);
            else if(['perform','verify','stranded'].includes(phase)){
                const work=FIELD_ROUTES[asset==='rover'?'inspection':'brush'];
                pose=fieldPoint(work,phase==='perform'?progress:1);
                working=phase==='perform'||phase==='verify';
            }
        } else if(asset==='human') {
            if(phase==='travel')pose=fieldPoint(route,progress);
            else if(phase==='queued'){visible=false;}
            else pose=fieldPoint(route,1);
            // Walking, opening a tool case and ratcheting are illustrative subposes
            // of the recorded hands-on interval, not additional simulated activities.
            walking=phase==='perform'&&progress<.25;
            working=phase==='perform'&&progress>=.25;
        } else {
            visible=phase!=='queued'; working=phase==='perform';
        }
        actors.push({asset,kind,order:order?.id||null,phase,progress,...pose,visible,working,walking,failed,
            moving:active&&['travel','return'].includes(phase),
            energy:state.robots?.[asset]?.energy_kwh,
            charging:phase==='docked'&&(rows[Math.max(0,hour-1)]?.field_operations?.charge_input_kwh||0)>0});
    }
    return {enabled:true,actors,underway,hour,fraction,clock:hour+fraction,
        dock:config.rover_enabled||config.cleaner_enabled, reduced:false};
}


function fieldSectionBrush(section) {
    const index=Number(String(section).slice(-2))-1;
    if(!Number.isInteger(index)||index<0||index>2)return FIELD_ROUTES.brush;
    return [[.2,.82],[.8,.82],[.8,.5],[.2,.5],[.2,.18],[.8,.18],[.2,.82]].map(([u,v])=>[67+144*(index+u)/3-34*v,132+64*v]);
}
function fieldRecoveryPoint(order,orders=[],depth=0) {
    const loc=order.recovery_location||{},name=order.robot,base=FIELD_ROUTES[name]||FIELD_ROUTES.cleaner;
    if(depth<8&&loc.phase==='return'&&loc.from_point?.startsWith('recovery/')){
        const previous=orders.find(q=>q.id===order.origin_order);
        if(previous?.kind==='guided-return')return fieldPoint(fieldGuidedPath(previous,orders,depth+1),loc.progress||0);
    }
    const sweep=name==='cleaner'?fieldSectionBrush(order.recovery_section):FIELD_ROUTES.inspection;
    const route=name==='cleaner'&&order.recovery_section?[...base.slice(0,-1),sweep[0]]:base;
    return fieldPoint(loc.phase==='travel'?route:loc.phase==='return'?[...route].reverse():sweep,loc.progress||0);
}
function fieldGuidedPath(order,orders,depth=0){
    const start=fieldRecoveryPoint(order,orders,depth),base=FIELD_ROUTES[order.robot]||FIELD_ROUTES.cleaner;
    return [[start.x,start.y],...base.slice(0,-1).reverse()];
}
function fieldSupportGeometry(order,span,progress,orders=[],hardware=false) {
    if(order.kind==='crew-return')return fieldCrewReturnGeometry(order,span,progress,orders,hardware);
    const portable=order.kind==='portable-cleaning',packing=order.kind==='pack-return',bench=order.robot==='portable'&&['hardware-test','hardware-replacement'].includes(order.kind);
    const gate=hardware?[1190,480]:[1318,379],dock=order.kind==='routine-service'?[715,528]:[762,480],park=order.robot==='cleaner'||portable||packing?[263,324]:[716,379];
    const road=(a,b)=>[a,[a[0],521],[b[0],521],b];
    const recovery=fieldRecoveryPoint(order,orders),from=span?.from_point||'site-gate',to=span?.to_point||'site-gate';
    const location=p=>p==='site-gate'?gate:p==='dock'?dock:p.startsWith('recovery/')||p==='solar'?park:[716,379];
    const collecting=order.kind==='retrieve'&&from.startsWith('recovery/')&&to==='dock';
    const travelProgress=collecting?Math.max(0,(progress-.25)/.75):progress;
    const pose=fieldPoint(from===to?[location(from),location(from)]:road(location(from),location(to)),travelProgress);
    let passenger=null,technician=null;
    if(order.kind==='retrieve'){
        if(from.startsWith('recovery/')&&to==='dock'){
            const pickup=[recovery.x,recovery.y],bed=[park[0]-94,park[1]-5],path=order.robot==='cleaner'?[pickup,[225,217],[234,266],bed]:[pickup,bed];
            passenger=progress<.25?fieldPoint(path,progress/.25):{x:pose.x-pose.heading*94,y:pose.y-5,heading:pose.heading};
        }else if(from==='dock')passenger=span?.phase==='perform'?fieldPoint([[dock[0]-94,dock[1]-5],[705,471]],progress):{x:705,y:471,heading:1};
        if(span?.phase==='prepare')technician={x:recovery.x+24,y:recovery.y+11,heading:1};
    }
    if(span?.phase==='perform')technician={x:717,y:480,heading:1};
    const plantWork=(order.visit_id&&['module-replacement','flow-calibration'].includes(order.kind))||(order.kind==='routine-service'&&['fixed_reader','reset'].includes(order.target));
    const walking=plantWork&&span?.phase==='perform'&&progress<.25;
    if(plantWork&&['perform','verify'].includes(span?.phase))technician=fieldPoint(FIELD_ROUTES.technician,walking?progress/.25:1);
    let toolTarget=null;
    if(portable&&['prepare','perform','verify'].includes(span?.phase)){
        technician={x:238,y:234,heading:1};
        if(span.phase==='perform')toolTarget=fieldPoint(fieldSectionBrush(order.section),progress);
    }
    let toolPosition=null;
    if(packing&&span?.phase==='prepare'){technician={x:322,y:269,heading:1};toolPosition={x:358,y:255};}
    if(bench&&span?.phase==='perform'){technician={x:gate[0]-65,y:gate[1]+15,heading:1};toolPosition={x:gate[0]-20,y:gate[1]+15};}
    if(packing&&span?.phase==='perform')technician=null;
    return {...pose,passenger,technician,toolTarget,toolPosition,packing:packing||bench,walking,technicianFacing:plantWork||packing||bench?1:-1,portableWork:(portable||packing||bench)&&!!technician,wet:portable&&order.method==='portable-wet',loading:collecting&&progress<.25,towing:!!passenger&&collecting&&progress>=.25};
}
function fieldCrewReturnGeometry(order,span,progress,orders,hardware,depth=0) {
    const gate=hardware?[1190,480]:[1318,379],dock=[762,480],solar=[263,324],ely=[716,379];
    const previous=orders.find(q=>q.id===order.origin_order),loc=order.recovery_location||{};
    let initial={x:gate[0],y:gate[1],heading:1};
    if(previous&&depth<16){
        if(previous.kind==='crew-return')initial=fieldCrewReturnGeometry(previous,loc,loc.progress||0,orders,hardware,depth+1);
        else if(previous.visit_id||!['module-replacement','flow-calibration'].includes(previous.kind))initial=fieldSupportGeometry(previous,loc,loc.progress||0,orders,hardware);
        else initial=fieldPoint(FIELD_ROUTES.human,loc.phase==='travel'?loc.progress||0:loc.phase==='return'?1-(loc.progress||0):1);
    }
    const location=p=>p==='site-gate'?gate:p==='solar'?solar:p==='dock'?dock:p?.startsWith('recovery/')?[initial.x,initial.y]:ely;
    const a=location(span?.from_point),b=location(span?.to_point);
    let root=previous;for(let i=0;i<16&&root?.kind==='crew-return';i++)root=orders.find(q=>q.id===root.origin_order);
    const road=root&&!root.visit_id&&['module-replacement','flow-calibration'].includes(root.kind)?[a,b]:[a,[a[0],521],[b[0],521],b];
    const pose=span?.phase==='prepare'?initial:fieldPoint(a[0]===b[0]&&a[1]===b[1]?[a,a]:road,progress);
    return {...pose,technician:span?.phase==='prepare'?{x:pose.x-45,y:pose.y,heading:1}:null,
        technicianFacing:1,packing:order.robot==='portable',portableWork:order.robot==='portable'&&span?.phase==='prepare',walking:false,loading:false,towing:false};
}
// Fractional service schedules are supplied by Python. Interpolate their recorded
// time spans; do not infer repair success from a working pose or later plant truth.
function fractionalFieldVisualState(result,state,{hour,fraction,underway}) {
    const config=result.config.field_operations,options=result.config.service_system,at=hour+(underway?fraction:0);
    const hardwareKinds=['remote-release','hardware-test','guided-return'];
    const definitions=[['cleaner',['cleaning','self-test',...hardwareKinds]],['rover',['inspection','inspection-confirm','self-test',...hardwareKinds]],['fixed_reader',['inspection']],['human',['module-replacement','flow-calibration','retrieve','restock','replace-brush','routine-service','portable-cleaning','hardware-replacement','pack-return','hardware-test','crew-return']],['reset',['reset']]];
    const actors=[];
    for(const [asset,kinds] of definitions){
        if(asset==='cleaner'&&!config.cleaner_enabled||asset==='rover'&&(!config.rover_enabled||!['mobile','both'].includes(options.inspector))||asset==='fixed_reader'&&!['fixed','both'].includes(options.inspector))continue;
        const orders=(state.orders||[]).filter(o=>kinds.includes(o.kind)&&(o.kind!=='self-test'||o.robot===asset)&&(!hardwareKinds.includes(o.kind)||(asset==='human'?o.robot==='portable':o.robot===asset))&&(asset!=='rover'||o.reader!=='fixed')&&(asset!=='fixed_reader'||o.reader!=='mobile'));
        const dispatched=orders.filter(o=>o.started_hour!==undefined).sort((a,b)=>a.started_hour-b.started_hour||a.sequence-b.sequence);
        const executing=underway?orders.findLast(o=>(state.planned_missions||[]).some(p=>p.order.order_id===o.id&&p.timeline.some(s=>s.start<=at&&at<s.end))):null;
        const stranded=orders.findLast(o=>o.retrieved_at===undefined&&state.executive?.orders.some(m=>m.order_id===o.id&&(m.status==='stranded'||o.kind==='crew-return'&&m.status==='blocked')));
        const order=executing||orders.findLast(o=>o.status==='active'&&(o.started_hour??0)<=at)||stranded||dispatched.filter(o=>o.started_hour<=at).at(-1)||orders.at(-1);
        if(['human','reset'].includes(asset)&&!order)continue;
        const plan=(state.planned_missions||[]).find(m=>m.order.order_id===order?.id);
        const segment=underway&&plan?.timeline?.find(s=>s.start<=at&&at<s.end);
        const info=state.executive?.orders.find(o=>o.order_id===order?.id);
        let phase=segment?.phase||info?.phase||'docked',progress=segment?(at-segment.start)/(segment.end-segment.start):(info?.progress||0);
        let failed=info?.status==='stranded'||info?.status==='blocked'||info?.status==='invalid';
        if(!segment&&underway&&plan&&plan.timeline.at(-1).end<=at){phase='docked';progress=1;}
        else if(failed){phase=info.status==='stranded'||order.kind==='crew-return'&&info.status==='blocked'?'stranded':'failed';progress=info.progress||0;}
        else if(!info||order?.status==='queued'||order?.started_hour>at)phase=order?'queued':'docked';
        else if(!['scheduled','active'].includes(info.status))phase='docked';
        if(order?.retrieved_at!==undefined&&order.retrieved_at<=hour){phase='docked';progress=1;failed=false;}
        let pose={x:asset==='fixed_reader'?606:622,y:asset==='fixed_reader'?153:194,heading:1},visible=true,working=false,walking=false;
        const sectionBrush=asset==='cleaner'&&order?.section?fieldSectionBrush(order.section):null;
        const route=sectionBrush?[...FIELD_ROUTES.cleaner.slice(0,-1),sectionBrush[0]]:FIELD_ROUTES[asset];
        if(route){
            pose=fieldPoint(route,0);
            const locationPhase=phase==='stranded'?info?.phase:phase;
            if(locationPhase==='travel')pose=fieldPoint(route,progress);
            else if(locationPhase==='return')pose=fieldPoint([...route].reverse(),progress);
            else if(['perform','verify','prepare','stranded'].includes(phase)){
                const path=asset==='human'?route:sectionBrush||FIELD_ROUTES[asset==='rover'?'inspection':'brush'];
                pose=fieldPoint(path,asset==='human'?1:phase==='perform'||(phase==='stranded'&&locationPhase==='perform')?progress:1);
            }
        }
        working=['perform','verify'].includes(phase);
        if(order?.kind==='self-test'){pose=fieldPoint(FIELD_ROUTES[asset],0);working=false;}
        if(hardwareKinds.includes(order?.kind)&&asset!=='human'){
            const field=order.equipment_step==='release'||order.equipment_step==='field-probe';
            pose=field?fieldRecoveryPoint(order,state.orders):fieldPoint(FIELD_ROUTES[asset],0);
            if(order.kind==='guided-return')pose=fieldPoint(fieldGuidedPath(order,state.orders),phase==='docked'?1:(segment?.phase||info?.phase)==='return'?progress:1);
            working=false; // A requested test does not imply observed successful motion.
        }
        if(asset==='human'){
            visible=!['queued','docked','failed'].includes(phase);
            walking=phase==='perform'&&progress<.25;
            working=phase==='perform'&&progress>=.25;
        }
        let supportGeometry=null;
        if(asset==='human'&&(order?.visit_id||['retrieve','restock','replace-brush','routine-service','portable-cleaning','hardware-replacement','pack-return','hardware-test','crew-return'].includes(order?.kind))){
            supportGeometry=fieldSupportGeometry(order,segment||info,progress,state.orders,options.equipment_recovery_enabled);
            pose=supportGeometry;walking=phase==='perform'&&!!supportGeometry.walking;working=['prepare','perform'].includes(phase)&&!walking;
            if(order.kind==='crew-return'){walking=false;working=phase==='prepare';}
        }
        actors.push({asset,kind:order?.kind||kinds[0],order:order?.id||null,phase,progress,...pose,visible,working,walking,failed,
                     moving:['travel','return'].includes(phase)&&!supportGeometry?.loading,testing:hardwareKinds.includes(order?.kind)&&phase==='perform',energy:state.robots?.[asset]?.energy_kwh,charging:false,
                     ...(supportGeometry?{support:true,recoveryRobot:order.robot}:{} )});
    }
    const recovery=actors.find(a=>a.asset==='human'&&a.kind==='retrieve'&&a.visible&&a.passenger);
    if(recovery){const robot=actors.find(a=>a.asset===recovery.recoveryRobot);if(robot&&(recovery.towing||recovery.phase==='perform'||robot.phase==='stranded'))Object.assign(robot,recovery.passenger,{phase:'retrieval',failed:false,working:false,moving:false});}
    return {enabled:true,actors,underway,hour,fraction,surface:state.surface,clock:at,dock:config.cleaner_enabled||(config.rover_enabled&&['mobile','both'].includes(options.inspector)),hardware:state.support?.equipment,standby:state.standby,inspectionInterface:state.inspection_interface,reduced:false};
}

function createFieldScene({root,getResult,getController,inspect}) {
    const ns='http://www.w3.org/2000/svg', layer=document.createElementNS(ns,'g');
    layer.classList.add('field-world');layer.setAttribute('aria-label','Site service hardware');
    // Append a separate layer. Every original equipment path and label stays intact.
    root.querySelector('.m-plant').append(layer);
    const wheels=(xs,y,r=5)=>xs.map(x=>`<g class="f-wheel" data-wheel-center="${x},${y}"><circle cx="${x}" cy="${y}" r="${r}"/><path d="M${x-r+1} ${y}H${x+r-1}M${x} ${y-r+1}V${y+r-1}"/></g>`).join('');
    layer.innerHTML=`
    <g class="f-surface" aria-hidden="true" pointer-events="none"></g>
    <g class="f-routes" aria-hidden="true">
        <path data-route="rover" d="${FIELD_ROUTES.rover.map((p,i)=>(i?'L':'M')+p.join(' ')).join('')}"/>
        <path data-route="cleaner" d="${FIELD_ROUTES.cleaner.map((p,i)=>(i?'L':'M')+p.join(' ')).join('')}"/>
        <path data-route="human" d="${FIELD_ROUTES.human.map((p,i)=>(i?'L':'M')+p.join(' ')).join('')}"/>
    </g>
    <g class="f-dock f-interactive" data-field-inspect="dock" role="button" tabindex="0" aria-label="Inspect service dock" transform="translate(675 449)">
      <title>Service dock · select to inspect work and charging</title>
      <path class="f-pad" d="M-51 26L-18 7H60L27 26ZM-51 26V29H27L60 10V7M27 26V29"/>
      <path class="f-shell" d="M7-32H35V6H7ZM7-32L20-40H48L35-32M35-32L48-40V-2L35 6"/>
      <path class="f-detail" d="M12-25H29V-15H12ZM14-10H27M14-6H27M41-28V-17M41-11V-6M15-37H37"/>
      <path class="f-light" d="M16-21H25M22-23V-18"/>
      <path class="f-cable" d="M10-2H-3V9L-13 15M30 4V13L17 20"/>
      <path class="f-pad-mark" d="M-34 21L-20 13H-9M2 21L17 13H28"/>
      <path class="f-focus" d="M-55 33V-44H53V33Z"/>
    </g>
    <g class="f-access-ramp" aria-hidden="true"><path class="f-pad" d="M212 219L228 210L179 186L165 196ZM212 219V222L228 213V210M212 219L165 196"/><path class="f-detail" d="M204 215L220 206M195 211L211 202M186 207L202 198M177 202L193 193"/></g>
    <g class="f-inspection-light" aria-hidden="true"><path class="f-scan-fill"/><path class="f-scan-line"/></g>
    <g class="f-actor f-rover f-interactive" data-field-inspect="rover" role="button" tabindex="0">
      <title>Inspection rover</title>
      <ellipse class="f-shadow" cx="0" cy="3" rx="29" ry="8"/>
      <g class="f-orientation">
       <g class="f-suspension">
        <path class="f-shell" d="M-25-11H13L27-19V-9L13 0H-25ZM-25-11L-12-20H27L13-11M13-11V0"/>
        <path class="f-deck" d="M-21-14L-10-24H15L23-19L10-10H-21Z"/>
        <path class="f-detail" d="M-15-16H6M-11-20H11M-21-6H-13M-8-6H0M5-6H10M20-13L24-15"/>
        <path class="f-light" d="M23-18V-14M-21-8V-5"/>
        <g class="f-arm"><path class="f-arm-back"/><path class="f-arm-front"/><circle class="f-elbow" r="2.8"/><circle cx="0" cy="-21" r="3"/>
         <g class="f-camera"><path class="f-shell" d="M-7-4H6V4H-7ZM6-4L10-7V1L6 4M-7-4L-3-7H10"/><circle cx="-3" r="2.2"/><path class="f-light" d="M3-2V2"/></g>
        </g>
        <path class="f-detail" d="M-15-23V-33M-17-33H-13"/>
       </g>
       ${wheels([-18,-3,12],0,5)}${wheels([24],-8,4)}
      </g><path class="f-focus" d="M-34 13V-61H36V13Z"/>
      <g class="f-alert"><path d="M0-65L5-55H-5Z"/><path d="M0-62V-59M0-57V-56"/></g>
    </g>
    <g class="f-recovery-trailer" aria-hidden="true"><path class="f-shell" d="M-32-5H28V1H-32ZM-32-5L-22-12H38L28-5M28-5L38-12V-6L28 1M28 0H45L55-4"/><path class="f-detail" d="M-24-6V-15M23-6V-15"/>${wheels([-20,20],3,5)}</g>
    <g class="f-actor f-cleaner f-interactive" data-field-inspect="cleaner" role="button" tabindex="0">
      <title>Solar cleaner</title><ellipse class="f-shadow" cx="0" cy="4" rx="26" ry="6"/>
      <g class="f-orientation">
       <path class="f-track" d="M-23-5H17V4H-23ZM-23-5L-16-11H24V-2L17 4M17-5L24-11"/>
       <path class="f-tread" d="M-20-3V2M-15-3V2M-10-3V2M-5-3V2M0-3V2M5-3V2M10-3V2M15-3V2"/>
       <path class="f-shell" d="M-19-9L-11-20H16L23-13L15-3H-19ZM-11-20L-2-25H25L32-18L23-13M23-13L32-18V-10L25-5L15-3"/>
       <path class="f-detail" d="M-7-17H10M-9-13H8M-11-9H6M15-18L21-14M1-23H19"/>
       <g class="f-brush"><path class="f-shell" d="M-26-4L-18-17H-13L-21-4Z"/><path class="f-bristles" d="M-28-4L-19-19M-24-3L-15-18M-21-5L-17-12"/></g>
       <path class="f-light" d="M15-9H20"/>
      </g><path class="f-focus" d="M-34 13V-34H39V13Z"/>
      <g class="f-alert"><path d="M0-43L5-33H-5Z"/><path d="M0-40V-37M0-35V-34"/></g>
    </g>
    <g class="f-cleaning-dust" aria-hidden="true"><path d="M-4 0H-1M2-3H4M-7 4H-5M0 6H2"/></g>

    <g class="f-actor f-human f-interactive" data-field-inspect="human" role="button" tabindex="0">
      <title>Human service vehicle</title><ellipse class="f-shadow" cx="0" cy="4" rx="43" ry="9"/>
      <g class="f-orientation">
       <path class="f-shell" d="M-39-9V-29H4L15-19H29L39-8V1H-39ZM-39-29L-25-37H17L29-27V-19M4-29L17-37M15-19L29-27L42-16V-6L39-3"/>
       <path class="f-window" d="M5-25L14-15H27L20-25ZM-34-24H-3V-14H-34"/>
       <path class="f-detail" d="M-36-10H3M-36-6H3M-1-27V-2M14-12V-2M17-10H21M31-6H37M-32-33H6"/>
       <path class="f-light" d="M35-5V-1M-38-5V-1"/>
       <path class="f-shell" d="M-24-38H-1L5-42H-18ZM-24-38V-35H-1L5-39V-42M-1-38V-35"/>
       ${wheels([-24,25],1,7)}${wheels([38],-6,5)}
      </g><path class="f-focus" d="M-46 13V-49H48V13Z"/>
    </g>
    <g class="f-technician f-interactive" data-field-inspect="human" role="button" tabindex="-1">
      <title>Qualified service · module replacement and flow calibration</title>
      <ellipse class="f-shadow" cx="0" cy="2" rx="12" ry="4"/>
      <g class="f-person"><path class="f-limbs f-legs"/>
       <path class="f-shell" d="M-6-29L2-31L8-26L6-12H-5L-8-23Z"/>
       <path class="f-detail" d="M-5-25L1-17L5-26M-4-15H5"/>
       <path class="f-shell" d="M-4-31V-37L0-40L5-37V-31L1-28Z"/><path class="f-helmet" d="M-6-36Q-6-43 0-43Q7-43 8-36ZM-8-36H10"/>
       <path class="f-limbs f-hands"/><g class="f-tool"><path d="M0 0L8-8M5-11L5-7L9-7L11-10M-2-1L1 2"/></g>
      </g><path class="f-focus" d="M-17 8V-48H35V8Z"/>
    </g>
    <g class="f-toolcase" aria-hidden="true"><path class="f-shell" d="M0 0H20V12H0ZM0 0L7-5H27V7L20 12M20 0L27-5M7-5V-10H21V-5"/><path d="M4 5H16M10 2V8"/></g>
    <g class="f-portable f-interactive" data-field-inspect="portable" role="button" tabindex="0" aria-label="Inspect portable cleaning equipment">
      <title>Portable cleaning equipment · operator, pump and finite water</title>
      <path class="f-shell" d="M-20-5V-34H6L16-27V-5ZM-20-34L-12-40H14L23-33V-11L16-5M6-34L14-40M6-34V-7"/>
      <path class="f-detail" d="M-16-29H1V-21H-16ZM-14-15H1M-14-11H1M11-29V-12M-10-39V-45H5V-39"/>
      <circle class="f-light" cx="-7" cy="-25" r="2"/>
      <path class="f-shell" d="M-25-4H21V1H-25M20-4L28-11H31V-25M31-25H38"/>
      <path class="f-cable" d="M15-21C35-21 36-7 23-7C13-7 13-17 23-17C31-17 30-10 24-10"/>
      ${wheels([-15,15],2,5)}
      <path class="f-focus" d="M-30 12V-50H42V12Z"/>
    </g>
    <g class="f-portable-lines" aria-hidden="true"><path class="f-portable-hose f-cable"/><path class="f-portable-lance"/><path class="f-portable-brush f-bristles"/><path class="f-portable-spray"/></g>
    <g class="f-contact-interface f-interactive" data-field-inspect="rover" role="button" tabindex="0" transform="translate(656 175)" style="display:none">
      <title>Contact inspection interface</title>
      <path class="f-shell" d="M-7-13H7V12H-7ZM-7-13L-2-16H12V9L7 12M7-13L12-16"/>
      <g class="f-contact-prepared"><circle cx="0" cy="-2" r="4"/><path class="f-detail" d="M-2-2H2M0-4V0M-4 7H4M-11-9L-15-7V8L-11 10Z"/></g>
      <g class="f-contact-enclosed"><path class="f-detail" d="M-4-10H4V9H-4M2-3V2M-5-11L-3-9M3 7L5 9"/></g>
      <path class="f-focus" d="M-18 17V-20H17V17Z"/>
    </g>
    <g class="f-actor f-fixed_reader f-interactive" data-field-inspect="fixed_reader" role="button" tabindex="0" transform="translate(606 153)">
      <title>Fixed trip-contact reader</title>
      <path class="f-shell" d="M-9-13H9V12H-9ZM-9-13L-3-17H15V8L9 12M9-13L15-17"/>
      <path class="f-detail" d="M-5-8H5V0H-5ZM-5 5H5M-5 8H5M-4 12V19H7"/>
      <circle class="f-light" cx="0" cy="-4" r="1.5"/>
      <path class="f-focus" d="M-14 22V-22H20V22Z"/>
    </g>
    <g class="f-actor f-reset f-interactive" data-field-inspect="reset" role="button" tabindex="0" transform="translate(622 194)">
      <title>Isolated module reset actuator</title>
      <path class="f-shell" d="M-8-12H11V11H-8ZM-8-12L-1-17H18V6L11 11M11-12L18-17"/>
      <path class="f-detail" d="M-4 6H6M-4-7H6"/><circle cx="2" cy="-1" r="4"/>
      <path class="f-reset-lever" d="M2-1V-10"/><path class="f-light" d="M13-8V-3"/>
      <path class="f-focus" d="M-14 17V-23H23V17Z"/>
    </g>`;
    const q=s=>layer.querySelector(s), nodes={};
    for(const asset of ['rover','cleaner','human','reset','fixed_reader'])nodes[asset]=q('.f-'+asset);
    let lastKey='', lastSurface='', lastClock=null, lastVisual=null, disposed=false;
    const reduced=matchMedia('(prefers-reduced-motion: reduce)');
    const set=(node,key,value)=>node?.setAttribute(key,value);
    const position=(node,x,y)=>set(node,'transform',`translate(${x.toFixed(3)} ${y.toFixed(3)})`);
    function render(clock) {
        if(disposed)return;lastClock=clock;
        const result=getResult(), controller=getController();
        // Reduced motion uses a static pose at each completed boundary.
        const sample=reduced.matches?{...clock,fraction:0,playing:false}:clock;
        const key=[result.run_id,controller,sample.hour,sample.fraction,sample.playing,reduced.matches].join('|');
        if(key===lastKey)return;lastKey=key;
        const v=fieldVisualState(result,controller,sample);lastVisual=v;
        layer.style.display=v.enabled?'':'none';if(!v.enabled)return;
        set(layer,'data-interval',v.hour);set(layer,'data-underway',v.underway);
        q('.f-dock').style.display=v.dock?'':'none';
        q('.f-dock .f-light').style.opacity=v.standby&&!v.standby.control_available?'.15':'';
        const dockIncident=v.hardware?.incidents.find(e=>e.target==='dock');
        set(q('.f-dock'),'data-failed',!!dockIncident&&dockIncident.state!=='ready');
        const port=q('.f-contact-interface');port.style.display=v.inspectionInterface?'':'none';
        if(v.inspectionInterface){const accessible=v.inspectionInterface.accessible;q('.f-contact-prepared').style.display=accessible?'':'none';q('.f-contact-enclosed').style.display=accessible?'none':'';set(port,'aria-label',(accessible?'Prepared contact test port':'Enclosed contact; installed reader cannot access')+'. Select to inspect.');}
        const surface=v.surface?.sections||[];
        const surfaceKey=JSON.stringify(surface);
        if(surfaceKey!==lastSurface){lastSurface=surfaceKey;q('.f-surface').innerHTML=surface.map(section=>{
            const index=Number(section.id.slice(-2))-1;
            const area=section.area_m2||1;
            return (section.patches||[]).map(p=>{
                const left=index/3+p.start_m2/area/3,width=(p.end_m2-p.start_m2)/area/3;
                return Array.from({length:Math.round((p.removable+p.adhered)*120*(p.end_m2-p.start_m2)/area)},(_,i)=>{
                    const u=left+width*((i*37+17)%97)/97,v=((i*23+9)%89)/89;
                    return `<rect x="${67+144*u-34*v}" y="${132+64*v}" width="1.5" height="1.5" fill="#cdb47d" opacity=".6"/>`;
                }).join('');
            }).join('');
        }).join('');
        }
        q('.f-access-ramp').style.display=v.actors.some(a=>a.asset==='cleaner'&&a.phase!=='docked'&&a.phase!=='queued')?'':'none';
        q('.f-inspection-light').style.display='none';q('.f-cleaning-dust').style.display='none';
        q('.f-technician').style.display='none';q('.f-toolcase').style.display='none';q('.f-recovery-trailer').style.display='none';q('.f-portable').style.display='none';q('.f-portable-lines').style.display='none';q('.f-tool').style.display='';
        for(const node of Object.values(nodes))node.style.display='none';
        const t=reduced.matches?0:v.clock;
        for(const a of v.actors){
            const node=nodes[a.asset];node.style.display=a.visible?'':'none';if(!a.visible)continue;
            position(node,a.x,a.y);set(node,'data-phase',a.phase);set(node,'data-moving',a.moving);set(node,'data-working',a.working);set(node,'data-failed',a.failed);set(node,'data-order',a.order||'');
            node.querySelectorAll('.f-light').forEach(l=>{l.style.opacity=a.testing?String(reduced.matches ? .65 : .5+.3*Math.sin(t*18)):'';});
            const label=`${{rover:'Inspection rover',cleaner:'Solar cleaner',human:'Human service vehicle',reset:'Module reset actuator',fixed_reader:'Fixed contact reader'}[a.asset]} · ${a.phase}${a.order?' · '+a.order:''}. Select to inspect.`;
            set(node,'aria-label',label);const title=node.querySelector('title');if(title.textContent!==label)title.textContent=label;
            // Rotation uses recorded elapsed time, so pausing and speed changes stay exact.
            node.querySelectorAll('.f-wheel').forEach(w=>{const [x,y]=w.dataset.wheelCenter.split(',');set(w,'transform',`rotate(${a.moving?t*900:0} ${x} ${y})`);});
            const orient=node.querySelector('.f-orientation');
            if(orient)set(orient,'transform',`scale(${a.moving?a.heading:1} 1)`);
            const bounce=a.moving&&!reduced.matches?Math.sin(t*50)*.5:0;
            if(a.asset==='rover'){
                set(q('.f-suspension'),'transform',`translate(0 ${bounce})`);
                const reach=a.working?1:0, sway=a.working?Math.sin(t*9):0;
                const elbow=[-5-8*reach,-32-9*reach],camera=[-4-18*reach,-43-9*reach+sway*3];
                set(q('.f-arm-back'),'d',`M0-21L${elbow}L${camera}`);set(q('.f-arm-front'),'d',`M3-22L${elbow[0]+3} ${elbow[1]}L${camera[0]+3} ${camera[1]}`);
                position(q('.f-elbow'),...elbow);position(q('.f-camera'),...camera);
                if(a.working){q('.f-inspection-light').style.display='';const y=151+sway*13;set(q('.f-scan-fill'),'d',`M${a.x+camera[0]} ${a.y+camera[1]}L605 ${y-13}V${y+13}Z`);set(q('.f-scan-line'),'d',`M${a.x+camera[0]} ${a.y+camera[1]}L605 ${y}`);}
            }
            if(a.asset==='cleaner'){
                set(q('.f-brush'),'transform',`translate(${a.working?Math.sin(t*70)*1.2:0} 0)`);
                set(q('.f-tread'),'stroke-dashoffset',a.moving||a.working?-t*12:0);
                if(a.phase==='perform'&&a.kind==='cleaning'){const dust=q('.f-cleaning-dust');dust.style.display='';position(dust,a.x-27,a.y+2);set(dust,'opacity',.25+.25*(1+Math.sin(t*21))/2);}
            }
            if(a.asset==='human'&&a.towing){const trailer=q('.f-recovery-trailer');trailer.style.display='';set(trailer,'transform',`translate(${a.x-a.heading*94} ${a.y+1}) scale(${a.heading} 1)`);}
            if(a.asset==='human'&&(a.technician||!a.support&&['perform','verify','awaiting verification','verified'].includes(a.phase))){
                const tech=q('.f-technician');tech.style.display='';
                const walking=a.walking, pos=a.technician||fieldPoint(FIELD_ROUTES.technician,walking?a.progress/.25:1);
                position(tech,pos.x,pos.y);set(tech,'data-phase',a.phase);
                set(q('.f-person'),'transform',a.support&&a.technicianFacing!==1?'scale(-1 1)':'');
                const gait=walking&&!reduced.matches?Math.sin(t*30)*5:0;
                set(q('.f-legs'),'d',`M-3-12L${-4+gait} -5L${-6+gait} 0H${-1+gait}M4-12L${5-gait} -5L${7-gait} 0H${11-gait}`);
                const work=a.working, hand=[work?36:9,work?-26+Math.sin(t*18)*2:-14];
                set(q('.f-hands'),'d',`M6-26L15-20L${hand}M-5-25L-10-17L${work?15:-5} -13`);
                const tool=q('.f-tool');set(tool,'transform',`translate(${hand}) rotate(${work?Math.sin(t*18)*22:60})`);
                q('.f-toolcase').style.display='';position(q('.f-toolcase'),a.support?pos.x+20:430,a.support?pos.y:213);
                if(a.portableWork){
                    q('.f-tool').style.display='none';q('.f-toolcase').style.display='none';
                    const cart=q('.f-portable');cart.style.display='';position(cart,a.toolPosition?.x??358,a.toolPosition?.y??255);set(cart,'data-order',a.order);set(cart,'data-phase',a.phase);set(cart,'data-wet',a.wet);
                    q('.f-portable-lines').style.display=a.packing?'none':'';
                    const grip=[pos.x-hand[0],pos.y+hand[1]];
                    set(q('.f-portable-hose'),'d',`M373 237Q401 253 372 265T314 238Q264 244 ${grip}`);
                    const target=a.toolTarget||{x:218,y:202};
                    set(q('.f-portable-lance'),'d',`M${grip}L${target.x} ${target.y}`);
                    set(q('.f-portable-brush'),'d',`M${target.x-10} ${target.y+1}L${target.x+7} ${target.y+1}M${target.x-8} ${target.y+1}V${target.y+5}M${target.x-4} ${target.y+1}V${target.y+5}M${target.x} ${target.y+1}V${target.y+5}M${target.x+4} ${target.y+1}V${target.y+5}`);
                    const spray=q('.f-portable-spray');spray.style.display=a.phase==='perform'&&a.toolTarget&&a.wet&&!reduced.matches?'':'none';
                    set(spray,'d',`M${target.x-8} ${target.y+7}l-4 4M${target.x-1} ${target.y+8}v5M${target.x+6} ${target.y+7}l4 4`);
                    set(spray,'opacity',.35+.25*(1+Math.sin(t*16))/2);
                }
            }
            if(a.asset==='reset')set(q('.f-reset-lever'),'transform',`rotate(${a.working?Math.sin(t*12)*40:0} 2 -1)`);
        }
        const motion=v.actors.filter(a=>a.moving).map(a=>a.asset);
        layer.querySelectorAll('[data-route]').forEach(path=>set(path,'data-active',motion.includes(path.dataset.route)));
    }
    function focusAsset(asset){
        const node=asset==='dock'?q('.f-dock'):asset==='portable'?q('.f-portable'):nodes[asset];
        if(node&&node.style.display!=='none'&&layer.style.display!=='none'){
            node.scrollIntoView({block:'nearest',inline:'center',behavior:'instant'});node.focus({preventScroll:true});return true;
        }
        return false;
    }
    const click=e=>{const target=e.target.closest('[data-field-inspect]');if(target){e.stopPropagation();inspect(target);}};
    const keydown=e=>{if((e.key==='Enter'||e.key===' ')&&e.target.closest('[data-field-inspect]')){e.preventDefault();e.stopPropagation();inspect(e.target.closest('[data-field-inspect]'));}};
    layer.addEventListener('click',click);layer.addEventListener('keydown',keydown);
    const change=()=>{lastKey='';if(lastClock)render(lastClock);};reduced.addEventListener('change',change);
    return {render,focusAsset,snapshot:()=>lastVisual,destroy(){disposed=true;reduced.removeEventListener('change',change);layer.remove();}};
}
if(typeof module!=='undefined')module.exports={FIELD_ROUTES,fieldPoint,fieldVisualState,fractionalFieldVisualState,fieldSectionBrush,fieldRecoveryPoint,fieldSupportGeometry};
