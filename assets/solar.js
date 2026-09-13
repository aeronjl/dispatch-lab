/* Geometry is visual only. Power accounting and weather replay are calculated in Python. */
function solarPanelGeometry(section) {
    const rows=Math.max(0,Math.min(5,Math.ceil(section.capacity_kw/125)));
    const tilt=section.tilt*Math.PI/180, az=section.azimuth*Math.PI/180;
    const project=(u,v,z=0)=>{
        const x=u*Math.cos(az)-v*Math.sin(az)*Math.cos(tilt), y=u*Math.sin(az)+v*Math.cos(az)*Math.cos(tilt);
        return [142+x*.86+y*.38,132-y*.34-v*Math.sin(tilt)*.72-z];
    };
    const tiles=[];
    for(let row=rows-1;row>=0;row--)for(let col=0;col<3;col++) {
        const u=-99+col*67,v=(row-rows/2)*43;
        const corners=[project(u,v),project(u+61,v),project(u+61,v+37),project(u,v+37)];
        const grid=[];
        for(let c=1;c<3;c++)grid.push([project(u+c*61/3,v),project(u+c*61/3,v+37)]);
        grid.push([project(u,v+18.5),project(u+61,v+18.5)]);
        tiles.push({corners,grid,index:row*3+col});
    }
    return {rows,tiles};
}
function createSolarWorkspace({root,props,watch,trigger,getResult,getFrame,getCost,pause,onReturn}) {
    const $=s=>root.querySelector(s), $$=s=>[...root.querySelectorAll(s)], workspace=$('.s-workspace');
    const q=s=>workspace.querySelector(s), qq=s=>[...workspace.querySelectorAll(s)];
    const num=(v,d=0)=>Number.isFinite(v)?(Math.abs(v)<.05?0:v).toLocaleString('en-GB',{maximumFractionDigits:d}):'—';
    const set=(name,value)=>{const n=q(`[data-s="${name}"]`);if(n)n.textContent=value;};
    const uuid=crypto.randomUUID();let generation=0, selected=0, design, baseline, response, pending=null;
    let fetchController=null;
    let open=false, dirty=false, applying=false, timer=null, flight=null, transition=0, drawn='', currentRun=null;
    const motion=()=>!matchMedia('(prefers-reduced-motion: reduce)').matches;
    const pts=points=>points.map(p=>p.map(n=>n.toFixed(2)).join(',')).join(' ');
    function inputValues() {
        qq('[data-setting]').forEach(input=>{
            const metadata=getResult().component_specs?.solar?.parameters?.find(p=>p.key===input.dataset.setting);
            if(metadata){input.min=metadata.lower;input.max=metadata.upper;input.setAttribute('aria-label',metadata.label);input.title=metadata.label+' / '+metadata.unit+' · '+metadata.source;}
            const key=input.dataset.setting, value=key in design?design[key]:design.sections[selected][key];
            if(input.type==='checkbox')input.checked=value;
            else {if(Number(input.max)<value)input.max=value;input.value=value;}
            const output=q(`[data-read="${key}"]`);
            if(output)output.textContent=['shade','soiling','efficiency'].includes(key)?`${num(value*100,1)}%`:
                ['tilt','azimuth'].includes(key)?`${num(value)}°`:key==='noct_c'?`${num(value)} °C`:`${num(value,1)} kW`;
        });
    }
    function drawBanks(displayDesign=design) {
        const signature=JSON.stringify(displayDesign)+selected;
        if(signature===drawn)return;drawn=signature;
        q('[data-s="banks"]').innerHTML=displayDesign.sections.map((section,index)=>{
            const geometry=solarPanelGeometry(section);
            const front=geometry.tiles.filter(t=>t.index<3);
            const supports=front.flatMap(t=>t.corners.slice(0,2)).map(([x,y])=>`M${x} ${y+5}v16h8`).join(' ');
            const terminal=front[1]?.corners[1] || [142,200];
            const panels=geometry.tiles.map(tile=>{
                const shade=tile.index<Math.ceil(section.shade*geometry.tiles.length);
                const side=tile.corners.slice(0,2).concat(tile.corners.slice(0,2).reverse().map(([x,y])=>[x,y+5]));
                const dust=Array.from({length:Math.round(section.soiling*35)},(_,i)=>{
                    const a=tile.corners[0],b=tile.corners[1],c=tile.corners[3],u=((i*37+13)%97)/100,v=((i*23+9)%89)/100;
                    return `<rect class="s-dust" x="${a[0]+(b[0]-a[0])*u+(c[0]-a[0])*v}" y="${a[1]+(b[1]-a[1])*u+(c[1]-a[1])*v}" width="2" height="2"/>`;
                }).join('');
                return `<g class="s-panel-tile" data-shaded="${shade}"><polygon class="s-panel-face" points="${pts(tile.corners)}"/><polygon class="s-panel-edge" points="${pts(side)}"/>${tile.grid.map(line=>`<polyline class="s-cell-line" points="${pts(line)}"/>`).join('')}${dust}</g>`;
            }).join('');
            return `<g class="s-bank" data-bank="${index}" data-online="${section.online}" data-selected="${selected===index}" transform="translate(${index*300} 100)" role="button" tabindex="0" aria-label="Inspect solar section ${String.fromCharCode(65+index)}" aria-pressed="${selected===index}">
            <rect class="s-bank-hit" x="12" y="-3" width="280" height="250"/><text x="28" y="20" class="s-bank-title">0${index+1} / ARRAY ${String.fromCharCode(65+index)}</text><text class="s-caption" x="28" y="40">${num(section.capacity_kw,1)} kWp · ${num(section.tilt)}° · ${num(section.azimuth)}°</text>
            <g class="s-panel-field">${panels || '<text x="142" y="132" text-anchor="middle">NO ARRAY INSTALLED</text>'}<path class="s-panel-support" d="${supports}"/><path class="s-track" d="M${terminal[0]} ${terminal[1]+5}V217H142"/></g>
            <text x="28" y="235" class="s-caption" data-bank-temperature="${index}">MODEL TEMPERATURE —</text>
            <path class="s-track" d="M142 217V250H157V264 M157 277V283 M157 334V345"/><path class="s-current" data-bank-flow="${index}" d="M142 217V250H157V264 M157 277V283 M157 334V345"/>
            <path class="s-isolator" d="${section.online?'M157 264V277':'M157 264L173 274'}"/><circle cx="157" cy="263" r="2"/><circle cx="157" cy="278" r="2"/>
            <text class="s-caption" x="178" y="273">${section.online?'CLOSED':'ISOLATED'}</text>
            <g class="s-mppt"><path class="s-case" d="M110 283H204V334H110Z M110 283L118 277H212L204 283 M204 283L212 277V328L204 334"/><text x="157" y="301" text-anchor="middle">MPPT 0${index+1}</text><text class="s-power" x="157" y="321" text-anchor="middle" data-bank-power="${index}">— kW</text><path d="M116 290H123 M116 327H123"/></g>
            </g>`;
        }).join('');
        qq('.s-section-picker [data-bank]').forEach(n=>n.setAttribute('aria-pressed',String(Number(n.dataset.bank)===selected)));
    }
    function requestPreview() {
        clearTimeout(timer);pause();generation++;pending=`${currentRun}|${uuid}|${generation}`;response=null;
        drawBanks();inputValues();render(getFrame());
        if(fetchController)fetchController.abort();
        timer=setTimeout(async()=>{
            const key=pending,token=getResult().preview_token;
            if(!token){trigger('input',{run_id:currentRun,key,design});return;}
            fetchController=new AbortController();
            try {
                const http=await fetch('/dispatch/preview-solar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token,run_id:currentRun,key,design}),signal:fetchController.signal});
                const value=await http.json();
                if(pending!==key)return;
                response=http.ok?value:{error:value.detail||'Preview unavailable'};pending=null;render(getFrame());
            } catch(error){if(error.name!=='AbortError'&&pending===key){response={error:'Preview unavailable. Retry or reload the saved run.'};pending=null;render(getFrame());}}
        },75);
    }
    function reset(result) {
        clearTimeout(timer);generation++;pending=null;applying=false;currentRun=result.run_id;
        baseline=result.solar;response=baseline;design=structuredClone(baseline.design);dirty=false;drawn='';
        inputValues();drawBanks();render(getFrame());
    }
    function changeView(next) {
        if(next===open)return;pause();const serial=++transition;
        if(flight){flight.remove();flight=null;}
        const source=next?$('.m-plant .solar-component'):q('.s-bank');
        const rect=source.getBoundingClientRect(), box=source.getBBox();
        const ghost=document.createElement('div');ghost.className='s-flight';
        const clone=source.cloneNode(true);clone.removeAttribute('transform');clone.removeAttribute('tabindex');clone.removeAttribute('data-component');clone.removeAttribute('data-bank');
        const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox',`${box.x} ${box.y} ${box.width} ${box.height}`);svg.setAttribute('class',next?'plant-drawing':'s-circuit');svg.append(clone);ghost.append(svg);ghost.setAttribute('aria-hidden','true');
        open=next;root.dataset.focus=next?'solar':'plant';workspace.hidden=!next;
        if(next){window.scrollTo({top:0,behavior:'instant'});render(getFrame());}
        if(motion()&&rect.width>0){
            root.append(ghost);flight=ghost;const target=(next?q('.s-bank'):$('.m-plant .solar-component')).getBoundingClientRect();
            Object.assign(ghost.style,{left:`${rect.left}px`,top:`${rect.top}px`,width:`${rect.width}px`,height:`${rect.height}px`});
            const animation=ghost.animate([{transform:'translate(0,0) scale(1)',opacity:1},{transform:`translate(${target.left-rect.left}px,${target.top-rect.top}px) scale(${target.width/rect.width},${target.height/rect.height})`,opacity:0}],{duration:620,easing:'cubic-bezier(.22,.8,.22,1)',fill:'forwards'});
            if(next){workspace.animate([{opacity:0,transform:'translateY(12px)'},{opacity:1,transform:'translateY(0)'}],{duration:500,delay:100,fill:'backwards',easing:'ease-out'});qq('.s-bank').forEach((node,i)=>node.animate([{opacity:0},{opacity:1}],{duration:420,delay:170+i*75,fill:'backwards'}));}
            animation.finished.catch(()=>{}).then(()=>{ghost.remove();if(serial===transition)flight=null;});
        }
        if(next)q('[data-s="back"]').focus({preventScroll:true});else onReturn();
    }
    function render(frame) {
        if(!design||!frame)return;
        const optical=frame.row?.field_operations?.optical;
        const recordedOptics=optical&&!dirty;
        drawBanks(recordedOptics?JSON.parse(optical.parameters.design_json):design);if(!open)return;
        const hour=Math.max(0,frame.hour-1), result=getResult(), detail=recordedOptics?frame.row.solar_detail:response?.frames?.[hour], section=detail?.sections[selected];
        set('time',frame.totals.local_time.replace('T',' / '));set('capacity',num(design.sections.reduce((s,x)=>s+x.capacity_kw,0))+' kWp');
        set('status',applying?'RUNNING PLANT EXPERIMENT…':pending?'CALCULATING DESIGN…':response?.error?'PREVIEW UNAVAILABLE':dirty?'DESIGN PREVIEW':recordedOptics?'RECORDED SURFACE':'RECORDED DESIGN');
        workspace.dataset.pending=String(Boolean(pending));workspace.dataset.dirty=String(dirty);
        const provenance=result.provenance_summary;
        const learned=frame.decision?.performance_estimates?.solar;
        const learnedText=learned?[`Recorded estimate / H${learned.hour}`,`Expected: ${num(learned.expected_kw)} kW`,`Observed: ${num(learned.measured_kw)} kW`,`Multiplier: ${num(learned.before,3)} → ${num(learned.after,3)}`,`Evidence: ${learned.status}`,`Informative intervals: ${learned.informative_intervals}`,'Effective performance only.','The cause is not identified.','',''].join('\n'):'';
        set('lineage',dirty?'This is a hypothetical design preview; restore the run design to inspect recorded execution.':learnedText+JSON.stringify(frame.row?.component_traces?.solar || {status:'unavailable',note:'Select an executed interval to load recorded generation lineage.'},null,2));
        set('evidence',`MODEL ${result.component_specs?.solar?.model_id||'solar'} / ${result.component_specs?.solar?.version||'unknown'} · ${provenance?.status||'legacy provenance unavailable'} · ${detail?.audits?.filter(a=>a.passed).length||0}/${detail?.audits?.length||0} checks. Weather content: ${provenance?.weather_content_hash||'unavailable'}.`);
        set('output',num(detail?.output_kw,1)+' kW');set('temperature',num(section?.temperature_c,1)+' °C');
        const delta=response?.energy_kwh-baseline.recorded_energy_kwh;
        set('delta',optical?'STATIC DESIGN ONLY':Number.isFinite(delta)?`${delta>=0?'+':''}${num(delta,1)} kWh`:'—');
        set('available',num(detail?.available_kw,1)+' kW');set('losses',`${num(detail?.conversion_loss_kw,1)} / ${num(detail?.clipped_kw,1)} kW`);
        set('dc-output','TO PLANT BUS / '+num(detail?.output_kw,1)+' kW');
        set('ambient','AMBIENT '+num(detail?.ambient_c,1)+' °C');set('irradiance',num(detail?.reference_irradiance_wm2)+' W/m² / REFERENCE PLANE');
        const progress=(((Date.parse(frame.row?.time||frame.decision.forecast.times[0])/3600000)%24)-6)/12;
        const sunX=90+Math.max(0,Math.min(1,progress))*735,sunY=90-68*Math.sin(Math.max(0,Math.min(1,progress))*Math.PI);
        q('[data-s="sun"]').setAttribute('transform',`translate(${sunX} ${sunY})`);
        q('[data-s="sun"]').style.opacity=detail?.reference_irradiance_wm2>0?1:.25;
        qq('.s-bank').forEach((node,i)=>{const s=detail?.sections[i];node.style.setProperty('--solar-level',Math.min(1,(s?.irradiance_wm2||0)/1000));node.dataset.active=String((s?.available_kw||0)>.01);});
        qq('[data-bank-power]').forEach(n=>n.textContent=num(detail?.sections[Number(n.dataset.bankPower)]?.available_kw,1)+' kW');
        qq('[data-bank-temperature]').forEach(n=>n.textContent='MODULE '+num(detail?.sections[Number(n.dataset.bankTemperature)]?.temperature_c,1)+' °C / MODELLED');
        for(const key of ['bus-flow','output-flow'])q(`[data-s="${key}"]`).dataset.active=String((detail?.output_kw||0)>.01);
        set('asset',`${result.asset_ids.solar} / SECTION 0${selected+1}`);set('bank-title',`ARRAY ${String.fromCharCode(65+selected)}`);
        const d=frame.decision;set('decision',`Recorded ${d.policy} decision: ${d.forecast.pv_kw.length}-hour plan. ${d.forecast.source.source}. Available ${d.forecast.source.available_at}. Forecast residual ${num(d.evidence.solar.current_error_kw,1)} kW; predicted curtailment ${num(d.evidence.solar.predicted_curtailment_kwh,1)} kWh. This evidence belongs to the original run, including while editing a design.`);
        set('allocation',`Recorded solar allocation through this hour: €${num(getCost()?.components.solar,2)}. Rerun the plant to price a changed design.`);
        set('assumptions',baseline.note+(optical?' Recorded section surface effects enter before conversion and clipping. Dry brushing leaves adhered fouling and permanent damage. Editable design controls remain separate from recorded surface state.':frame.row?.field_operations?' Site service layer: this design diagram precedes the additional lumped soiling loss. Available at the plant: '+num(frame.row.pv_kw)+' kW; service loss: '+num(frame.row.field_operations.soiling_loss_kw)+' kW. Inspect Site services for this recorded calculation.':''));set('energy',optical?`RECORDED INTERVAL ${num(frame.row.pv_kw)} kW / STATIC DESIGN PREVIEW ${num(response?.energy_kwh)} kWh`:`DESIGN ${num(response?.energy_kwh)} kWh / RUN ${num(baseline.recorded_energy_kwh)} kWh`);
        const budget=section?[['Light-equivalent power',section.gross_kw],['Shading',-section.shade_loss_kw],['Soiling',-section.soiling_loss_kw],['Temperature',-section.temperature_loss_kw],['Existing electrical losses',-section.electrical_loss_kw],['Disconnected',-section.offline_loss_kw],['Available DC',section.available_kw]]:[];
        q('[data-s="budget"]').innerHTML=budget.map(([k,v])=>`<div><dt>${k}</dt><dd>${v>0&&k==='Temperature'?'+':''}${num(v,1)} kW</dd></div>`).join('')||'<div><dt>Recalculating…</dt></div>';
        const rows=result.records[frame.controller||Object.keys(result.records)[0]], max=Math.max(1,...rows.map(x=>x.pv_kw),...(response?.frames||[]).map(x=>x.output_kw));
        const path=values=>values.map((v,i)=>`${i?'L':'M'}${i/Math.max(1,values.length-1)*1000},${85-v/max*78}`).join(' ');
        q('[data-s="profile-base"]').setAttribute('d',path(rows.map(x=>x.pv_kw)));
        q('[data-s="profile-draft"]').setAttribute('d',response?.frames?path(response.frames.map(x=>x.output_kw)):'');
        const cx=hour/Math.max(1,rows.length-1)*1000;q('[data-s="profile-cursor"]').setAttribute('d',`M${cx} 0V90`);
        set('change-label',applying?'RUNNING ALL THREE CONTROLLERS':response?.error?'DESIGN COULD NOT BE EVALUATED':dirty?'DESIGN CHANGED / PREVIEW ONLY':'EXPLORING THE RECORDED DESIGN');
        set('change-help',response?.error|| (dirty?'Run the plant to evaluate production, storage and cost consequences.':optical?'Controls edit the underlying design; recorded fouling is a separate surface state.':'Select an array section to inspect its configuration.'));
        q('[data-s="apply"]').disabled=applying||Boolean(pending)||!dirty||!response?.frames;
        q('[data-s="restore"]').disabled=applying;
        qq('[data-setting]').forEach(n=>n.disabled=applying);
    }
    workspace.addEventListener('click',event=>{
        const bank=event.target.closest('[data-bank]');
        if(bank){selected=Number(bank.dataset.bank);inputValues();drawn='';render(getFrame());if(bank.closest('.s-section-picker'))q('.s-scroll').scrollTo({left:Math.max(0,selected*300+157-q('.s-scroll').clientWidth/2),behavior:motion()?'smooth':'instant'});return;}
        const tab=event.target.closest('[data-s-tab]');
        if(tab){qq('[data-s-tab]').forEach(n=>n.setAttribute('aria-pressed',String(n===tab)));qq('[data-s-panel]').forEach(n=>n.hidden=n.dataset.sPanel!==tab.dataset.sTab);return;}
        const action=event.target.closest('button[data-s]')?.dataset.s;
        if(action==='back')changeView(false);
        if(action==='restore'){clearTimeout(timer);pending=null;generation++;response=baseline;design=structuredClone(baseline.design);dirty=false;inputValues();drawn='';render(getFrame());q(`.s-bank[data-bank="${selected}"]`).focus({preventScroll:true});}
        if(action==='apply'&&!applying&&dirty&&response?.frames){pause();applying=true;pending=null;generation++;const key=`${currentRun}|${uuid}|${generation}`;pending=key;trigger('apply',{run_id:currentRun,key,design});render(getFrame());}
    });
    workspace.addEventListener('input',event=>{
        const input=event.target.closest('[data-setting]');if(!input||applying)return;
        const key=input.dataset.setting,value=input.type==='checkbox'?input.checked:Number(input.value);
        if(key in design)design[key]=value;else design.sections[selected][key]=value;
        dirty=JSON.stringify(design)!==JSON.stringify(baseline.design);requestPreview();
    });
    workspace.addEventListener('keydown',event=>{
        const bank=event.target.closest('.s-bank');if(bank&&['Enter',' '].includes(event.key)){event.preventDefault();event.stopPropagation();selected=Number(bank.dataset.bank);drawn='';inputValues();render(getFrame());}
    });
    watch('solar_answer',()=>{const value=props.solar_answer;if(value?.key!==pending)return;pending=null;applying=false;response=value;render(getFrame());});
    return {open:()=>changeView(true),close:()=>changeView(false),isOpen:()=>open,render,reset};
}
if(typeof module!=='undefined')module.exports={solarPanelGeometry};
