/* Rendering only: physics, economics, explanations and replanning live in Python. */
function decodeMethanePayload(value) { return typeof value==='string'?JSON.parse(value):value; }
function methaneSelectionKey(runId, controller, hour, alternative, revision = '') {
    return `${runId}|${controller}|${hour}|${alternative}|${revision}`;
}
function methaneFrame(result, elapsed, controller) {
    const rows = result.records[controller] || [];
    const hour = Math.max(0, Math.min(rows.length, Math.round(elapsed)));
    const row = hour ? rows[hour - 1] : null;
    return {hour, row, controller, decision: rows[Math.max(0, hour - 1)]?.decision, totals: result.frames[controller][hour]};
}
function mountMethane(element, props, watch, trigger) {
    let result = decodeMethanePayload(props.value), costs = decodeMethanePayload(props.economics), selected = null, section = 'Now';
    let controller = 'MPC · methane', clock, pendingKey = null, answer = null, guideIndex = 0, generation = 0;
    let workflow, agentControl, agentOrigin, investigation, investigationOrigin, controlView, controlOrigin, solar, model, taxonomy, studies, sites, project, fieldScene, serviceAlternatives, serviceOrigin=null, renderedKey = "", costRevision = 0, detailRequest = null, utility = null;
    const instanceId = crypto.randomUUID();
    const root = element.querySelector('.methane-console');
    const $ = selector => root.querySelector(selector);
    const $$ = selector => [...root.querySelectorAll(selector)];
    const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
    const num = (value, d = 1) => Number.isFinite(value) ? (Math.abs(value)<Math.pow(10,-d)/2?0:value).toLocaleString('en-GB', {maximumFractionDigits:d, minimumFractionDigits:d}) : '—';
    const money = value => Number.isFinite(value) ? `€${num(value,2)}` : '—';
    const text = (name, value) => { const node=$(`[data-m="${name}"]`); if(node) node.textContent=value; };
    const svgText = (name, value) => { const node=$(`[data-svg="${name}"]`); if(node) node.textContent=value; };
    const labels = {solar:'Solar array',battery:'Battery',electrolyser:'Electrolyser',hydrogen:'Hydrogen buffer',co2:'CO₂ supply',reactor:'Methanator'};
    const alternatives = {battery:'Prevent discharge for this interval',electrolyser:'Keep electrolysis off for this interval',reactor:'Delay a reactor start by one interval',co2:'Delay the next CO₂ delivery by 24 hours'};
    const fact = (label, value) => `<div class="m-fact"><span>${escape(label)}</span><strong>${escape(value)}</strong></div>`;
    const paragraph = value => `<p>${escape(value)}</p>`;
    function current() { return methaneFrame(result, clock?.snapshot().hour || 0, controller); }
    function currentKey(alt=selected) {
        const f=current();
        return methaneSelectionKey(result.run_id,controller,Math.max(0,f.hour-1),alt,`${instanceId}-${generation}`);
    }
    function invalidate() { generation+=1;pendingKey=null;answer=null; }
    function costFrame(hour) {
        return costs?.run_id === result.run_id ? costs.controllers[controller]?.[hour] : null;
    }
    function table(headers, rows) {
        return `<table><thead><tr>${headers.map(h=>`<th>${escape(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(v=>`<td>${escape(v)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
    }
    function closePanels(focus=true) {
        serviceAlternatives?.close(false);
        const previous=selected, origin=serviceOrigin;serviceOrigin=null;
        selected=null;utility=null;invalidate();
        $('.m-utility').hidden=true;$('.m-timeline').hidden=true;
        $('[data-do="menu"]').setAttribute('aria-expanded','false');
        $('[data-do="timeline"]').setAttribute('aria-expanded','false');
        render();
        if(focus)(origin?.isConnected?origin:($(`[data-component="${previous}"]`)||$('[data-do="menu"]'))).focus({preventScroll:true});
    }
    function openUtility(panel='work', origin=null) {
        if(investigation?.isSuspended()){controlView?.close(false);investigation.resume();return;}
        controlView?.close(false);
        clock.pause();closePanels(false);serviceOrigin=origin;utility=panel;root.dataset.chrome='visible';
        $('.m-utility').hidden=false;
        $('[data-do="menu"]').setAttribute('aria-expanded','true');
        $$('[data-utility-section]').forEach(node=>node.hidden=node.dataset.utilitySection!==panel);
        $$('.m-utility-tabs [data-panel]').forEach(node=>node.setAttribute('aria-pressed',String(node.dataset.panel===panel)));
        workflow?.sync();render();
        const tab=$(`.m-utility-tabs [data-panel="${panel}"]`),heading=$(`[data-utility-section="${panel}"] h3`);
        if(heading)heading.setAttribute('tabindex','-1');
        (panel==='tools'?$('[data-work-search]'):tab||heading).focus({preventScroll:true});
    }
    function hideControls() {
        if(investigation?.isSuspended()){controlView?.close(false);investigation.resume();return;}
        controlView?.close(false);
        closePanels(false);root.dataset.chrome='hidden';root.focus({preventScroll:true});
    }
    function selectComponent(key) {
        if(controlView?.isOpen()&&labels[key]){controlView.select(key);return;}
        if(key==='services'){openUtility('services');return;}
        if(!labels[key])return;
        closePanels(false);root.dataset.chrome='visible';
        if(key==='solar'){solar.open();return;}
        selected=key;section='Now';render();
        $('[data-do="close"]').focus({preventScroll:true});
    }
    function loadDetail(f) {
        if(!f.decision)return;
        const row=f.row || result.records[controller]?.[0];
        if(row?.economic_trace?.report_price_version===costs?.report_price_version && row?.economic_trace?.report_service_price_version===costs?.report_service_price_version && f.decision.plan.trajectory)return;
        const key=`${result.run_id}|${controller}|${Math.max(0,f.hour-1)}|${costRevision}`;
        if(detailRequest!==key){detailRequest=key;trigger('select',{run_id:result.run_id,controller,hour:Math.max(0,f.hour-1),prices:costs?.costs,service_prices:costs?.service_economics,key});}
    }
    function inspect(f) {
        const drawer=$('.m-inspector'); drawer.hidden=!selected;
        if(!selected || !f.decision) return;
        const d=f.decision, p=result.config.plant, e=d.evidence, row=f.row;
        const state=row?.observations_after || d.observations, action=row?.applied || {};
        text('asset',result.asset_ids[selected]); text('selected',labels[selected]);
        if(!$('.m-inspector-tabs').children.length)$('.m-inspector-tabs').innerHTML=['Now','Why','Next','Costs','What if'].map(tab=>`<button data-section="${tab}">${tab.toUpperCase()}</button>`).join('');
        $$('[data-section]').forEach(node=>node.setAttribute('aria-pressed',String(node.dataset.section===section)));
        let body='';
        if(section==='Now') {
            const now={
                solar:[['Generation',`${num(row?.pv_kw || 0)} kW`],['Irradiance',`${num(row?.irradiance_wm2 || 0)} W/m²`],['Ambient',`${num(row?.ambient_c ?? state.temperature_c)} °C`],['Humidity',`${num(row?.humidity_pct)} %`],['Unused solar',`${num(row?.curtailed_kwh || 0)} kWh`]],
                battery:[['Stored energy',`${num(Math.max(0,state.battery_kwh))} / ${num(p.battery_kwh,0)} kWh`],['Charging',`${num(action.charge_kw || 0)} kW`],['Discharging',`${num(action.discharge_kw || 0)} kW`],['Interval losses',`${num(row?.battery_loss_kwh || 0)} kWh`]],
                electrolyser:[['Requested',`${num(row?.requested.electrolyser_kw || 0)} kW`],['Delivered',`${num(action.electrolyser_kw || 0)} kW`],['Metered power',`${num(state.power_kw)} kW`],['Flow meter',`${num(state.hydrogen_flow_kg)} kg/h`],['Capacity estimate',`${num(row?.diagnosis_after.capacity_kw ?? d.diagnosis.capacity_kw)} kW`]],
                hydrogen:[['Inventory estimate',`${num(state.h2_inventory_kg)} / ${num(p.h2_capacity_kg,0)} kg`],['Independent outflow meter',`${num(state.h2_outflow_kg)} kg/h`],['Upstream flow meter',`${num(state.hydrogen_flow_kg)} kg/h`],['Usable inlet',`${num(state.usable_hydrogen_inflow_kg ?? state.hydrogen_flow_kg)} kg/h`]],
                co2:[['Inventory',`${num(state.co2_kg)} / ${num(p.co2_capacity_kg,0)} kg`],['Accepted delivery',`${num(row?.co2_delivered_kg || 0)} kg`],['Rejected delivery',`${num(row?.co2_rejected_kg || 0)} kg`],['Consumed',`${num(row?.co2_consumed_kg || 0)} kg`]],
                reactor:[['Temperature',`${num(state.temperature_c)} °C`],['Heating',`${num(action.heater_kw || 0)} kW`],['Reaction heat',`${num(row?.reaction_heat_kwh || 0)} kWh`],...(row?.feed_heating_kwh!==undefined?[['Feed heating',`${num(row.feed_heating_kwh)} kWh`]]:[]),['Heat loss',`${num(row?.heat_loss_kwh || 0)} kWh`],['Heat rejected',`${num(action.cooling_kw || 0)} kWh`],['Commitment remaining',`${state.commitment_hours} h`]]
            };
            body=`<div class="m-facts">${now[selected].map(([k,v])=>fact(k,v)).join('')}</div>`;
            body+=paragraph(f.hour ? `Observed after interval ${f.hour-1}. ${selected==='electrolyser'||selected==='hydrogen' ? row.diagnosis_after.status+' · '+row.diagnosis_after.uncertainty : 'Select WHY for the evidence available before this action.'}` : 'Initial state. Select NEXT to inspect the first recorded decision.');
            if(selected==='hydrogen')body+=paragraph(`Usable inlet source: ${state.hydrogen_inflow_source || 'flow sensor'}. Tank inventory is independently measured; isolation protects flow telemetry.`);
            if(selected==='reactor') body+=paragraph('Analytic hourly heat balance includes exothermic reaction heat. Production requires both the beginning and ending temperature within the operating band.');
            if(selected==='solar') body+=paragraph(`DC conversion: ${num(result.config.weather.loss_fraction*100,0)}% losses; panel temperature = ambient + (NOCT−20) × irradiance / 800. ${result.weather.reference}.`);
        }
        if(section==='Why') {
            const item=e[selected];
            const details={
                solar:`${item.forecast_source?.source || e.solar.forecast_source.source}. Current-hour forecast residual ${num(e.solar.current_error_kw)} kW. Predicted unused solar over this horizon: ${num(e.solar.predicted_curtailment_kwh)} kWh.`,
                battery:`Power is limited to ${num(e.battery.power_limit_kw)} kW; initial stored energy ${num(e.battery.energy_kwh)} kWh. Planned demand exceeds solar by ${num(e.battery.planned_deficit_kwh)} kWh across the horizon.`,
                electrolyser:`Minimum productive load ${num(e.electrolyser.minimum_kw)} kW. Estimated capacity ${num(e.electrolyser.estimated_capacity_kw)} kW. Hydrogen headroom ${num(e.electrolyser.hydrogen_headroom_kg)} kg.`,
                hydrogen:`The plan expects ${num(e.hydrogen.predicted_inflow_kg)} kg from electrolysis and ${num(e.hydrogen.predicted_use_kg)} kg consumed downstream. Each kg methane needs 0.5 kg H₂.`,
                co2:`The plan consumes ${num(e.co2.predicted_use_kg)} kg CO₂. Each kg methane needs 2.75 kg CO₂. Delivery occurs before consumption; tank surplus is explicitly rejected.`,
                reactor:`Production band ${p.temperature_min_c}–${p.temperature_max_c} °C. At this decision: ${num(e.reactor.temperature_c)} °C and ${e.reactor.commitment_hours} hours committed. Reaction heat can sustain production after warm-up.`
            };
            body=paragraph(`RECORDED OBJECTIVE: ${d.policy==='greedy'?'Local downstream priority, then warming, hydrogen and storage':d.policy==='methane'?'Maximise horizon methane; cost and start tie-breaks':'Maximise assumed methane value less variable inputs and usage wear'}`)+paragraph(details[selected]);
            if(selected==='battery') body+=paragraph(`Planned discharge at offsets: ${e.battery.planned_discharge_offsets.length?e.battery.planned_discharge_offsets.map(h=>'+'+h+'h').join(', '):'none'}.`);
            if(selected==='battery'&&e.terminal_battery)body+=paragraph(`Study continuation assumption: ${num(e.terminal_battery.value_kg_ch4_per_kwh,3)} kg CH₄-equivalent per kWh at the planning horizon. Planned ending battery: ${num(e.terminal_battery.predicted_ending_kwh)} kWh. ${e.terminal_battery.note} ${e.terminal_battery.applied_by_optimizer?'Optimized in this decision.':'Fallback used; terminal value was not optimized.'}`);
            if(d.performance_estimates?.solar){const v=d.performance_estimates.solar;body+=paragraph(`Solar performance estimate: ${num(v.before,3)} → ${num(v.after,3)} × nominal conversion. ${v.status}; ${v.informative_intervals} informative intervals. Future planning uses this recorded estimate; current power is observed.`);}
            if(selected==='electrolyser'||selected==='hydrogen') body+=paragraph(`Evidence before dispatch: ${d.diagnosis.status}. Electrical tracking residual ${num(d.diagnosis.tracking_residual*100)}%; flow/balance residual ${num(d.diagnosis.flow_residual*100)}%. ${d.diagnosis.uncertainty}. ${d.probe?'This decision includes a constrained upward capacity probe.':''}`);
            if(e.bindings?.[selected]?.length)body+=paragraph('Binding limits in the first planned interval: '+e.bindings[selected].join('; ')+'.');
            if(selected==='electrolyser'&&d.diagnosis.capacity_kw<p.electrolyser_kw*.999)body+=paragraph(`Recovery needs enough present solar for a load probe, startup and heating; hydrogen headroom; a feasible thermal plan; and ${result.config.sensors.confirmation_hours} successful informative intervals before each capacity increase. An untested load remains uncertain.`);
            body+=e.constraints.length?`<p class="m-annotation">${e.constraints.map(escape).join('<br>')}</p>`:paragraph('No listed initial-state bottleneck. The recorded trajectory shows the combined constraints and trade-offs; no causal importance score is assigned.');
            body+=paragraph(`Solver: ${d.plan.solver.status}; gap ${d.plan.solver.gap==null?'not available':num(d.plan.solver.gap*100,2)+'%'}. Physical limits can reduce the requested action at execution.`);
        }
        if(section==='Next' && !d.plan.trajectory) body=paragraph('Loading the recorded plan…');
        if(section==='Next' && d.plan.trajectory) {
            const pred=d.plan.predicted, end=pred.ending;
            body=`<div class="m-facts">${fact('Predicted methane',num(pred.methane_kg)+' kg')}${fact('Ending H₂ / CO₂',num(end.h2_kg)+' / '+num(end.co2_kg)+' kg')}${fact('Ending battery',num(end.battery_kwh)+' kWh')}${fact('Assumed contribution',money(pred.assumed_contribution_eur))}</div>`;
            body+=paragraph(`PREDICTION / ${d.forecast.pv_kw.length} HOURS. Issued ${d.forecast.source.initialized_at}; available ${d.forecast.source.available_at}. ${d.forecast.source.source}.`);
            const points=pred.temperature_c.map((v,i)=>`${i/Math.max(1,pred.temperature_c.length-1)*900},${80-(v+20)/450*75}`).join(' ');
            body+=`<svg class="m-trajectory" viewBox="0 0 900 85" role="img" aria-label="Predicted reactor temperature"><polyline points="${points}"/></svg>`;
            body+=`<div class="m-prediction">${table(['Offset','PV kW','Ely kW','Battery kWh','H₂ kg','CO₂ kg','Temp °C','CH₄ kg'],d.plan.trajectory.map((r,i)=>['+'+i+'h',num(r.pv_kw),num(r.applied.electrolyser_kw),num(r.state.battery_kwh),num(r.state.h2_kg),num(r.state.co2_kg),num(r.state.temperature_c),num(r.applied.methane_kg)]))}</div>`;
            body+=paragraph('These were predictions at the selected decision, not the later realised trace. Terminal inventories have no assumed resale proceeds.');
        }
        if(section==='Costs') {
            const c=costFrame(f.hour), component=c?.components[selected];
            body=`<div class="m-facts">${fact('Component allocation',money(component))}${fact('Whole plant allocation',money(c?.total_eur))}${fact('Whole plant contribution',money(c?.assumed_contribution_eur))}</div>`;
            body+=paragraph('Illustrative allocated period cost: ownership, maximum of calendar/usage allowance for replaceables, consumables and confirmed-incident budgets. Fixed ownership is excluded from the dispatch objective. Contribution is a separate variable-input and wear-proxy view; do not add it to allocation.');
            const allowance={battery:'battery',electrolyser:'stack',reactor:'reactor'}[selected];
            if(allowance && c) body+=table(['Replaceable allowance','Calendar','Usage','Charged once'],[[allowance,...c.allowances[allowance].map(money)]]);
            body+=paragraph(`Decision costs frozen as ${d.cost_version}. Repricing only changes this report. Ending inventories receive no speculative sales credit. CO₂ is charged on consumption; unused feedstock remains inventory.`);
            body+='<button data-do="setup">EDIT ASSUMPTIONS IN SETUP ↗</button>';
        }
        if(section==='What if') {
            const alt=alternatives[selected];
            if(!alt) body=paragraph('Select the battery, electrolyser, methanator or CO₂ buffer to test a targeted alternative.');
            else {
                body=paragraph(alt)+paragraph('Playback pauses. Replanning uses the original state estimate, forecast vintage and frozen costs. The completed run stays unchanged.');
                body+=`<button data-do="whatif" ${pendingKey===currentKey()?'disabled':''}>${pendingKey===currentKey()?'REPLANNING…':'REPLAN ALTERNATIVE →'}</button>`;
                if(answer?.key===currentKey()) {
                    body+=paragraph(answer.note);
                    const a=answer.alternative_plan.predicted,b=answer.original;
                    if(a) body+=table(['Predicted outcome','Original','Alternative'],[['Methane kg',num(b.methane_kg),num(a.methane_kg)],['Reactor starts',b.reactor_starts,a.reactor_starts],['Ending battery kWh',num(b.ending.battery_kwh),num(a.ending.battery_kwh)],['Ending H₂ kg',num(b.ending.h2_kg),num(a.ending.h2_kg)],['Ending CO₂ kg',num(b.ending.co2_kg),num(a.ending.co2_kg)],['Ending temperature °C',num(b.ending.temperature_c),num(a.ending.temperature_c)],['Variable inputs + wear €',money(b.variable_and_wear_eur),money(a.variable_and_wear_eur)],['Contribution €',money(b.assumed_contribution_eur),money(a.assumed_contribution_eur)]]);
                    body+=paragraph(`Original solver: ${answer.original_solver.status}, gap ${answer.original_solver.gap==null?'unavailable':num(answer.original_solver.gap*100,2)+'%'}. Alternative: ${answer.alternative_plan.solver.status}, gap ${answer.alternative_plan.solver.gap==null?'unavailable':num(answer.alternative_plan.solver.gap*100,2)+'%'}. ${answer.alternative_plan.solver.message || ''}`);
                    body+=paragraph('Predictions are subject to these solver limits. A nonbinding restriction can still yield a different time-limited plan.');
                    if(a) body+=`<div class="m-prediction">${table(['Offset','Original °C','Alternative °C'],b.temperature_c.map((v,i)=>['+'+i+'h',num(v),num(a.temperature_c[i])]))}</div>`;
                    else body+=paragraph('No feasible incumbent was returned. The operating commitment or the alternative restriction may be infeasible; a time limit can also prevent finding a solution.');
                }
            }
        }
        if(selected==='reactor') {
            const spec=result.provenance_summary?.components?.reactor || result.component_specs?.reactor;
            body+=`<details class="m-model-evidence"><summary>MODEL AND EVIDENCE</summary>${paragraph((result.provenance_summary?.components?'RECORDED MODEL: ':'CURRENT REFERENCE; ARCHIVED MODEL VERSION UNAVAILABLE: ')+(spec?.model_id||'reactor')+' / '+(spec?.version||'unknown'))}${paragraph(spec?.validation||'Legacy model provenance unavailable')}${paragraph((spec?.assumptions||[]).join(' · '))}${paragraph('Checks: '+(row?.audit_summary?.passed??0)+' / '+(row?.audit_summary?.total??0)+'. Provenance: '+(result.provenance_summary?.status||'unavailable'))}${paragraph('Thermal inputs: '+num(row?.ambient_c??state.temperature_c)+' °C ambient; '+num(action.heater_kw||0)+' kW heating; '+num(action.methane_kg||0)+' kg methane in interval.')}${row?.audits?.length?table(['Retrospective physical check','Residual','Tolerance','Unit'],row.audits.filter(a=>a.component==='reactor').map(a=>[a.check_id,num(a.residual,8),num(a.tolerance,8),a.unit])):''}<a href="/gradio_api/file=docs/components.md" target="_blank" rel="noopener">COMPONENT REFERENCE ↗</a></details>`;
        }
        if(selected==='battery' && section==='Now') {
            const trace=row?.battery_trace;
            let detail=paragraph(f.hour ? 'Loading recorded battery lineage…' : 'Initial energy is capacity × configured initial SOC. Step forward to inspect an executed interval.');
            if(f.hour && trace?.status==='unavailable') detail=paragraph(trace.note);
            if(f.hour && trace?.status==='recorded') {
                detail=paragraph(`RECORDED MODEL: ${trace.model.model_id} / ${trace.model.model_version} · ${trace.model.implementation_id}`)
                    +paragraph(`${trace.asset_id} · interval ${trace.hour} · ${trace.controller}`)
                    +table(['Quantity','Value','Unit'],trace.nodes.map(n=>[n.label,num(n.value,6),n.unit]))
                    +paragraph(trace.nodes.find(n=>n.id==='end').formula)
                    +paragraph(`Requested charge / discharge: ${num(trace.requested.charge_kw)} / ${num(trace.requested.discharge_kw)} kW. Applied values appear above.`)
                    +table(['Check','Passed','Residual','Tolerance'],trace.audits.map(a=>[a.check_id,a.passed?'yes':'NO',num(a.residual,8),num(a.tolerance,8)]))
                    +`<details><summary>INPUT PATHS AND SOURCE</summary>${table(['Quantity','Source / parents'],trace.nodes.map(n=>[n.label,n.source+' · '+n.parents.join(', ')]))}${paragraph('Run: '+trace.run_id)}${paragraph('Decision: '+trace.decision_path)}${paragraph('Record SHA-256: '+trace.record_sha256)}${paragraph(trace.implementation_file+' SHA-256: '+trace.implementation_file_sha256)}${paragraph('Source content: '+trace.source_content_hash)}</details>`
                    +paragraph(trace.note);
            }
            body+=`<details class="m-battery-trace"><summary>TRACE THIS RESULT</summary>${detail}<a href="/gradio_api/file=docs/components.md" target="_blank" rel="noopener">COMPONENT REFERENCE ↗</a></details>`;
        }
        if(selected!=='battery' && section==='Now') {
            const trace=row?.component_traces?.[selected];
            let content=paragraph(f.hour?'Loading recorded lineage…':'Step forward to inspect an executed interval.');
            if(trace?.status==='unavailable')content=paragraph(trace.note);
            if(trace?.status==='recorded') content=paragraph(`${trace.model.model_id} / ${trace.model.model_version} · ${trace.model.implementation_id}`)
                +paragraph(trace.note)
                +table(['Observed channel','Value','Unit'],trace.observed_nodes.map(n=>[n.label,num(n.value,6),n.unit]))
                +`<details><summary>RETROSPECTIVE EXECUTION AND INPUTS</summary><pre>${escape(JSON.stringify(trace,null,2))}</pre></details>`;
            body+=`<details class="m-component-trace"><summary>TRACE THIS RESULT</summary>${content}</details>`;
        }
        if(section==='Costs') {
            const trace=row?.economic_trace;
            body+=paragraph(`Report price version: ${costs?.report_price_version||'unavailable'}.`);
            body+=`<details class="m-cost-trace"><summary>TRACE COSTS AND TOTALS</summary><pre>${escape(trace?JSON.stringify({economics:trace,physical_totals:row.derived_trace},null,2):'Loading the recorded cost basis…')}</pre></details>`;
        }
        body+=`<nav class="d-inspector-links"><button data-explore="${selected}">Explore component</button><button data-model-topic="${selected}">How it is modelled</button><button data-model-topic="${section==='Costs'?'economics':selected}" data-model-context="This run">Trace calculation</button></nav>`;
        if(result.study_origin?.kind==='site-study')body+='<nav class="d-inspector-links"><button data-do="project-revise">Revise this design</button></nav>';
        if(row?.lifecycle&&['solar','battery','electrolyser','reactor'].includes(selected))body+=`<nav class="d-inspector-links"><button data-model-topic="deployment" data-model-context="This run">Commissioning record</button>${['solar','electrolyser'].includes(selected)?'<button data-model-topic="condition" data-model-context="This run">Condition & maintenance</button>':''}</nav>`;
        $('.m-inspector-content').innerHTML=body;
    }
    function render() {
        if(!result || !clock) return;
        fieldScene?.render(clock.visualSnapshot());
        controlView?.sync();
        const f=current(), p=result.config.plant, row=f.row, d=f.decision;
        if(selected || solar?.needsDetail())loadDetail(f);
        root.dataset.playing=String(clock.snapshot().playing);
        $('[data-do="play"]').textContent=clock.snapshot().playing?'Ⅱ':'▶';
        $('[data-do="play"]').setAttribute('aria-label',clock.snapshot().playing?'Pause simulation':'Play simulation');
        $('[data-m="scrubber"]').value=f.hour;
        const key=[result.run_id,controller,f.hour,selected,section,costRevision,utility].join('|');
        if(renderedKey===key)return;
        renderedKey=key;
        performance.mark('dispatch-render-start');
        if(!d) return;
        const state=row?.observations_after || d.observations,a=row?.applied || {}, c=costFrame(f.hour);
        root.dataset.playing=String(clock.snapshot().playing);
        text('time',f.totals.local_time.replace('T',' / '));
        text('source',result.weather.reference); text('methane',num(f.totals.methane_kg)+' kg');
        text('mode',(row?.mode||'INITIAL').toUpperCase()); text('capacity',num(row?.diagnosis_after.capacity_kw ?? d.diagnosis.capacity_kw,0)+' kW');
        text('cost',money(c?.total_eur)); text('unit',c?.eur_per_kg_ch4==null?(f.methane_kg>1e-8?'— / UNPRICED':'— / NO OUTPUT'):money(c.eur_per_kg_ch4));
        text('diagnosis',row?.diagnosis_after.status || d.diagnosis.status);
        text('interval',`${f.hour} / ${result.records[controller].length} h`);
        $('[data-do="play"]').textContent=clock.snapshot().playing?'Ⅱ':'▶';
        $('[data-do="play"]').setAttribute('aria-label',clock.snapshot().playing?'Pause simulation':'Play simulation');
        $('[data-m="scrubber"]').value=f.hour;
        const ratio=(value,capacity)=>Math.max(0,Math.min(1,value/(capacity||1)));
        const pv=row?.pv_kw||0, capacity=row?.diagnosis_after.capacity_kw ?? d.diagnosis.capacity_kw;
        const batteryLevel=ratio(state.battery_kwh,p.battery_kwh), loadLevel=ratio(a.electrolyser_kw||0,p.electrolyser_kw);
        svgText('solar',num(pv,0));svgText('solar-caption',`${num(row?.irradiance_wm2||0,0)} W/m² / INCIDENT`);
        svgText('battery-soc',num(batteryLevel*100,0));svgText('battery',`${num(Math.max(0,state.battery_kwh),0)} / ${num(p.battery_kwh,0)} kWh`);
        svgText('battery-loss',`LOSSES ${num(row?.battery_loss_kwh||0)} kWh / STEP`);
        svgText('electrolyser',num(a.electrolyser_kw||0,0));svgText('stack-load',num(loadLevel*100,0));
        svgText('stack-state',a.electrolyser_kw>.01?'RUNNING':'STANDBY');svgText('stack-capacity',`${num(capacity,0)} kW EST. AVAILABLE`);
        svgText('hydrogen',num(state.h2_inventory_kg)+' kg');svgText('h2-headroom',`OF ${num(p.h2_capacity_kg,0)} kg / STORED`);
        svgText('co2',num(state.co2_kg)+' kg');svgText('co2-capacity',`OF ${num(p.co2_capacity_kg,0)} kg / STORED`);
        svgText('co2-delivery',`DELIVERY ${num(row?.co2_delivered_kg||0,0)} kg / STEP`);
        svgText('reactor',num(state.temperature_c)+' °C');svgText('thermal','HEAT '+num(a.heater_kw||0)+' kW');
        svgText('methane',num(a.methane_kg||0)+' kg/h');svgText('curtail',num(row?.curtailed_kwh||0,0));
        $$('[data-cell]').forEach(node=>node.setAttribute('width',70*ratio(batteryLevel*3-(2-Number(node.dataset.cell)),1)));
        for(const [key,value,cap,bottom,height,gaugeHeight] of [['hydrogen',state.h2_inventory_kg,p.h2_capacity_kg,170,120,96],['co2',state.co2_kg,p.co2_capacity_kg,130,110,87]]) {
            const level=ratio(value,cap), node=$(`[data-fill="${key}"]`);
            node.setAttribute('height',level*height);node.setAttribute('y',bottom-level*height);
            $(`[data-level="${key}"]`).setAttribute('transform',`translate(0 ${-level*gaugeHeight})`);
        }
        $('.solar-component').style.setProperty('--solar-level',ratio(pv,p.solar_kw));
        $('.stack-component').style.setProperty('--reaction-time',`${2.5-1.7*loadLevel}s`);
        $('.stack-component').dataset.fault=String(capacity<p.electrolyser_kw*.999);
        $$('.stack-plate').forEach((node,i)=>{
            const available=ratio(ratio(capacity,p.electrolyser_kw)*7-i,1);
            node.style.setProperty('--plate-level',loadLevel*available);node.style.opacity=.3+.7*available;
        });
        $('.m-heat').style.fillOpacity=ratio(state.temperature_c,p.temperature_max_c)*.3;
        const flows={source:pv,solar:Math.max(0,pv-(row?.curtailed_kwh||0)),load:(a.electrolyser_kw||0)+(row?.startup_kwh||0),
            battery:(a.charge_kw||0)+(a.discharge_kw||0),electrolyser:state.usable_hydrogen_inflow_kg??state.hydrogen_flow_kg??0,
            hydrogen:state.h2_outflow_kg||0,co2:row?.co2_consumed_kg||0,reactor:a.methane_kg||0,curtailment:row?.curtailed_kwh||0,
            auxiliary:(a.heater_kw||0)+(a.cooling_kw||0)*p.cooling_electric_fraction+(a.methane_kg>.01?p.auxiliary_kw:0)+(a.methane_kg||0)*p.methane_electric_kwh_per_kg};
        const limits={source:p.solar_kw,solar:p.solar_kw,load:p.electrolyser_kw,battery:p.battery_kwh*p.battery_c_rate,
            electrolyser:p.electrolyser_kw/p.specific_energy_kwh_per_kg,hydrogen:p.methane_max_kgph*.5,co2:p.methane_max_kgph*2.75,
            reactor:p.methane_max_kgph,curtailment:p.solar_kw,auxiliary:p.heater_max_kw+p.auxiliary_kw+p.methane_max_kgph*p.methane_electric_kwh_per_kg+p.cooling_max_kw*p.cooling_electric_fraction};
        $$('[data-flow]').forEach(node=>{
            const flow=node.dataset.flow, level=ratio(flows[flow],limits[flow]);node.dataset.active=String(flows[flow]>.01);
            node.style.setProperty('--flow-strength',1.5+level*3.5);node.style.setProperty('--flow-time',`${3.2-level*2.4}s`);
            node.style.setProperty('--flow-direction',flow==='battery'&&a.discharge_kw>.01?'reverse':'normal');
        });
        svgText('load-flow',num(flows.load,0)+' kW');svgText('h2-flow',num(flows.electrolyser)+' kg/h');
        svgText('battery-direction',a.discharge_kw>.01?'DISCHARGING':a.charge_kw>.01?'CHARGING':'BATTERY IDLE');svgText('battery-flow',num(flows.battery,0)+' kW');
        const activity={solar:pv,battery:flows.battery,electrolyser:a.electrolyser_kw,hydrogen:flows.electrolyser+flows.hydrogen,co2:flows.co2,reactor:flows.reactor};
        $$('[data-component]').forEach(node=>{
            node.dataset.selected=String(selected===node.dataset.component);node.setAttribute('aria-expanded',node.dataset.selected);
            node.dataset.active=String(activity[node.dataset.component]>.01);node.dataset.cooling=String((a.cooling_kw||0)>.01);node.dataset.heating=String((a.heater_kw||0)>.01);
        });
        $('.methane-product').dataset.active=String(flows.reactor>.01);$('.methane-product').style.setProperty('--gas-time',`${3-2*ratio(flows.reactor,p.methane_max_kgph)}s`);
        $('.curtail-component').dataset.active=String(flows.curtailment>.01);
        $$('[data-svg-cost]').forEach(node=>{node.textContent=(node.dataset.svgCost==='site'?'SHARED PLANT ':'')+money(c?.components[node.dataset.svgCost]);});
        $$('.m-events [data-hour]').forEach(node=>{node.dataset.future=String(Number(node.dataset.hour)>=f.hour);node.setAttribute('aria-pressed',String(Number(node.dataset.hour)===f.hour-1));});
        if(utility==='truth')text('truth',JSON.stringify({hour:Math.max(0,f.hour-1),...(result.retrospective_truth_by_controller?.[controller]||result.retrospective_truth)[Math.max(0,f.hour-1)],state:row?.state,balances:row?{electricity:row.electrical_residual_kwh,hydrogen:row.h2_residual_kg,co2:row.co2_residual_kg}:null},null,2));
        if(utility==='services'){
            serviceAlternatives?.sync();
            const pane=$('[data-m="services"]'), expanded=Boolean(pane.querySelector('details')?.open);
            pane.innerHTML='<nav class="d-inspector-links"><button data-explore="services">Explore service system</button></nav>'+renderFieldOperations(result,f,c,fieldScene?.snapshot());
            if(expanded&&pane.querySelector('details'))pane.querySelector('details').open=true;
        }
        if(utility==='compare'){
        const comparisons=Object.keys(result.records).map(name=>{const v=result.frames[name][Math.min(f.hour,result.frames[name].length-1)],cst=costs?.controllers[name]?.[f.hour];return [name,num(v.methane_kg),num(v.h2_kg),num(v.co2_kg),num(v.battery_kwh),num(v.curtailed_kwh),money(cst?.total_eur)];});
        $('[data-m="comparison"]').innerHTML=table(['Controller','CH₄ kg','Ending H₂ kg','Ending CO₂ kg','Battery kWh','Curtail kWh','Allocated €'],comparisons);
        }
        inspect(f);
        solar?.render(f);
        performance.measure('dispatch-render','dispatch-render-start');
        performance.clearMarks('dispatch-render-start');
    }
    function refreshEvents() {
        renderedKey="";
        $('.m-events').innerHTML=(result.events[controller]||[]).map(e=>`<button data-hour="${Number(e.hour)||0}" data-event-component="${escape(e.component)}">H${String(e.hour).padStart(3,'0')} · ${escape(e.label)}</button>`).join('') || '<span class="m-muted">No operating events in this run.</span>';
    }
    function reset() {
        agentControl?.close(false);
        investigation?.close(false);
        controlView?.close(false);
        studies?.close();
        sites?.close();
        model?.close();
        taxonomy?.close();
        project?.close();
        result=decodeMethanePayload(props.value); costs=decodeMethanePayload(props.economics); invalidate();
        if(result.study_origin)controller=result.study_origin.controller;
        const names=Object.keys(result.records);if(!names.includes(controller))controller=names[0];
        $('[data-m="controller"]').innerHTML=names.map(name=>`<option ${name===controller?'selected':''}>${escape(name)}</option>`).join('');
        $('[data-m="scrubber"]').max=result.records[controller].length;
        refreshEvents();clock.reset(result.records[controller].length);solar?.reset(result);render();project?.sync();
        $('[data-do="agent-control"]').hidden=!!result.offline_mode;
        $('[data-do="studies"]').hidden=!!result.offline_mode;
        $('[data-do="sites"]').hidden=!!result.offline_mode;
        $('[data-do="project"]').hidden=!!result.offline_mode;
        $('[data-do="study-origin"]').hidden=!result.study_origin||!!result.offline_mode;
        if(result.study_origin){clock.seek(result.study_origin.hour+1);selectComponent(result.study_origin.component);section='Why';inspect(current());}
        workflow?.sync();
        if(result.entry_workspace)investigation?.open(selected||'battery',null,{tab:result.entry_workspace==='write-up'?'Notes':'Period'});
    }
    fieldScene=typeof createFieldScene==='function'?createFieldScene({root,getResult:()=>result,getController:()=>controller,
        inspect:origin=>{clock.pause();openUtility('services',origin);}}):null;
    clock=createPlaybackClock({onFrame:frame=>fieldScene?.render(frame),duration:result.records[controller]?.length || 0,onChange:()=>{if(answer&&answer.key!==currentKey())invalidate();render();}});
    solar=createSolarWorkspace({root,props,watch,trigger,getResult:()=>result,getFrame:current,getCost:()=>costFrame(current().hour),
        onInspect:()=>loadDetail(current()),
        pause:()=>clock.pause(),onReturn:()=>{selected=null;render();$('.m-plant .solar-component').focus({preventScroll:true});}});
    $('.m-mobile-select').innerHTML=Object.entries(labels).map(([key,label])=>`<button data-mobile-component="${key}">${label}</button>`).join('');
    model=typeof createModelWorkspace==='function'?createModelWorkspace({root,getResult:()=>result,getFrame:current,getController:()=>controller,getPrices:()=>costs?.costs,getServicePrices:()=>costs?.service_economics,pause:()=>clock.pause()}):null;
    taxonomy=typeof createTaxonomyWorkspace==='function'?createTaxonomyWorkspace({root,getResult:()=>result,getFrame:current,getController:()=>controller,pause:()=>clock.pause()}):null;
    controlView=typeof createControlView==='function'?createControlView({root,getResult:()=>result,getFrame:current,pause:()=>clock.pause(),
        setController:value=>{controller=value;$('[data-m="controller"]').value=value;invalidate();refreshEvents();render();},
        seekDecision:hour=>{clock.pause();clock.seek(hour+1);},
        onOpen:()=>{controlOrigin={selected,section,utility};closePanels(false);},
        onComparison:value=>investigation?.acceptComparison(value),
        onReturn:origin=>{if(investigation?.resume())return;const previous=controlOrigin;controlOrigin=null;if(previous?.selected){selectComponent(previous.selected);section=previous.section;inspect(current());if(origin?.isConnected&&!origin.closest('[hidden]'))origin.focus({preventScroll:true});}else if(previous?.utility){openUtility(previous.utility);if(origin?.isConnected&&!origin.closest('[hidden]'))origin.focus({preventScroll:true});}else $('[data-do="menu"]').focus({preventScroll:true});}
    }):null;
    $('[data-do="control"]').hidden=!controlView;
    $('[data-do="watch-control"]').hidden=!controlView;
    investigation=typeof createInvestigation==='function'?createInvestigation({root,getResult:()=>result,getFrame:current,pause:()=>clock.pause(),
        onOpen:()=>{investigationOrigin={selected,section,utility};controlView?.close(false);closePanels(false);},
        restoreFrame:frame=>{if(!frame)return;controller=frame.controller;$('[data-m="controller"]').value=controller;invalidate();refreshEvents();clock.seek(frame.hour);render();},
        inspectDecision:value=>{controller=value.controller;$('[data-m="controller"]').value=controller;invalidate();refreshEvents();clock.seek(value.hour+1);controlView.open(value.component,null,{tab:value.tab});},
        onClose:origin=>{controlView?.close(false);const previous=investigationOrigin;investigationOrigin=null;if(previous?.selected){selectComponent(previous.selected);section=previous.section;inspect(current());}else if(previous?.utility)openUtility(previous.utility);if(origin?.isConnected&&!origin.closest('[hidden]'))origin.focus({preventScroll:true});else $('[data-do="menu"]').focus({preventScroll:true});}
    }):null;
    $$('[data-do="investigate"]').forEach(n=>n.hidden=!investigation);
    agentControl=typeof createAgentControl==='function'?createAgentControl({root,getResult:()=>result,getFrame:current,pause:()=>clock.pause(),
        onOpen:()=>{agentOrigin={selected,section,utility};controlView?.close(false);closePanels(false);},
        onClose:origin=>{const previous=agentOrigin;agentOrigin=null;if(previous?.selected){selectComponent(previous.selected);section=previous.section;inspect(current());}else if(previous?.utility)openUtility(previous.utility);if(origin?.isConnected&&!origin.closest('[hidden]'))origin.focus({preventScroll:true});else $('[data-do="menu"]').focus({preventScroll:true});},
        replay:request=>trigger('retry',{...request,run_id:result.run_id})}):null;
    $('[data-do="agent-control"]').hidden=!agentControl||!!result.offline_mode;
    serviceAlternatives=typeof createServiceAlternatives==='function'?createServiceAlternatives({root,getResult:()=>result,getFrame:current,pause:()=>clock.pause(),seekDecision:hour=>{clock.pause();clock.seek(hour+1);}}):null;
    studies=typeof createStudiesWorkspace==='function'?createStudiesWorkspace({root,getResult:()=>result,pause:()=>clock.pause(),replay:request=>trigger('retry',{...request,run_id:result.run_id})}):null;
    sites=typeof createSitesWorkspace==='function'?createSitesWorkspace({root,getResult:()=>result,pause:()=>clock.pause(),openModel:(topic='siting',context='Current model')=>model?.open(topic,context),replay:request=>trigger('retry',{...request,run_id:result.run_id})}):null;
    project=typeof createProjectWorkspace==='function'?createProjectWorkspace({root,getResult:()=>result,pause:()=>clock.pause(),replay:request=>trigger('retry',{...request,run_id:result.run_id}),openModel:topic=>model?.open(topic,'Current model'),openSites:(id,page)=>sites?.openSite(id,page),openStudy:id=>sites?.openStudy(id),openTaxonomy:()=>taxonomy?.open('services'),openSetup:()=>trigger('edit')}):null;
    workflow=typeof createWorkflow==='function'?createWorkflow({root,getResult:()=>result,getFrame:current}):null;
    root.addEventListener('revise-plant-design',()=>{solar?.close();project?.open({study:result.study_origin?.edition_id,component:'solar'});});
    root.addEventListener('open-studies',()=>studies?.open());
    root.addEventListener('click',event=>{
        if(event.target.closest('.ac-workspace'))return;
        if(event.target.closest('.iv-workspace'))return;
        if(event.target.closest('.cv-workspace'))return;
        if(event.target.closest('[data-service-alternatives]'))return;
        if(event.target.closest('.pj-workspace'))return;
        if(event.target.closest('.st-workspace'))return;
        if(event.target.closest('.si-workspace'))return;
        const documentation=event.target.closest('[data-model-topic]');if(documentation){if(result.offline_mode){window.location.href='model-report.html#'+encodeURIComponent(documentation.dataset.modelTopic);return;}model?.open(documentation.dataset.modelTopic,documentation.dataset.modelContext||'Current model',documentation);return;}
        const explore=event.target.closest('[data-explore]');if(explore){taxonomy?.open(explore.dataset.explore,explore);return;}
        if(event.target.closest('.x-workspace'))return;
        if(event.target.closest('.d-workspace'))return;
        if(event.target.closest('.s-workspace'))return;
        const work=event.target.closest('[data-work]')?.dataset.work;
        if(work){
            if(work==='watch')closePanels();
            if(work==='build'||work==='operate')project?.open({mode:work});
            if(work==='notes')investigation?.open(selected||'battery',event.target.closest('button'),{tab:'Notes'});
            if(work==='alternative')investigation?.open(selected||'battery',event.target.closest('button'),{tab:'Evidence'});
            if(work==='designs')sites?.openPage('compare');
            if(work==='reports')sites?.openPage('reports');
            if(work==='protocols')studies?.open();
            return;
        }
        const component=event.target.closest('[data-component]'); if(component){selectComponent(component.dataset.component);return;}
        const mobile=event.target.closest('[data-mobile-component]');if(mobile){selectComponent(mobile.dataset.mobileComponent);if(selected)$(`[data-component="${selected}"]`).scrollIntoView({block:'nearest',inline:'center'});return;}
        const eventButton=event.target.closest('[data-hour]');if(eventButton){invalidate();clock.seek(Number(eventButton.dataset.hour)+1);selectComponent(eventButton.dataset.eventComponent);return;}
        const locate=event.target.closest('[data-field-locate]');if(locate){clock.pause();closePanels(false);fieldScene?.focusAsset(locate.dataset.fieldLocate);return;}
        const panel=event.target.closest('[data-panel]');if(panel){openUtility(panel.dataset.panel);return;}
        const tab=event.target.closest('[data-section]');if(tab){section=tab.dataset.section;inspect(current());return;}
        const action=event.target.closest('[data-do]')?.dataset.do;
        if(action==='control'||action==='watch-control')controlView?.open(selected||'battery',event.target.closest('button'));
        if(action==='agent-control')agentControl?.open(event.target.closest('button'));
        if(action==='investigate')investigation?.open(selected||'battery',event.target.closest('button'));
        if(action==='play')clock.snapshot().playing?clock.pause():clock.play();
        if(action==='back'||action==='next'){invalidate();clock.step(action==='next'?1:-1);}
        if(action==='reset'){invalidate();clock.reset();}
        if(action==='close'||action==='dismiss')closePanels();
        if(action==='menu'){if(utility)closePanels();else openUtility();}
        if(action==='hide-ui')hideControls();
        if(action==='studies')studies?.open();
        if(action==='sites')sites?.open();
        if(action==='project')project?.open({mode:event.target.closest('[data-work-mode]')?.dataset.workMode});
        if(action==='project-revise')project?.open({study:result.study_origin?.edition_id,component:selected});
        if(action==='study-origin'){if(result.study_origin?.kind==='site-study')sites?.openStudy(result.study_origin.edition_id);else studies?.open(result.study_origin?.edition_id,result.study_origin?.report_id);}
        if(action==='timeline'){
            const opening=$('.m-timeline').hidden;closePanels(false);
            root.dataset.chrome='visible';$('.m-timeline').hidden=!opening;
            $('[data-do="timeline"]').setAttribute('aria-expanded',String(opening));
            if(opening)$('[data-m="scrubber"]').focus();
        }
        if(action==='costs'){const on=root.dataset.costs==='false';root.dataset.costs=String(on);$('[data-do="costs"]').textContent=on?'COSTS ON':'COSTS OFF';$('[data-do="costs"]').setAttribute('aria-pressed',String(on));}
        if(action==='setup'||action==='analysis'){controlView?.close(false);clock.pause();closePanels(false);trigger(action==='setup'?'edit':'expand');}
        if(action==='whatif'){
            clock.pause();const f=current();pendingKey=currentKey();answer=null;
            trigger('submit',{controller,hour:Math.max(0,f.hour-1),alternative:selected,run_id:result.run_id,key:pendingKey});inspect(f);
        }
        if(action==='guide'){
            const events=result.events[controller]||[];
            const milestones=[events.find(e=>e.label.includes('started')&&e.component==='reactor'),events.find(e=>e.label.includes('Forecast')),events.find(e=>e.label.includes('confirmed')||e.label.includes('isolated')),events.find(e=>e.label.includes('probe')),events.find(e=>e.label.includes('recovered'))].filter(Boolean);
            const chosen=milestones[guideIndex++%Math.max(1,milestones.length)];
            if(chosen){clock.seek(chosen.hour+1);selectComponent(chosen.component);section='Why';inspect(current());}
            else openUtility('compare');
        }
        if(!action&&!event.target.closest('.m-utility,.m-inspector,.m-dock'))closePanels(false);
    });
    $('[data-m="controller"]').addEventListener('change',e=>{controller=e.target.value;invalidate();refreshEvents();render();});
    $('[data-m="speed"]').addEventListener('change',e=>clock.setSpeed(Number(e.target.value)));
    $('[data-m="scrubber"]').addEventListener('input',e=>{invalidate();clock.seek(Number(e.target.value));});
    root.addEventListener('keydown',e=>{
        if(agentControl?.isOpen())return;
        if(investigation?.isOpen()&&!investigation.isSuspended())return;
        if(project?.isOpen())return;
        if(studies?.isOpen())return;
        if(sites?.isOpen())return;
        if(model?.isOpen())return;
        if(taxonomy?.isOpen())return;
        if(e.key==='Escape'&&controlView?.isOpen()){e.preventDefault();controlView.close();return;}
        if(e.key==='Escape'&&solar.isOpen()){e.preventDefault();solar.close();return;}
        if(e.key==='Escape'){e.preventDefault();closePanels();return;}
        if(e.target.closest('input,select,textarea'))return;
        if(e.key.toLowerCase()==='h'){e.preventDefault();if(root.dataset.chrome==='hidden'){root.dataset.chrome='visible';$('[data-do="menu"]').focus();}else hideControls();return;}
        if(e.target.closest('button'))return;
        const component=e.target.closest('[data-component]');
        if(component&&(e.key==='Enter'||e.key===' ')){e.preventDefault();selectComponent(component.dataset.component);return;}
        if(e.key===' '){e.preventDefault();clock.snapshot().playing?clock.pause():clock.play();}
        if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();invalidate();clock.step(e.key==='ArrowRight'?1:-1);}
        if(e.key.toLowerCase()==='r'){invalidate();clock.reset();}
    });
    const visibility=()=>{if(document.hidden)clock.pause();}; document.addEventListener('visibilitychange',visibility);
    const observer=new IntersectionObserver(entries=>{if(!entries[0].isIntersecting)clock.pause();});observer.observe(root);
    const cleanup=new MutationObserver(()=>{if(!element.isConnected){clock.destroy();agentControl?.destroy();investigation?.destroy();controlView?.destroy();project?.destroy();fieldScene?.destroy();observer.disconnect();cleanup.disconnect();document.removeEventListener('visibilitychange',visibility);}});cleanup.observe(document.body,{childList:true,subtree:true});
    watch('value',reset);watch('economics',()=>{costs=decodeMethanePayload(props.economics);costRevision++;render();});
    watch('decision_answer',()=>{
        const value=props.decision_answer;
        if(value?.key!==detailRequest||value.run_id!==result.run_id||value.controller!==controller)return;
        const row=result.records[controller]?.[value.hour];if(!row||!value.trajectory)return;
        row.decision.plan.trajectory=value.trajectory;row.audits=value.audits;row.battery_trace=value.battery_trace;row.component_traces=value.component_traces;row.derived_trace=value.derived_trace;row.economic_trace=value.economic_trace;
        detailRequest=null;renderedKey='';render();
    });
    watch('answer',()=>{const value=props.answer;if(value?.key===pendingKey&&value.key===currentKey()){answer=value;pendingKey=null;inspect(current());}});
    reset();
    if(props.project_start&&!result.offline_mode)project?.open();
}
if(typeof module!=='undefined')module.exports={methaneSelectionKey,methaneFrame,decodeMethanePayload};
