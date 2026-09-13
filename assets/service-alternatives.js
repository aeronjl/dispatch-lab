/* Render recorded comparisons. All scheduling and accounting remain in Python. */
function serviceAlternativeKey(run, controller, hour, generation) {
    return JSON.stringify([run, controller, hour, generation]);
}
function serviceAlternativeRows(answer) {
    const names=['baseline','alternative'], get=path=>names.map(name=>path.reduce((v,k)=>v?.[k],answer[name]?.summary));
    return [
        ['Methane','kg',...get(['prediction','methane_kg'])],
        ['Reactor starts','',...get(['prediction','reactor_starts'])],
        ['Ending plant battery','kWh',...get(['prediction','ending','battery_kwh'])],
        ['Ending hydrogen','kg',...get(['prediction','ending','h2_kg'])],
        ['Ending CO₂','kg',...get(['prediction','ending','co2_kg'])],
        ['Ending reactor temperature','°C',...get(['prediction','ending','temperature_c'])],
        ['Service decision cost','€',...get(['service_decision_eur'])],
        ['Total decision cost','€',...get(['total_decision_eur'])],
        ['Assumed contribution','€',...get(['assumed_contribution_eur'])],
    ];
}
function investigationAlternativeRows(answer) {
    const get=path=>['baseline','alternative'].map(name=>path.reduce((v,k)=>v?.[k],answer[name]?.summary?.expected));
    return [
        ['Expected methane','kg',...get(['methane_kg'])],
        ['Expected starts','',...get(['reactor_starts'])],
        ['Expected ending plant battery','kWh',...get(['ending','battery_kwh'])],
        ['Expected ending hydrogen','kg',...get(['ending','h2_kg'])],
        ['Expected ending CO₂','kg',...get(['ending','co2_kg'])],
        ['Expected ending reactor temperature','°C',...get(['ending','temperature_c'])],
        ['Expected service decision cost','€',...get(['service_decision_eur'])],
        ['Expected total decision cost','€',...get(['total_decision_eur'])],
        ['Expected assumed contribution','€',...get(['assumed_contribution_eur'])],
    ];
}
function createServiceAlternatives({root,getResult,getFrame,pause,seekDecision,fetcher=fetch}) {
    const host=root.querySelector('[data-service-alternatives]');
    if(!host)return null;
    const q=s=>host.querySelector(s), openButton=q('[data-sa=open]'), workspace=q('[data-sa=workspace]');
    openButton.hidden=false;
    const instance=crypto.randomUUID();
    let opened=false, generation=0, signature='', context=null, description=null, running=null, last=null, pollTimer=null;
    const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const num=v=>Number.isFinite(v)?v.toLocaleString('en-GB',{maximumFractionDigits:3}):'Unavailable';
    function selection(){const r=getResult(),f=getFrame();return {token:r.model_token,run_id:r.run_id,controller:f.controller,hour:Math.max(0,f.hour-1)};}
    function sign(s){return serviceAlternativeKey(s.run_id,s.controller,s.hour,s.token);}
    function next(){generation++;const s=selection();return {...s,key:serviceAlternativeKey(s.run_id,s.controller,s.hour,`${instance}-${generation}`)};}
    function fresh(c){return opened&&context?.key===c.key&&sign(selection())===sign(c);}
    async function send(c,operation,extra={}){
        const response=await fetcher('/dispatch/service-alternative',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...c,operation,...extra})});
        if(!response.ok){let msg='Comparison unavailable';try{msg=(await response.json()).detail||msg;}catch{}throw Error(typeof msg==='string'?msg:'Invalid comparison request');}
        return response.json();
    }
    function status(message){const node=q('[data-sa=status]');if(node)node.textContent=message;}
    function idleButtons(){const stop=q('[data-sa=cancel]'),button=q('[data-sa=calculate]'),restore=stop&&document.activeElement===stop;stop?.setAttribute('hidden','');if(button){button.disabled=false;if(restore)button.focus({preventScroll:true});}}
    function cancel(){
        clearTimeout(pollTimer);pollTimer=null;
        if(running){const old=running;running=null;send(old.context,'cancel',old.job_id?{job_id:old.job_id}:{}).catch(()=>{});}
        idleButtons();
    }
    function close(focus=true){cancel();opened=false;generation++;context=null;workspace.hidden=true;openButton.setAttribute('aria-expanded','false');if(focus)openButton.focus({preventScroll:true});}
    function shell(){workspace.innerHTML='<header><h3>Compare this service decision</h3><button data-sa="close" aria-label="Close service comparison">Close</button></header><p data-sa="status" role="status" aria-live="polite"></p><div data-sa="inputs"></div><div data-sa="result"></div>';}
    async function load(){
        cancel();description=null;last=null;context=next();const c=context;signature=sign(c);shell();
        const r=getResult();
        if(r.offline_mode||!r.model_token){status('Live recalculation requires the restored application. Saved mission and cost records remain available below.');return;}
        status('Loading original decision information…');
        try{const d=await send(c,'describe');if(!fresh(c)||d.key!==c.key)return;if(d.status!=='available'){status(d.error||d.status);return;}description=d;form();status(d.note);}catch(e){if(fresh(c))status(e.message);}
    }
    async function open(){pause();opened=true;workspace.hidden=false;openButton.setAttribute('aria-expanded','true');await load();q('[data-sa=close]')?.focus({preventScroll:true});}
    function sync(){if(opened&&signature!==sign(selection()))load();}
    function form(){
        const d=description, kinds=[];
        if(d.investigation?.selection_id)kinds.push(['investigation','Inspect first or intervene directly']);
        if(d.orders.length)kinds.push(['postpone','Postpone selected work']);
        if(d.orders.some(o=>o.action?.includes('clean')))kinds.push(['defer-cleaning','Defer cleaning']);
        if(d.orders.some(o=>o.procedures?.length))kinds.push(['procedure','Change compatible procedure']);
        if(d.reserve_available&&d.robots.length)kinds.push(['reserve-energy','Reserve robot energy']);
        const origin=d.investigation?.origin_hour;
        const navigate=Number.isInteger(origin)&&origin!==context.hour&&seekDecision?`<p><button data-sa="origin">Review the original investigation choice at H${origin}</button></p>`:'';
        if(!kinds.length){q('[data-sa=inputs]').innerHTML='<p>No new work or joint charging target is available for a targeted change at this decision.</p>'+navigate;return;}
        q('[data-sa=inputs]').innerHTML=`${navigate}<form data-sa="form"><label>Alternative<select data-sa="kind">${kinds.map(([v,l])=>`<option value="${v}">${l}</option>`).join('')}</select></label><div data-sa="parameters"></div><div class="sa-actions"><button data-sa="calculate" type="submit">Calculate comparison</button><button data-sa="cancel" type="button" hidden>Cancel</button></div></form>`;
        parameters();
    }
    function parameters(){
        const d=description, kind=q('[data-sa=kind]').value;
        if(kind==='investigation'){
            const i=d.investigation;
            q('[data-sa=parameters]').innerHTML=`<p>Originally selected: ${esc(i.selected_label)}.</p><label>Alternative strategy<select data-sa="strategy">${i.strategies.map(s=>`<option value="${esc(s.value)}">${esc(s.label)}</option>`).join('')}</select></label><p class="m-muted">${esc(i.note)}</p>`;
        }else if(kind==='reserve-energy'){
            q('[data-sa=parameters]').innerHTML=`<label>Robot<select data-sa="robot">${d.robots.map(r=>`<option value="${esc(r.name)}">${esc(r.name)} · ${num(r.initial_kwh)} / ${num(r.capacity_kwh)} kWh</option>`).join('')}</select></label><label>Required energy / kWh<input data-sa="energy" type="number" min="0" step="any" required></label><label>Absolute deadline / hour<input data-sa="due" type="number" min="1" step="1" required></label>`;reserveDefaults();
        }else{
            const orders=d.orders.filter(o=>kind==='procedure'?o.procedures?.length:kind!=='defer-cleaning'||o.action?.includes('clean'));
            q('[data-sa=parameters]').innerHTML=`<label>Work order<select data-sa="order">${orders.map(o=>`<option value="${esc(o.order_id)}">${esc(o.order_id)} · ${esc(o.kind)}${o.shared_visit?' · shared visit':''}</option>`).join('')}</select></label>${kind==='procedure'?'<label>Recorded procedure<select data-sa="procedure"></select></label><p data-sa="procedure-scope" class="m-muted"></p>':'<label>Delay / hours<input data-sa="delay" type="number" min="0.001" step="any" value="1" required></label><p class="m-muted">A shared visit moves as one itinerary. Delays beyond the forecast window can be infeasible.</p>'}`;
            if(kind==='procedure')procedures();
        }
    }
    function procedures(){const order=description.orders.find(o=>o.order_id===q('[data-sa=order]').value);q('[data-sa=procedure]').innerHTML=order.procedures.map(p=>`<option value="${esc(p.procedure_id)}">${esc(p.label)}${p.unavailable?' · unavailable':''}</option>`).join('');procedureScope();}
    function procedureScope(){const order=description.orders.find(o=>o.order_id===q('[data-sa=order]').value),p=order.procedures.find(p=>p.procedure_id===q('[data-sa=procedure]').value);q('[data-sa=procedure-scope]').textContent=p.scope+(p.unavailable?' Original restriction: '+p.unavailable:'')+' Departure and all other selected work are retained.';}
    function reserveDefaults(){const robot=q('[data-sa=robot]').value,t=description.energy_targets.find(t=>t.robot===robot),r=description.robots.find(r=>r.name===robot);q('[data-sa=energy]').value=t?.energy_kwh??r.initial_kwh;q('[data-sa=due]').value=t?.due_hour??context.hour+description.hours;}
    function inputs(){const kind=q('[data-sa=kind]').value;return kind==='investigation'?{kind,selection_id:description.investigation.selection_id,strategy:q('[data-sa=strategy]').value}:kind==='reserve-energy'?{kind,robot:q('[data-sa=robot]').value,energy_kwh:Number(q('[data-sa=energy]').value),due_hour:Number(q('[data-sa=due]').value)}:kind==='procedure'?{kind,order_id:q('[data-sa=order]').value,procedure_id:q('[data-sa=procedure]').value}:{kind,order_id:q('[data-sa=order]').value,delay_hours:Number(q('[data-sa=delay]').value)};}
    function changed(){cancel();context=next();status(last?'Inputs changed. The displayed comparison belongs to the previous inputs.':'Inputs changed. Calculate to compare.');q('[data-sa=result]').dataset.stale=String(!!last);const prior=q('[data-sa=previous]');if(prior)prior.hidden=!last;}
    async function calculate(){
        if(!q('[data-sa=form]').reportValidity())return;
        pause();cancel();context=next();const c=context, alternative=inputs();running={context:c,job_id:null};
        const button=q('[data-sa=calculate]'),restore=document.activeElement===button;button.disabled=true;q('[data-sa=cancel]').hidden=false;if(restore)q('[data-sa=cancel]').focus({preventScroll:true});
        status(last?'Calculating. The previous comparison remains displayed.':'Calculating from the original information…');q('[data-sa=result]').dataset.stale=String(!!last);const prior=q('[data-sa=previous]');if(prior)prior.hidden=!last;
        async function receive(operation,extra){
            try{const a=await send(c,operation,extra);if(!fresh(c)||a.key!==c.key)return;
                if(a.status==='running'){running.job_id=a.job_id;status(a.progress||'Starting isolated comparison…');pollTimer=setTimeout(()=>receive('poll',{job_id:a.job_id}),200);return;}
                running=null;idleButtons();
                if(a.baseline&&a.alternative){last=a;render(a);status(a.status==='complete'?'Comparison complete. Both columns are conditional predictions.':'Comparison incomplete. Some predictions or costs remain unresolved; inspect their conditions.');}
                else status((a.error||a.status)+(last?' The previous comparison remains displayed.':''));
            }catch(e){if(fresh(c)){running=null;idleButtons();status(e.message+(last?' The previous comparison remains displayed.':''));}}
        }
        await receive('start',{alternative});
    }
    function plot(a){
        const series=['baseline','alternative'].map(k=>a[k].summary.prediction?.temperature_c||[]),values=series.flat().filter(Number.isFinite);if(!values.length)return '';
        const min=Math.min(...values),max=Math.max(min+1,...values),n=Math.max(...series.map(s=>s.length));
        return `<figure><svg viewBox="0 0 480 120" role="img" aria-label="Predicted reactor temperature: baseline solid line, alternative dashed line">${series.map((s,i)=>`<polyline fill="none" stroke="currentColor" stroke-width="2" ${i?'stroke-dasharray="6 4"':''} points="${s.map((v,t)=>`${12+t*456/Math.max(1,n-1)},${108-(v-min)*96/(max-min)}`).join(' ')}"/>`).join('')}</svg><figcaption>Predicted reactor temperature · ${num(min)}–${num(max)}°C. Baseline solid; alternative dashed.</figcaption></figure>`;
    }
    function render(a){
        if(a.kind==='investigation'){renderInvestigation(a);return;}
        const s=q('[data-sa=result]');s.dataset.stale='false';
        const table=rows=>`<div class="sa-table"><table><thead><tr><th>Prediction</th><th>Baseline</th><th>Alternative</th></tr></thead><tbody>${rows.map(([l,u,x,y])=>`<tr><th>${esc(l)}${u?' / '+esc(u):''}</th><td>${num(x)}</td><td>${num(y)}</td></tr>`).join('')}</tbody></table></div>`;
        let html=`<p data-sa="previous" hidden>Previous inputs. Recalculate to update this comparison.</p><h4>H${a.hour} · ${esc(a.controller)} · ${a.hours}-hour prediction</h4><p>${esc(a.note)}</p>`;
        if(!a.same_application_source||!a.same_service_source)html+='<p>Current-model recalculation: the implementation differs from the saved run. The recorded prediction is retained separately below.</p>';
        html+=table(serviceAlternativeRows(a))+plot(a);
        for(const k of ['baseline','alternative']){const e=a[k].evaluation,v=a[k].summary;html+=`<p><strong>${k==='baseline'?'Baseline':'Alternative'}: ${esc(v.state)}</strong> · ${esc(v.solver?.status||'No validated process plan')}${v.solver?.fallback_used?' · fallback used':''}</p>`;if(v.cost_status==='incomplete')html+='<p>Decision cost is incomplete. Unpriced inputs or conditional supply acceptance are not treated as free resources.</p>';for(const c of e.constraints||[])html+=`<p>${esc(c.reason||c.condition)}</p>`;}
        html+='<button data-sa="details" aria-expanded="false">Prediction boundary and recorded original</button><section data-sa="evidence" hidden>';
        for(const k of ['baseline','alternative']){const v=a[k].summary;html+=`<h4>${k==='baseline'?'Baseline':'Alternative'} boundary</h4><p>Unselected work: ${esc((v.unselected_work||[]).map(o=>o.id).join(', ')||'None recorded')}.</p>`;for(const t of v.original_obligations||[])html+=`<p>${esc(t.obligation.id)} · original deadline H${num(t.obligation.due_hour)} · ${t.met?'within deadline':'deadline not established as met'} · ${esc(t.basis)}.</p>`;for(const t of v.terminal_work||[])html+=`<p>${esc(t.order_id)}: ${num(t.remaining_work_hours)} work hours beyond this boundary.</p>`;html+=`<p>${esc(v.scope||'No validated continuation for this candidate.')}</p>`;}
        const x=a.baseline.summary.ending_service_stocks,y=a.alternative.summary.ending_service_stocks,units=a.baseline.summary.service_stock_units||a.alternative.summary.service_stock_units||{},keys=[...new Set([...Object.keys(x||{}),...Object.keys(y||{})])];html+=table(keys.map(k=>[k,units[k]||'',x?.[k],y?.[k]]));
        html+=`<h4>Recorded original prediction</h4><p>${num(a.recorded.process_prediction?.methane_kg)} kg methane · ${esc(a.recorded.process_solver?.status)} · service ${esc(a.recorded.service_status)}${a.recorded.service_fallback?' (fallback)':''}.</p><p>${esc(a.context_note)}</p><p>Forecast ${esc(a.forecast_source.id)} · available ${esc(a.forecast_source.available_at)}.</p><p>Original prices ${esc(a.cost_version)} · service prices ${esc(a.service_cost_version)}.</p><p>Original source ${esc(a.original_source||'Missing')}<br>Replanner ${esc(a.replanner_source)}<br>Snapshot ${esc(a.snapshot_id)}<br>Comparison ${esc(a.comparison_id)}</p></section>`;
        s.innerHTML=html;
    }
    function renderInvestigation(a){
        const node=q('[data-sa=result]');node.dataset.stale='false';
        let html=`<p data-sa="previous" hidden>Previous inputs. Recalculate to update this comparison.</p><h4>H${a.hour} · ${esc(a.controller)} · ${a.hours}-hour investigation prediction</h4><p>${esc(a.note)}</p>`;
        if(!a.same_application_source||!a.same_service_source)html+='<p>Current-model recalculation: implementation differs from the saved run. The original prediction remains separate below.</p>';
        html+=`<div class="sa-table"><table><thead><tr><th>Prediction</th><th>Baseline · ${esc(a.baseline.label)}</th><th>Alternative · ${esc(a.alternative.label)}</th></tr></thead><tbody>${investigationAlternativeRows(a).map(([l,u,x,y])=>`<tr><th>${esc(l)}${u?' / '+esc(u):''}</th><td>${num(x)}</td><td>${num(y)}</td></tr>`).join('')}</tbody></table></div>`;
        for(const key of ['baseline','alternative']){
            const v=a[key].summary;
            html+=`<p><strong>${esc(a[key].label)}: ${esc(v.state)}</strong> · ${esc(v.solver?.status||'No validated process plan')}${v.solver?.termination?' · '+esc(v.solver.termination):''}${v.solver?.fallback_used?' · fallback used':''} · ${v.eligible?'meets':'does not establish'} the original restoration requirement.</p><p>Assumed restoration probability ${num(v.restoration_probability)}; required ${num(v.restoration_requirement)}. Operating recovery remains unverified in every branch.</p>`;
            if(v.solver)html+=`<p>Solver gap ${num(v.solver.gap)} · ${v.solver.valid_incumbent?'validated incumbent':'no validated incumbent'}.</p>`;
            if(v.reason)html+=`<p>${esc(v.reason)}</p>`;
            for(const condition of v.conditions||[])html+=`<p>${esc(typeof condition==='string'?condition:JSON.stringify(condition))}</p>`;
        }
        html+='<button data-sa="details" aria-expanded="false">Explore possible findings and original evidence</button><section data-sa="evidence" hidden>';
        for(const key of ['baseline','alternative']){
            const arm=a.comparison.strategies?.[a[key].strategy]||{},cases=arm.cases||[];
            html+=`<h4>${esc(a[key].label)} · possible outcomes</h4>`;
            if(cases.length)html+=`<label>Conditional branch<select data-sa="branch" data-arm="${key}">${cases.map((c,i)=>`<option value="${i}">${esc(c.finding)} · ${esc(c.mechanism_hypothesis)} · ${c.restoration_hypothesis?'restored hypothesis':'still impaired hypothesis'} · weight ${num(c.probability)}</option>`).join('')}</select></label>`;
            cases.forEach((c,i)=>{
                const branch=arm.process?.branches?.find(b=>b.branch_id===c.branch_id),prediction=branch?.predicted;
                const pair={baseline:{summary:{prediction}},alternative:{summary:{prediction:null}}};
                html+=`<section data-sa-branch="${key}-${i}" ${i?'hidden':''}><p>Finding: ${esc(c.finding)}. Conditional procedure: ${esc(c.requested_remedy)}. Operating test: H${num(c.test_start_hour)}–H${num(c.test_end_hour)}${Number.isFinite(c.test_target_kw)?' at '+num(c.test_target_kw)+' kW':''}.</p><p>${esc(c.ending_diagnostic_state)}. ${esc(c.required_followup)}</p>`;
                if(prediction)html+=`<p>Predicted methane ${num(prediction.methane_kg)} kg · starts ${num(prediction.reactor_starts)} · service decision cost €${num(branch.service_decision_eur)}.</p>${plot(pair).replace('Baseline solid; alternative dashed.','Selected branch, solid line.').replace('baseline solid line, alternative dashed line','selected conditional branch')}`;
                else html+='<p>No validated process trajectory for this branch. Its conditions are retained above.</p>';
                html+=`<p>Unselected requests: ${esc((c.unselected_requests||[]).map(o=>o.id).join(', ')||'None recorded')}. Outstanding retrieval/readiness obligations: ${esc((c.outstanding_recovery||[]).map(o=>o.order_id||o.asset_id||JSON.stringify(o)).join(', ')||'None predicted')}.</p>`;
                html+=`<div class="sa-table"><table><thead><tr><th>Conditional ending service stock</th><th>Amount</th></tr></thead><tbody>${Object.entries(c.conditional_ending_service_stocks||{}).map(([k,v])=>`<tr><th>${esc(k)} / ${esc(a.service_stock_units?.[k]||'unit not recorded')}</th><td>${num(v)}</td></tr>`).join('')}</tbody></table></div></section>`;
            });
        }
        html+='<h4>Recorded original predictions</h4>';
        for(const [name,arm] of Object.entries(a.recorded.strategies||{}))html+=`<p>${esc(name)} · ${esc(arm.status)} · ${num(arm.process?.expected?.methane_kg)} kg expected methane · ${esc(arm.process?.solver?.status||'No validated process plan')}.</p>`;
        html+=`<p>${esc(a.context_note)}</p><p>Forecast ${esc(a.forecast_source.id)} · available ${esc(a.forecast_source.available_at)}.</p><p>Original process prices ${esc(a.original_prices?.process)} · original service prices ${esc(a.original_prices?.service)}.</p><p>Objective ${esc(a.objective)} · declared risk weight ${num(a.risk_weight)}.</p><p>Assumption source ${esc(a.comparison.inputs?.belief?.assumptions?.source)}. These weights are illustrative, not calibrated failure rates.</p><p>Original source ${esc(a.original_source||'Missing')}<br>Replanner ${esc(a.replanner_source)}<br>Original selection ${esc(a.selection_id)}<br>Comparison ${esc(a.comparison_id)}</p></section>`;
        node.innerHTML=html;
    }
    host.addEventListener('click',e=>{e.stopPropagation();const action=e.target.closest('[data-sa]')?.dataset.sa;if(action==='open'){if(opened)close();else open();}if(action==='close')close();if(action==='origin'){cancel();seekDecision?.(description.investigation.origin_hour);q('[data-sa=close]')?.focus({preventScroll:true});}if(action==='cancel'){cancel();context=next();status('Calculation cancelled. Previous results remain labelled with their earlier inputs.');}if(action==='details'){const el=q('[data-sa=evidence]');el.hidden=!el.hidden;e.target.setAttribute('aria-expanded',String(!el.hidden));}});
    host.addEventListener('submit',e=>{e.preventDefault();e.stopPropagation();calculate();});
    host.addEventListener('input',e=>{e.stopPropagation();if(e.target.closest('form'))changed();});
    host.addEventListener('change',e=>{e.stopPropagation();if(e.target.dataset.sa==='branch'){const arm=e.target.dataset.arm;for(const el of host.querySelectorAll(`[data-sa-branch^="${arm}-"]`))el.hidden=el.dataset.saBranch!==`${arm}-${e.target.value}`;}if(e.target.dataset.sa==='kind'){parameters();changed();}if(e.target.dataset.sa==='robot'){reserveDefaults();changed();}if(q('[data-sa=kind]')?.value==='procedure'){if(e.target.dataset.sa==='order'){procedures();changed();}if(e.target.dataset.sa==='procedure'){procedureScope();changed();}}});
    host.addEventListener('keydown',e=>{if(e.key==='Escape'&&!opened)return;e.stopPropagation();if(e.key==='Escape'&&opened){e.preventDefault();close();}});
    return {sync,close,isOpen:()=>opened};
}
if(typeof module!=='undefined')module.exports={serviceAlternativeKey,serviceAlternativeRows,investigationAlternativeRows,createServiceAlternatives};
