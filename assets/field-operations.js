/* Render recorded service state; all quantities and costs are calculated in Python. */
function renderFieldOperations(result, frame, costs, visual) {
    const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const n = (v,d=2) => Number.isFinite(v) ? v.toLocaleString('en-GB',{maximumFractionDigits:d}) : '—';
    const model=result.field_operations_model, record=frame.row?.field_operations;
    const underway=visual?.underway?visual.actors.filter(a=>['travel','perform','verify','return'].includes(a.phase)):[];
    const live=underway.length?`<p>In progress during H${frame.hour} → H${frame.hour+1}: ${underway.map(a=>esc(a.kind+' · '+a.phase+' · '+a.order)).join('; ')}.</p><p class="m-muted">Animation uses recorded starting work orders. Completed quantities below stop at H${frame.hour}; work outcomes are not yet available.</p>`:'';
    if(!record)return `<h3>Site services</h3>${live}<p>${frame.hour===0&&result.config.field_operations?.enabled?'Step forward to inspect an executed interval. Robots start with the full battery inventories declared in setup.':'This run has no recorded field operations. Enable the service layer in experiment setup, or choose a field-services preset.'}</p><p>${esc(result.config.faults?.lifecycle||'Archived timed fault behaviour')} · ${esc(result.config.faults?.capacity_cause||'Original fault assumptions')}</p><button data-do="setup">Experiment setup ↗</button>`;
    const state=record.state, orders=state.orders, active=orders.filter(o=>o.status==='active');
    const diagram=`<svg class="m-service-diagram" viewBox="0 0 400 160" role="img" aria-label="Declared routes connect the dock to the solar array and electrolyser. No navigation physics is simulated.">
        <g fill="none" stroke="currentColor" stroke-width="1.3"><path d="M76 67H165V33H297M165 67V125H297" stroke-dasharray="3 5"/>
        <path d="M20 45H75V92H20ZM27 51H67V82H27M44 36V45M53 36V45M37 60H55M46 60V75"/>
        <path d="M300 10H370L384 44H288ZM308 10L301 44M325 10V44M348 10L357 44M296 27H377M312 44V56M362 44V56M305 56H370"/>
        <path d="M297 96H374V144H297ZM307 101V138M317 101V138M327 101V138M337 101V138M347 101V138M357 101V138M292 117H280M374 117H387"/>
        <g class="m-service-rover" data-active="${active.some(o=>o.robot==='rover')}"><path d="M192 94H232L239 112H188ZM210 94V78H225V86H213M194 104H229"/><circle cx="197" cy="117" r="5"/><circle cx="230" cy="117" r="5"/></g>
        <g class="m-service-cleaner" data-active="${active.some(o=>o.robot==='cleaner')}"><path d="M197 19H241V35H197ZM201 15V39M208 15V39M215 15V39M222 15V39M229 15V39M236 15V39"/></g></g>
        <g fill="currentColor" font-size="9"><text x="22" y="108">DC DOCK</text><text x="288" y="70">SOLAR</text><text x="290" y="158">ELECTROLYSER</text></g></svg>`;
    const fact=(key,value)=>`<div class="m-fact"><span>${esc(key)}</span><strong>${esc(value)}</strong></div>`;
    let out=`<h3>Site services</h3>${live}<p class="m-muted">${esc(record.version)} · recorded through H${frame.hour}</p>${diagram}`;
    const beliefs=record.decision?.uncertainty_beliefs;
    if(beliefs){out+='<h4>What remains uncertain</h4><p>'+esc(beliefs.scope)+'</p>';for(const [key,v] of Object.entries(beliefs.durations)){if(v.completed_phases||v.censored_phases)out+=fact(key+' time · estimate / support',n(v.mean_factor,2)+'× / '+n(v.bounds[0],2)+'–'+n(v.bounds[1],2)+'×')+fact('Observed / unfinished phases',n(v.completed_phases,0)+' / '+n(v.censored_phases,0))+fact('Evidence',v.status);}for(const [key,v] of Object.entries(beliefs.reliability))out+=fact(key+' · completed / interrupted',n(v.returned,0)+' / '+n(v.interrupted,0))+fact('Recovery awaiting verification',n(v.pending_verifications,0));}
    if(record.performance_update){const u=record.performance_update;out+='<h4>Learning from this service</h4>'+fact('Expected removal / revised estimate',n(u.before*100)+'% / '+n(u.after*100)+'%')+fact('Observed removal',u.estimated_removal==null?u.status:n(u.estimated_removal*100)+'%')+'<p>'+esc(u.inputs.basis)+'. An ineffective pass does not identify its mechanical cause. Available to planning from H'+n(u.available_at,0)+'.</p>'; }
    out+=fact('Dock electricity / this interval',n(record.charge_input_kwh)+' kWh')+fact('Charging loss',n(record.charging_loss_kwh)+' kWh')+fact('Robot consumption',n(record.robot_use_kwh)+' kWh');
    if(record.fixed_service_kwh!==undefined)out+=fact('Fixed service electricity',n(record.fixed_service_kwh)+' kWh')+fact('Service requested / applied',n(record.requested_service_kwh)+' / '+n(record.applied_service_kwh)+' kWh');
    if(record.standby)out+=fact('Dock controls / electricity',n(record.standby.applied_kwh)+' kWh supplied · '+n(record.standby.unserved_kwh)+' kWh unserved')+fact('Dock controls',record.standby.control_available?'Powered':'Unavailable');
    if(state.cleaning_policy){const p=state.cleaning_policy;out+=fact('Local cleaning rule',p.mode);for(const s of p.schedules)out+=fact(s.section+' / cleaning due','H'+n(s.next_due_hour)+' · '+n(s.completed_passes,0)+' full passes'+(s.overdue_hours>0?' · '+n(s.overdue_hours)+' h overdue':''));out+='<p class="m-muted">'+esc(p.scope)+'</p>';}
    if(state.inspection_interface)out+=fact('Contact inspection access',state.inspection_interface.accessible?'Accessible test port':'Enclosed contact / incompatible with installed reader')+'<p class="m-muted">'+esc(state.inspection_interface.scope)+'</p>';
    for(const [robot,value] of Object.entries(state.robots))if(record.assets[robot])out+=fact(robot+' energy',n(value.energy_kwh)+' kWh · '+value.status);
    out+=fact('Available-DC soiling loss',n(record.soiling_loss_kw)+' kW')+fact('Service / cleaning kits remaining',state.service_kits+' / '+state.cleaning_kits);
    out+='<p class="m-muted">Travel and tool poses illustrate recorded work phases; routes and repair mechanics are schematic. Select hardware in the plant to inspect it. A completed service still requires operating verification.</p>';
    out+='<p>'+Object.entries({dock:'Service dock',rover:'Inspection rover',cleaner:'Solar cleaner',human:'Service vehicle',fixed_reader:'Fixed contact reader',portable:'Portable cleaner'}).filter(([k])=>k==='portable'?visual?.actors.some(a=>a.portableWork&&a.visible):k==='human'?orders.some(o=>['human-service','module-replacement','flow-calibration','retrieve','restock','replace-brush','routine-service','portable-cleaning'].includes(o.kind)&&o.status!=='queued'):record.assets[k]).map(([k,label])=>`<button data-field-locate="${k}">Find ${label} ↗</button>`).join(' ')+'</p>';
    if(state.portable){out+=fact('Portable '+state.portable.method+' cleaner',state.portable.status)+fact('Water / this interval',n(record.water_used_l)+' L')+fact('Cleaning water remaining',n(state.portable.water_l)+' L')+fact('Portable tool use / this interval',n(record.portable_hours)+' h');out+='<p class="m-muted">'+esc(state.portable.ownership)+'. Wet treatment can remove the configured adhered fraction; damage is unchanged.</p>'; }
    if(state.inspection){
        const info=state.inspection;
        out+='<section class="m-inspection-evidence"><h4>Contact evidence</h4>'+fact('Interpretation',info.quality+' · '+(info.value===null?'unresolved':info.value?'latched':'not latched'))+'<p>'+esc(info.reason)+'</p>';
        out+='<table><thead><tr><th>Reader</th><th>Signal / V</th><th>Zero / V</th><th>Span / V</th><th>Evidence</th></tr></thead><tbody>'+info.channels.map(c=>`<tr><td>${esc(c.reader)}</td><td>${c.raw_v?.signal==null?'—':n(c.raw_v.signal,2)}</td><td>${c.raw_v?.zero==null?'—':n(c.raw_v.zero,2)}</td><td>${c.raw_v?.span==null?'—':n(c.raw_v.span,2)}</td><td>${esc(c.quality)}</td></tr>`).join('')+'</tbody></table>';
        for(const c of info.channels)out+='<p>'+esc(c.reader)+': '+esc(c.reason)+(c.measured_at!==undefined?' · measured H'+n(c.measured_at,2)+', available H'+n(c.available_at,2):'')+'.</p>';
        out+='<p class="m-muted">'+esc(info.scope)+'</p></section>';
    }
    if(state.support){
        if(state.support.crew_return)out+='<h4>Returning interrupted crews</h4><p class="m-muted">'+esc(state.support.crew_return.scope)+'</p>';
        out+=fact('Crew commitment / this interval',n(record.crew_committed_hours)+' h')+fact('Remote supervision / this interval',n(record.remote_hours)+' h');
        out+=fact('Crew / remote allowance remaining',n(state.support.crew_hours_remaining)+' / '+n(state.support.remote_hours_remaining)+' h');
        out+='<p class="m-muted">'+esc(state.support.calendar_basis)+'. Retrieval brings an aborted mission home; only a subsequent observed drive test makes the robot available again.</p>';
        out+='<p>Upstream supply: '+Object.entries(state.support.upstream).map(([k,v])=>esc(k)+' '+n(v,0)+' '+esc(state.support.upstream_units?.[k]||'kit')).join(' · ')+'. On-site brush spares: '+n(state.support.brush_spares,0)+'.</p>';
        for(const effect of record.support_effects||[])out+='<p>'+esc(effect.kind)+' · '+esc(effect.order_id)+' · effective H'+n(effect.effective_at)+ (effect.kind==='restock'?' · accepted '+n(effect.accepted)+' / rejected '+n(effect.rejected)+' '+esc(effect.material)+' '+esc(effect.unit||'kit'):'')+'</p>';
        if(state.support.maintenance){const m=state.support.maintenance;out+='<h4>Scheduled routine work</h4>';for(const s of m.schedules)out+=fact(s.target+' / next due','H'+n(s.next_due_hour)+' · '+n(s.completed_count,0)+' completed'+(s.overdue_hours>0?' · '+n(s.overdue_hours)+' h overdue':''));out+='<p class="m-muted">'+esc(m.scope)+'</p>';}
        if(state.support.equipment){
            out+='<section class="m-hardware-evidence"><h4>Service hardware recovery</h4>';
            for(const e of state.support.equipment.incidents)out+='<article class="m-service-order"><strong>'+esc(e.target)+' · '+esc(e.state)+'</strong><p>'+esc(e.reason)+'</p><p class="m-muted">Observed incident '+esc(e.id)+' · opened H'+n(e.opened_at)+'. Original work '+esc(e.origin_order)+'.</p></article>';
            out+='<p>Compatible spares: '+Object.entries(state.support.hardware_spares||{}).map(([k,v])=>esc(k)+' '+n(v,0)).join(' · ')+'.</p><p class="m-muted">'+esc(state.support.equipment.limit)+'</p></section>';
        }
    }
    if(record.surface_after){
        out+=fact('Area treated / this interval',n(record.treated_area_m2)+' m²')+fact('Brush usable area remaining',n(record.brush_after_m2)+' m²');
        out+='<p class="m-muted">Dry brushing removes loose material only. Compatible wet treatment can also reduce adhered fouling; permanent damage persists. Surface effects enter conversion before clipping; more captured light need not produce more available electricity.</p>';
        out+='<table><thead><tr><th>Section</th><th>Loose</th><th>Adhered</th><th>Damage</th></tr></thead><tbody>'+(state.surface?.sections||[]).map(s=>`<tr><td>${esc(s.id)}</td><td>${n(s.removable_fraction*100)}%</td><td>${n(s.adhered_fraction*100)}%</td><td>${n(s.damage_fraction*100)}%</td></tr>`).join('')+'</tbody></table>';
    }
    if(state.executive?.visits?.length){
        out+='<section class="m-visit-evidence"><h4>Shared crew visits</h4>';
        for(const v of state.executive.visits){
            out+='<article class="m-service-order"><strong>'+esc(v.visit_id)+' · '+esc(v.status)+'</strong>';
            out+='<p>Planned H'+n(v.starting_at)+' → H'+n(v.planned_return_at)+' · '+n(v.planned_crew_hours)+' crew-hours. '+(v.returned_at==null?'Return not established.':'Returned H'+n(v.returned_at)+'.')+'</p>';
            out+='<ol>'+v.planned_jobs.map(j=>'<li>'+esc(j.order_id)+' · '+esc(j.action)+' · planned H'+n(j.starting_at)+' → H'+n(j.ending_at)+'</li>').join('')+'</ol>';
            if(v.interruption)out+='<p>'+esc(v.interruption)+'</p>';
            out+='<p class="m-muted">'+esc(v.reason)+'. Each job retains its own acceptance test.</p></article>';
        }
        out+='</section>';
    }
    const control=record.decision?.service_control;
    const recovery=frame.row?.decision?.recovery_planning;
    if(recovery?.version==='scheduled-load-tests/2'&&recovery.status!=='inactive'){
        out+='<details class="m-recovery-commitment"><summary>Reserved recovery test</summary><p>'+esc(recovery.status)+'</p>';
        const c=recovery.commitment;
        if(c)out+=fact('Accepted window','H'+n(c.start_hour)+' → H'+n(c.end_hour))+fact('Requested load',n(c.target_kw)+' kW')+fact('Original deadline','H'+n(c.due_hour));
        else if(recovery.due_hour!=null)out+=fact('Original deadline','H'+n(recovery.due_hour));
        for(const reason of recovery.commitment_changes||[])out+='<p>'+esc(reason)+'</p>';
        out+='<p class="m-muted">Work, dock charging and load tests share this prediction. A reserved or performed test does not establish recovery; actual operating observations must confirm it.</p></details>';
    }
    if(control){
        if(control.investigation){
            const i=control.investigation;
            out+='<details class="m-investigation"><summary>Investigation and recovery</summary><p>Decisions use returned observations. Predicted restoration probabilities are assumptions; only operating observations can confirm recovery.</p>';
            for(const e of i.episodes||[]){
                out+='<article><h4>'+esc(e.id)+' · '+esc(e.status)+'</h4>'+fact('Original deadline','H'+n(e.due_hour))+fact('Requested work',(e.requests||[]).join(', ')||'None')+'<p>'+esc(e.reason||e.prior_scope)+'</p>';
                if(e.selection){for(const c of e.selection.candidates||[])out+='<p>'+esc(c.strategy)+' · '+esc(c.status)+' · assumed restoration probability '+n(c.restoration_probability*100)+'% · '+(c.eligible?'eligible under the recorded requirement':'not eligible')+'</p>';out+='<p>Selected: '+esc(e.selection.selected?.strategy||'unresolved')+'. Original calculation '+esc(e.selection.selection_id)+'.</p><p class="m-muted">Archive path: '+esc(e.selection.full_calculation_path||'See the recorded investigation selection')+'</p>';}
                if(e.finding)out+='<p>Returned finding: '+esc(e.finding.reason)+'</p>';
                if(e.belief_after_intervention)out+='<p>'+esc(e.belief_after_intervention)+'</p>';
                if(e.recovery_belief){const b=e.recovery_belief;out+='<p>Recovery belief: '+esc(b.status)+' · '+(b.restoration_probability==null?'probability unavailable':n(b.restoration_probability*100)+'% assumed restoration')+'. '+esc(b.reason||'Actual operating confirmation remains separate.')+'</p><p class="m-muted">Impaired-capacity assumption '+n(b.inputs.impaired_capacity_kw)+' kW; procedure reliability '+n(b.inputs.success_probability*100)+'%. '+esc(b.scope)+'</p>';}
                if(e.followup_belief_gate){const g=e.followup_belief_gate;out+='<p>Follow-up decision at H'+n(g.at_hour)+' after '+esc(g.after_order_id)+': '+(g.eligible?'probability requirement met':'probability requirement unmet')+' · '+(g.impairment_probability==null?'impairment probability unavailable':n(g.impairment_probability*100)+'% assumed impairment')+'; threshold '+n(g.threshold*100)+'%. Repeated feasible shortfalls are also required.</p>';}
                if(e.test_obligation){const t=e.test_obligation;out+='<p>Operating follow-up: '+esc(e.continuation_status)+' · after '+esc(t.work_order_id)+'. '+(t.predicted_test_start==null?'Based on actual post-service evidence.':'Original conditional test: H'+n(t.predicted_test_start)+' at '+n(t.test_target_kw)+' kW.')+'</p>';if(e.accepted_test)out+='<p>Accepted H'+n(e.accepted_test.start_hour)+' → H'+n(e.accepted_test.end_hour)+' at '+n(e.accepted_test.target_kw)+' kW; work/return prerequisite H'+n(e.accepted_test.not_before_hour)+'. Recovery remains unverified until actual tracking.</p>';}
                if(e.continuation_error)out+='<p>Continuation unresolved: '+esc(e.continuation_error)+'</p>';
                if(e.confirmed_at!==undefined)out+='<p>Observer confirmation at H'+n(e.confirmed_at)+'.</p>';
                out+='</article>';
            }
            out+='<p class="m-muted">'+esc(i.scope)+'</p></details>';
        }
        out+='<section><h4>Recorded service decision</h4><p>'+esc(control.status)+' · '+esc(control.selected_candidate_id||'current feasible fallback')+'</p>';
        out+='<p class="m-muted">'+esc(control.scope)+'</p>';
        if(control.unmet_deadlines?.length)out+='<p>Unmet work deadlines: '+esc(control.unmet_deadlines.join(', '))+'.</p>';
        for(const task of control.obligations||[])out+='<p>'+esc(task.id)+' · '+esc(task.kind)+' · '+esc(task.status)+' · original deadline H'+n(task.due_hour)+' · '+n(task.attempts.length,0)+' attempt(s)'+(task.deadline_missed_at==null?'':'; missed at H'+n(task.deadline_missed_at))+'.</p>';
        for(const target of Object.values(control.energy_targets||{}))out+='<p>'+esc(target.robot)+': '+n(target.energy_kwh)+' kWh required by original H'+n(target.due_hour)+'.</p>';
        if(control.verification){
            const v=control.verification, test=v.previous_test;
            out+='<details class="m-load-verification"><summary>Post-service load tests</summary><p>Actual measured tests at decision H'+n(v.at_hour)+'. A completed procedure does not establish recovery.</p>';
            for(const a of v.attempts)out+='<p>'+esc(a.order_id)+' · '+esc(a.status)+' · '+n(a.qualifying.length,0)+' qualifying test(s), '+n(v.required_tests,0)+' required within '+n(v.maximum_age_hours)+' h. '+esc(a.reason||'')+'</p>';
            if(test){const p=test.inputs.packet, o=test.operands;out+='<p>H'+n(p.hour)+' → H'+n(p.available_at)+': '+esc(test.outcome)+'. '+esc(test.reason)+'.</p>'+fact('Requested / measured power',n(o.requested_kw)+' / '+n(o.measured_kw)+' kW')+fact('Hydrogen balance / electrical estimate',n(o.balance_hydrogen_kg)+' / '+n(o.expected_hydrogen_kg)+' kg')+fact('Resource check',test.resource_check.status)+'<p class="m-muted">'+esc(test.scope)+'</p><pre>'+esc(JSON.stringify(test,null,2))+'</pre>';}
            out+='</details>';
        }
        out+='<details><summary>Candidate calculations</summary>';
        for(const candidate of control.candidates||[]){const e=candidate.evaluation,p=e?.process_plan?.predicted;out+='<p>'+esc(candidate.candidate_id)+' · '+esc(candidate.status)+(p?' · predicted '+n(p.methane_kg)+' kg CH₄; incremental mission cost €'+n(e.mission_decision_eur):'')+'</p>';for(const c of e?.constraints||[])out+='<p class="m-muted">'+esc(c.reason||c.condition)+'</p>';}
        out+='<p>Source calculation '+esc(control.input_id)+'. These are predictions at the selected decision, not later realised outcomes.</p></details></section>';
    }
    out+='<h4>Work orders</h4>';
    out+=orders.length?orders.map(o=>`<article class="m-service-order"><strong>${esc(o.id)} · ${esc(o.kind)}${o.section?" · "+esc(o.section):""}</strong><p>${esc(o.status)} · ${esc(o.phase)}${o.status==='active'?' · '+n(o.remaining,2)+(record.version?.startsWith('plant-service-contracts/')?' h remaining in mission':' h remaining in phase'):''}</p><p class="m-muted">${esc(o.reason)}</p>${o.retrieved_at!==undefined?`<p>Hardware returned at H${n(o.retrieved_at)}; the original failed work remains recorded.</p>`:''}${o.blocked?`<p>${esc(o.blocked)}</p>`:''}${o.reported?`<p>${esc(typeof o.reported==='string'?o.reported:JSON.stringify(o.reported))}</p>`:''}</article>`).join(''):'<p>No work requested.</p>';
    const c=costs?.field_operations;
    if(c?.views){const money=v=>v==null?'Unpriced':'€'+n(v);out+='<div class="m-cost"><h4>Service costs / elapsed period</h4>';for(const [key,label] of [['allocated','Period allocation'],['decision','Action-dependent costs'],['expenditure','Modelled expenditure']]){const v=c.views[key];out+=fact(label,money(v.total_eur));if(v.unpriced.length)out+='<p>Known subtotal '+money(v.known_subtotal_eur)+'. Missing '+esc(v.unpriced.join(', '))+'.</p>';}out+=fact('Crew hours',n(c.quantities['crew-hours']||0))+fact('Remote hours',n(c.quantities['remote-hours']||0))+'<p class="m-muted">'+esc(c.basis)+'</p><details><summary>Accounting boundaries</summary>'+c.boundaries.map(t=>'<p>'+esc(t)+'</p>').join('')+'</details><button data-model-topic="economics" data-model-context="This run">Trace service costs</button></div>';}else if(c){out+='<div class="m-cost"><h4>Service costs / elapsed period</h4>';for(const [key,v] of Object.entries(c.components))out+=fact(key.replaceAll('_',' '),'€'+n(v));out+=fact('Allocated services','€'+n(c.total_eur))+fact('Variable inputs and usage wear','€'+n(c.variable_and_wear_eur))+'<p class="m-muted">'+esc(c.basis)+'</p>';for(const q of c.unpriced||[])out+='<p>Unpriced: '+n(q.amount)+' '+esc(q.unit)+' '+esc(q.quantity.replaceAll('_',' '))+'. '+esc(q.reason)+'.</p>';out+='</div>';}
    out+=`<details><summary>Mechanics, assumptions and recorded calculation</summary><p>${esc(model?.timing)}</p><p>${esc(model?.power_policy)}</p><p>${esc(model?.solar_scope)}</p><ul>${(model?.assumptions||model?.limitations||[]).map(x=>'<li>'+esc(x)+'</li>').join('')}</ul><p>Physical fault outcomes are available only in the retrospective Truth view. Work completion and operating verification are separate events.</p><p>Run ${esc(result.run_id)} · record /records/[selected controller]/${esc(frame.hour-1)}/field_operations. Model identity and source bytes are retained in the run archive.</p><pre>${esc(JSON.stringify({energy_before_kwh:record.energy_before_kwh,charge_input_kwh:record.charge_input_kwh,charging_loss_kwh:record.charging_loss_kwh,robot_use_kwh:record.robot_use_kwh,energy_after_kwh:record.energy_after_kwh,fixed_service_kwh:record.fixed_service_kwh,standby:record.standby,maintenance:state.support?.maintenance,resource_events:record.resource_events,mission_events:record.mission_events,surface_events:record.surface_events,support_effects:record.support_effects,audits:record.audits},null,2))}</pre></details>`;
    return out;
}
if(typeof module!=='undefined')module.exports={renderFieldOperations};
