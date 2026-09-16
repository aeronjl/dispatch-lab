/* Optional recorded-decision lens. Physics and policy comparisons remain in Python. */
function controlSelectionKey(run, controller, hour, generation) {return JSON.stringify([run,controller,hour,generation]);}
function controlValue(point, component) {
    if(!point)return null;
    const keys={battery:'battery_kwh',hydrogen:'h2_kg',co2:'co2_kg',reactor:'temperature_c'};
    return component==='solar'?point.pv_kw:component==='electrolyser'?point.action?.electrolyser_kw:point.state?.[keys[component]];
}
function controlSegments(values, width=720, height=118, maximum=null, minimum=0) {
    const finite=values.filter(Number.isFinite), max=maximum??Math.max(1,...finite);
    const segments=[];let part=[];
    values.forEach((v,i)=>{if(Number.isFinite(v))part.push(`${(i+.5)*width/values.length},${height-6-(v-minimum)/Math.max(1e-9,max-minimum)*(height-18)}`);else if(part.length){segments.push(part.join(' '));part=[];}});
    if(part.length)segments.push(part.join(' '));return segments;
}
function createControlView({root,getResult,getFrame,pause,setController,seekDecision,onOpen,onReturn,onComparison,fetcher=fetch}) {
    const labels={solar:'Solar array',battery:'Battery',electrolyser:'Electrolyser',hydrogen:'Hydrogen buffer',co2:'CO₂ supply',reactor:'Methanator'};
    const metrics={solar:['Available solar','kW'],battery:['Ending energy','kWh'],electrolyser:['Productive load','kW'],hydrogen:['Ending inventory','kg H₂'],co2:['Ending inventory','kg CO₂'],reactor:['Ending temperature','°C']};
    const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const percent=v=>Number.isFinite(v)?(v*100).toFixed(1)+'%':'Not recorded';
    const num=v=>Number.isFinite(v)?v.toLocaleString('en-GB',{maximumFractionDigits:1}):'Not recorded';
    const host=document.createElement('section');host.className='cv-workspace';host.hidden=true;host.setAttribute('aria-label','Control view');
    host.innerHTML=`<header class="cv-toolbar"><span>Control</span><label><span class="cv-sr">Recorded controller</span><select data-cv="controller"></select></label><span data-cv="interval"></span><label><span class="cv-sr">Recorded events</span><select data-cv="events"></select></label><button data-cv="close" aria-label="Close Control view">×</button></header>
      <div class="cv-panel"><div class="cv-panel-head"><label><span class="cv-sr">Control component</span><select data-cv="component">${Object.entries(labels).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select></label><nav aria-label="Decision views">${['Plan','Delivery','Evidence','Compare'].map(t=>`<button data-cv-tab="${t}" aria-pressed="false">${t}</button>`).join('')}</nav></div>
      <p class="cv-status" data-cv="status" role="status" aria-live="polite"></p><div class="cv-content" data-cv="content"></div><div class="cv-horizon" data-cv="horizon"><span data-cv="horizon-start"></span><label><span class="cv-sr">Predicted interval</span><input data-cv="offset" type="range" min="0" step="1"></label><span data-cv="horizon-end"></span></div></div>`;
    root.append(host);
    const q=s=>host.querySelector(s), instance=crypto.randomUUID();
    let opened=false,component='battery',tab='Plan',choice='policies',offset=0,generation=0,context=null,signature='',eventSignature='',boundary=-1,data=null,comparison=null,running=null,timer=null,origin=null;
    const choices={policies:'Compare control policies',battery:'Prevent battery discharge',electrolyser:'Keep electrolysis off',reactor:'Delay reactor start',co2:'Delay next CO₂ delivery by 24 h'};
    const selection=()=>{const r=getResult(),f=getFrame();return {token:r.model_token,run_id:r.run_id,controller:f.controller,hour:Math.max(0,f.hour-1),alternative:choice};};
    const sign=c=>controlSelectionKey(c.run_id,c.controller,c.hour,`${c.token}|${c.alternative}`);
    const next=()=>{const s=selection();return {...s,key:controlSelectionKey(s.run_id,s.controller,s.hour,`${instance}-${++generation}`)};};
    const fresh=c=>opened&&context?.key===c.key&&sign(selection())===sign(c);
    function status(message){q('[data-cv=status]').textContent=message;q('[data-cv=status]').hidden=!message;}
    async function send(c,operation,extra={}){
        const r=await fetcher('/dispatch/control-view',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...c,operation,...extra})});
        if(!r.ok){let detail;try{detail=(await r.json()).detail;}catch{}throw Error(typeof detail==='string'?detail:'Control view unavailable');}return r.json();
    }
    function cancel(){clearTimeout(timer);timer=null;if(running){const old=running;running=null;send(old.context,'cancel',old.job_id?{job_id:old.job_id}:{}).catch(()=>{});}}
    function highlight(){root.querySelectorAll('.m-plant [data-component]').forEach(n=>{
        n.dataset.controlSelected=String(opened&&n.dataset.component===component);
        n.dataset.controlBound=String(opened&&!!data?.evidence?.bindings?.[n.dataset.component]?.length);
    });}
    function close(focus=true){if(!opened)return;cancel();opened=false;context=null;data=null;comparison=null;host.hidden=true;delete root.dataset.controlView;highlight();if(focus)onReturn?.(origin);}
    function open(key='battery',from=document.activeElement,options={}){origin=from;pause();onOpen?.();component=labels[key]?key:'battery';opened=true;tab=options.tab||'Plan';choice='policies';root.dataset.chrome='visible';root.dataset.controlView='true';host.hidden=false;
        const r=getResult();q('[data-cv=controller]').innerHTML=Object.keys(r.records).map(k=>`<option>${esc(k)}</option>`).join('');q('[data-cv=controller]').value=getFrame().controller;q('[data-cv=component]').value=component;load();q('[data-cv=close]').focus({preventScroll:true});}
    async function load(){
        cancel();data=null;comparison=null;offset=0;context=next();const c=context;signature=sign(c);boundary=getFrame().hour;
        q('[data-cv=controller]').value=c.controller;q('[data-cv=interval]').textContent=boundary===0?'Decision H0 · plant initial':`Recorded H${c.hour} → ${c.hour+1}`;
        if(eventSignature!==`${c.run_id}|${c.controller}`){eventSignature=`${c.run_id}|${c.controller}`;q('[data-cv=events]').innerHTML='<option value="">Recorded events…</option>'+(getResult().events[c.controller]||[]).map((e,i)=>`<option value="${i}">H${e.hour} · ${esc(e.label)}</option>`).join('');}q('[data-cv=events]').value='';paint();highlight();
        if(!c.token||getResult().offline_mode){status('Original decision detail requires the restored application. No missing plan is reconstructed.');return;}
        status('Loading recorded decision…');
        try{const a=await send(c,'describe');if(!fresh(c)||a.key!==c.key)return;if(a.status!=='available'){status(a.error||a.status);return;}data=a;status('');paint();highlight();}catch(e){if(fresh(c))status(e.message);}
    }
    function sync(){if(opened&&(signature!==sign(selection())||boundary!==getFrame().hour))load();}
    function select(key){if(!labels[key])return;component=key;q('[data-cv=component]').value=key;paint();highlight();}
    function initial(){const e=data.estimate, keys={battery:'battery_kwh',hydrogen:'h2_kg',co2:'co2_kg',reactor:'temperature_c'};return e?.[keys[component]];}
    function chart(series,legend){
        const [title,unit]=metrics[component],all=series.flatMap(s=>s.points.map(p=>controlValue(p,component))).filter(Number.isFinite),min=Math.min(0,...all),max=Math.max(1,...all),n=data.points.length;
        if(!all.length)return '<p>No trajectory was saved for this component.</p>';
        return `<figure class="cv-chart"><figcaption>${esc(title)} · ${esc(unit)} <span>${num(min)}–${num(max)}</span></figcaption><svg viewBox="0 0 720 118" preserveAspectRatio="none" role="img" aria-label="${esc(title)}: ${esc(legend.map(v=>v[1]).join(', '))}"><path d="M0 112H720" class="cv-axis"/><rect class="cv-cursor" x="${offset*720/n}" y="0" width="${720/n}" height="118"/>${series.map((s,j)=>controlSegments(s.points.map(p=>controlValue(p,component)),720,118,max,min).map(points=>`<polyline class="cv-line cv-line-${j}" points="${points}"/>`).join('')).join('')}</svg><div class="cv-legend">${legend.map(([j,name])=>`<span class="cv-key-${j}">${esc(name)}</span>`).join('')}</div></figure>`;
    }
    function schedule(){
        const lanes=[['solar','Solar','pv_kw'],['battery','Charge','charge_kw'],['battery','Discharge','discharge_kw'],['electrolyser','Electrolysis','electrolyser_kw'],['reactor','Methane','methane_kg']];
        return `<div class="cv-schedule" aria-label="Recorded planning horizon">${lanes.map(([c,label,k])=>{
            const v=data.points.map(p=>k==='pv_kw'?p.pv_kw:p.action?.[k]),max=Math.max(1,...v.filter(Number.isFinite));
            return `<button class="cv-lane-label" data-cv-select="${c}">${label}</button><div class="cv-lane" style="--count:${v.length}">${v.map((a,i)=>`<button data-cv-offset="${i}" aria-label="${label}, predicted interval H${data.hour+i} to ${data.hour+i+1}: ${num(a)} ${k==='methane_kg'?'kg':'kW'}" aria-pressed="${i===offset}" style="--level:${Number.isFinite(a)?Math.max(0,a)/max:0}"><i></i></button>`).join('')}</div>`;}).join('')}</div>`;
    }

    function planView(){
        const point=data.points[offset],prior=data.previous[offset], [metric,unit]=metrics[component],a=point?.action||{},initialValue=initial();
        const actions={battery:`Charge ${num(a.charge_kw)} / discharge ${num(a.discharge_kw)} kW`,electrolyser:`Request ${num(a.electrolyser_kw)} kW`,reactor:`Produce ${num(a.methane_kg)} kg · heat ${num(a.heater_kw)} kW`,hydrogen:`Stored for downstream methanation`,co2:`Delivery ${num(point?.deliveries_kg)} kg`,solar:`Shared service demand ${num(point?.service_kw)} kW`};
        const objective={greedy:'Use a local dispatch rule',methane:'Maximise horizon methane',economics:'Maximise assumed operating contribution'}[data.objective]||data.objective||'Objective not recorded';
        const bindings=data.evidence.bindings?.[component]||[], e=data.evidence;
        const factors={
            battery:[Number.isFinite(e.battery?.planned_deficit_kwh)?`Forecast demand above solar: ${num(e.battery.planned_deficit_kwh)} kWh across this plan.`:'',e.battery?.planned_discharge_offsets?.length?`First planned discharge: H${data.hour+e.battery.planned_discharge_offsets[0]}.`:''],
            electrolyser:[Number.isFinite(e.electrolyser?.estimated_capacity_kw)?`Estimated available capacity: ${num(e.electrolyser.estimated_capacity_kw)} kW.`:'',Number.isFinite(e.electrolyser?.hydrogen_headroom_kg)?`Hydrogen headroom: ${num(e.electrolyser.hydrogen_headroom_kg)} kg.`:''],
            hydrogen:[Number.isFinite(e.hydrogen?.predicted_use_kg)?`Planned downstream use: ${num(e.hydrogen.predicted_use_kg)} kg over the horizon.`:''],
            co2:[Number.isFinite(e.co2?.predicted_use_kg)?`Planned downstream use: ${num(e.co2.predicted_use_kg)} kg over the horizon.`:''],
            reactor:[e.reactor?.commitment_hours?`${e.reactor.commitment_hours} hours of minimum run remain at this decision.`:'',e.reactor?.production_band_c?`Production band: ${e.reactor.production_band_c.map(num).join('–')}°C.`:''],
            solar:[e.solar?.forecast_source?.source||'']
        }[component].filter(Boolean);
        return `<div class="cv-reading"><span class="cv-eyebrow">${esc(objective)}</span><h3>Predicted H${data.hour+offset} → ${data.hour+offset+1}</h3><p class="cv-value">${num(controlValue(point,component))} <small>${esc(unit)}</small></p><p>${esc(metric)}. ${esc(actions[component])}.</p>${Number.isFinite(initialValue)?`<p class="cv-muted">Starting estimate ${num(initialValue)} ${unit}</p>`:''}${prior?`<p class="cv-muted">Previous plan: ${num(controlValue(prior,component))} ${unit}</p>`:''}${factors.length?`<p class="cv-muted">${esc(factors.join(' '))}</p>`:''}${bindings.length?`<p class="cv-bound">At this decision: ${esc(bindings.join(' · '))}</p>`:''}</div>
        <div class="cv-visual">${chart([{points:data.points},{points:data.previous}],[[0,'Recorded plan'],[1,'Previous plan · aligned hours']])}${schedule()}</div>`;
    }
    function table(headers,rows){return `<div class="cv-table"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;}
    function deliveryView(){
        const rows=[['Electrolysis','electrolyser_kw','kW'],['Battery charge','charge_kw','kW'],['Battery discharge','discharge_kw','kW'],['Reactor heating','heater_kw','kW'],['Heat rejection','cooling_kw','kW thermal'],['Methane','methane_kg','kg']];
        return `<div class="cv-reading"><span class="cv-eyebrow">Requested → applied</span><h3>H${data.hour} → ${data.hour+1}</h3><p>${boundary===0?'The diagram is at the initial boundary. Step forward to see this first recorded interval.':'The diagram shows this recorded interval. Future timeline cells show predictions only.'}</p><p class="cv-bound">${data.forced_trip?'Forced trip recorded.':'No forced trip recorded.'}</p><p class="cv-muted">Applied actions are execution records. They are not independent sensor measurements.</p></div><div class="cv-visual">${table(['Action','Requested','Applied','Unit'],rows.map(([l,k,u])=>[l,num(data.requested?.[k]),num(data.applied?.[k]),u]))}<div class="cv-delivery-bars">${rows.filter(([,k])=>k!=='methane_kg').map(([l,k])=>{
            const requested=data.requested?.[k],applied=data.applied?.[k],max=Math.max(1,requested||0,applied||0);return `<div><span>${l}</span><svg viewBox="0 0 220 18" role="img" aria-label="${l}: requested ${num(requested)}, applied ${num(applied)} kW">${Number.isFinite(requested)?`<rect class="cv-request" x="0" y="2" width="${requested/max*218}" height="5"/>`:''}${Number.isFinite(applied)?`<rect class="cv-applied" x="0" y="11" width="${applied/max*218}" height="5"/>`:''}</svg></div>`;
        }).join('')}</div><p class="cv-muted">Outline: requested · filled: applied</p></div>`;
    }
    function evidenceView(){
        const b=data.diagnosis_before||{},a=data.diagnosis_after||{},s=data.solver||{},source=data.forecast_source||{};
        return `<div class="cv-reading"><span class="cv-eyebrow">Recorded evidence</span><h3>${esc(labels[component])}</h3>${(data.evidence.bindings?.[component]||[]).map(v=>`<p class="cv-bound">${esc(v)}</p>`).join('')||'<p>No active limit recorded for this component.</p>'}${(data.evidence.constraints||[]).map(v=>`<p>${esc(v)}</p>`).join('')}<p class="cv-muted">A binding limit is not a causal importance score.</p></div><div class="cv-visual cv-evidence">
        <section><h4>Observe → test → check</h4><p>Before: ${esc(b.status||'Not recorded')} · ${num(b.capacity_kw)} kW estimated.</p><p>${data.probe?'Load probe requested. Recovery still requires successful tracking.':'No load probe at this decision.'}</p><p>After: ${esc(a.status||'Not recorded')} · ${num(a.capacity_kw)} kW estimated.</p><p>${a.flow_isolated?'Flow sensor isolated. Independent balance estimate in use.':a.informative?'Tracking evidence available at the tested load.':'Insufficient excitation is not evidence of health.'}</p><p class="cv-muted">${esc(a.uncertainty||b.uncertainty||'Uncertainty not recorded')}</p>${data.recovery&&data.recovery.status!=='inactive'?`<p>Recovery test: ${esc(data.recovery.status)}${Number.isFinite(data.recovery.selected_start)?' · planned H'+data.recovery.selected_start:''}. A planned test does not establish recovery.</p>`:''}${data.events.map(e=>`<p class="cv-event">${esc(e.label)}</p>`).join('')}</section>
        <section><h4>Forecast & solve</h4><p>${esc(source.source||'Source not recorded')}</p><p class="cv-muted">Issued ${esc(source.initialized_at||'not recorded')}<br>Available ${esc(source.available_at||'not recorded')}</p><p>${data.points.length} h horizon · ${esc(s.status||'Solver status not recorded')}${s.fallback_used?' · fallback used':''}</p><p class="cv-muted">${esc(s.message||s.reason||'')}</p><p>Tracking residual ${percent(b.tracking_residual)} · flow residual ${percent(b.flow_residual)}</p><p class="cv-muted">Residual ratios shown as percentages, before this decision.</p><p class="cv-muted">Recorded model: ${esc(data.original_model_version||'Missing')}<br>Dispatch prices: ${esc(data.cost_version||'Missing')}</p></section></div>`;
    }
    function comparisonView(){
        const allowed=data.comparison.available;
        let output='';
        if(comparison){
            const names=comparison.order||Object.keys(comparison.predictions), ps=names.map(n=>comparison.predictions[n]);
            const rows=[['Methane / kg',p=>p?.methane_kg],['Decision cost / €',p=>p?.variable_and_wear_eur],['Assumed contribution / €',p=>p?.assumed_contribution_eur],['Reactor starts',p=>p?.reactor_starts],['Ending battery / kWh',p=>p?.ending?.battery_kwh],['Ending hydrogen / kg',p=>p?.ending?.h2_kg],['Ending CO₂ / kg',p=>p?.ending?.co2_kg],['Ending temperature / °C',p=>p?.ending?.temperature_c]];
            output=`${chart(ps, names.map((n,i)=>[i,n]))}${table(['Predicted',...names],rows.map(([n,fn])=>[n,...ps.map(p=>num(fn(p.predicted)))]))}${table(['Calculation',...names],[['Basis',...ps.map(p=>p.basis)],['Termination',...ps.map(p=>p.solver.status)],['Fallback',...ps.map(p=>p.solver.fallback_used?'Used':'No')],['Gap',...ps.map(p=>Number.isFinite(p.solver.gap)?num(p.solver.gap*100)+'%':'—')]])}<p class="cv-muted">${esc(comparison.comparison_version)} · input ${esc(comparison.information_id.slice(0,12))} · frozen dispatch prices. No ending-inventory sale credit.${comparison.terminal_battery_value?' Methane terminal battery allowance: '+num(comparison.terminal_battery_value)+' kg/kWh.':''}</p><p class="cv-muted">Current source <span title="${esc(comparison.replanner_source_content_hash)}">${esc(comparison.replanner_source_content_hash?.slice(0,12))}</span> · recorded source <span title="${esc(comparison.original_source||'Not saved')}">${esc(comparison.original_source?.slice(0,12)||'Not saved')}</span></p>`;
        }else output=`<p class="cv-comparison-empty">One starting point.<br>${choice==='policies'?'Three ways to use the next hours.':'One action to reconsider.'}</p>`;
        return `<div class="cv-reading"><span class="cv-eyebrow">Same information · new predictions</span><h3>Try an alternative</h3><label class="cv-alternative">Question<select data-cv="alternative">${Object.entries(choices).map(([k,v])=>`<option value="${k}" ${choice===k?'selected':''}>${esc(v)}</option>`).join('')}</select></label><button data-cv="calculate" ${!allowed||running?'disabled':''}>Calculate comparison</button><button data-cv="cancel" ${running?'':'hidden'}>Cancel</button><p>${esc(comparison?.scope||(choice==='policies'?data.comparison.scope:'Re-solve reference dispatch and the declared alternative from the same recorded estimate, forecast and frozen prices. These are predictions, not alternative realised histories. Service commitments stay fixed.'))}</p>${!allowed?`<p class="cv-bound">${esc(data.comparison.reason)}</p>`:''}<p class="cv-muted">${choice==='policies'?'Greedy follows a local rule. MPC methane favours output; MPC economics trades output against variable cost and wear. Fixed ownership costs do not drive dispatch.':'Only the declared restriction changes. The reference is also recalculated; solver differences from the archived plan remain possible. No automatic fallback replaces an infeasible or unresolved alternative.'}</p></div><div class="cv-visual">${output}</div>`;
    }
    function paint(){
        if(!opened)return;
        performance.mark('control-render-start');
        host.dataset.tab=tab;q('[data-cv=component]').value=component;
        q('[data-cv=horizon]').hidden=!data||!['Plan','Compare'].includes(tab);
        if(data){q('[data-cv=horizon-start]').textContent=`Forecast H${data.hour}`;q('[data-cv=horizon-end]').textContent=`H${data.hour+data.points.length}`;q('[data-cv=offset]').max=Math.max(0,data.points.length-1);q('[data-cv=offset]').value=offset;}
        host.querySelectorAll('[data-cv-tab]').forEach(n=>n.setAttribute('aria-pressed',String(n.dataset.cvTab===tab)));
        q('[data-cv=content]').innerHTML=!data?'':tab==='Plan'?planView():tab==='Delivery'?deliveryView():tab==='Evidence'?evidenceView():comparisonView();
        performance.measure('dispatch-control-render','control-render-start');performance.clearMarks('control-render-start');
    }
    async function calculate(){
        if(!data?.comparison.available)return;pause();cancel();context=next();const c=context;running={context:c,job_id:null};status('Calculating from the original decision information…');paint();q('[data-cv=cancel]')?.focus({preventScroll:true});
        async function receive(operation,extra={}){
            try{const a=await send(c,operation,extra);if(!fresh(c)||a.key!==c.key||!running)return;
                if(a.status==='running'){running.job_id=a.job_id;status(a.progress||'Starting isolated comparison…');timer=setTimeout(()=>receive('poll',{job_id:a.job_id}),200);return;}
                running=null;const restore=document.activeElement===q('[data-cv=cancel]');if(a.predictions){comparison=a;onComparison?.(a);}
                status(a.predictions?`Comparison ${a.status}. All curves are conditional predictions; inspect solver termination below.`:a.error||a.status);paint();if(restore)q('[data-cv=calculate]')?.focus({preventScroll:true});
            }catch(e){if(fresh(c)){running=null;status(e.message);paint();}}
        }
        await receive('start');
    }
    host.addEventListener('click',e=>{
        const t=e.target.closest('[data-cv-tab]');if(t){tab=t.dataset.cvTab;paint();return;}
        const s=e.target.closest('[data-cv-select]');if(s){select(s.dataset.cvSelect);return;}
        const o=e.target.closest('[data-cv-offset]');if(o){offset=Number(o.dataset.cvOffset);paint();q(`[data-cv-offset="${offset}"]`)?.focus({preventScroll:true});return;}
        const action=e.target.closest('[data-cv]')?.dataset.cv;
        if(action==='close')close();if(action==='calculate')calculate();if(action==='cancel'){cancel();context=next();status('Comparison cancelled.');paint();q('[data-cv=calculate]')?.focus({preventScroll:true});}
    });
    host.addEventListener('change',e=>{if(e.target.matches('[data-cv=alternative]')){cancel();choice=e.target.value;comparison=null;context=next();signature=sign(context);status('');paint();q('[data-cv=alternative]').focus();}if(e.target.matches('[data-cv=events]')&&e.target.value!==''){const event=getResult().events[getFrame().controller][Number(e.target.value)];pause();seekDecision(event.hour);select(event.component);}if(e.target.matches('[data-cv=controller]')){pause();setController(e.target.value);}if(e.target.matches('[data-cv=component]'))select(e.target.value);});
    host.addEventListener('input',e=>{if(e.target.matches('[data-cv=offset]')){offset=Number(e.target.value);paint();}});
    host.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close();}});
    return {open,close,sync,select,isOpen:()=>opened,destroy:()=>{cancel();host.remove();}};
}
if(typeof module!=='undefined')module.exports={controlSelectionKey,controlValue,controlSegments};
