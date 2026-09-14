/* Recorded and teaching lifecycle diagrams. Rendering never advances a model. */
function lifecycleEscape(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function lifecycleArt(topic, data, step = 0) {
  if (!['deployment','condition','hardware','maintenance'].includes(topic)) return null;
  const e = lifecycleEscape;
  const text = (x,y,value,size=11) => `<text x="${x}" y="${y}" fill="currentColor" stroke="none" font-size="${size}">${e(value)}</text>`;
  const s = data?.steps?.[step] || {};
  const panel = `<path d="M250 126l166-32 56 48-170 38zM278 121l53 54m-24-61 55 54m-24-60 56 54m-24-60 56 54M266 141l166-32m-151 48 169-31M316 178v42m120-71v71m-131 0h26m93 0h25"/>`;
  const tracks = `<rect x="0" y="0" width="112" height="26" rx="13"/><path d="M13 5h86m-86 16h86"/>${[15,35,55,75,95].map(x=>`<circle cx="${x}" cy="13" r="7"/>`).join('')}`;
  let art = `<path d="M18 18h30m-30 0v20M522 18h-30m30 0v20M18 258h30m-30 0v-20M522 258h-30m30 0v-20" opacity=".4"/>`;
  if (topic === 'deployment') {
    const phase = s.package?.phase || 'mobilisation';
    const departed = s.package?.status === 'departed';
    const accepted = s.package?.accepted_at != null;
    art += text(34,44,'COMMISSIONING / ' + String(phase).toUpperCase());
    art += `<g opacity="${accepted?1:.35}">${panel}</g><path d="M30 224h480" opacity=".4"/>`;
    if (!departed) {
      art += `<g class="lc-machine" data-working="${s.crew_hours>0}"><g transform="translate(72 196)">${tracks}</g><path d="M82 196v-44h41l14 25h32v19M88 158h29l9 18H88zM150 177V85l-13-12V57h16l10 22v98M153 82l126-48 7 11-126 50M281 43v53m-7 0h14m-14 0v12l7 5 7-5V96"/><path d="M175 182h-18m25 7h-25"/><g class="lc-work-light"><path d="M190 158l13-7m-8 15h15m-20 9l13 7"/></g></g>`;
    } else art += text(45,183,'TEMPORARY',10) + text(45,200,'EQUIPMENT DEPARTED',10);
    art += text(292,239,accepted?'ACCEPTED / '+(s.capacity_kw??0)+' kW':'AWAITING ACCEPTANCE',10);
    art += text(34,246,'H'+(s.hour??0)+' · '+(s.crew_hours??0)+' CREW h',10);
  } else if (topic === 'condition') {
    const physical = Math.min(1, Math.max(0,s.physical_condition || 0));
    const observed = s.measurement == null ? null : Math.min(1,Math.max(0,s.measurement.value));
    art += text(34,43,'CONDITION / SEPARATE EVIDENCE');
    art += `<path d="M67 85h151v125H67zM67 103h151m-137 0v96m124-96v96M82 77v8m28-8v8m28-8v8m28-8v8m28-8v8"/>`;
    for(let i=0;i<7;i++) art += `<path d="M${89+i*17} 111v83" opacity="${Math.max(.15,1-physical*5)}" stroke-width="5"/>`;
    art += `<path d="M218 136h49v-39h52m-101 82h49v36h52"/><rect x="319" y="73" width="171" height="58"/><rect x="319" y="188" width="171" height="50"/>`;
    art += text(330,93,'RETROSPECTIVE',10) + text(330,117,(physical*100).toFixed(2)+'% condition',13);
    art += text(330,208,'ELIGIBLE MEASUREMENT',10) + text(330,228,observed==null?'NO READING':(observed*100).toFixed(2)+'%',13);
    art += text(69,236,'STOCK '+(s.stock??'—')+' / '+(s.availability===0?'ISOLATED':'AVAILABLE'),10);
    art += `<path d="M267 141v28m-5-28h10m-10 28h10" stroke-dasharray="2 4"/>` + text(277,160,'delay',10);
  } else if (topic === 'hardware') {
    const a = data?.assessment || {};
    const restricted = a.status === 'evidence restricted';
    art += text(34,43,String(a.family||'hardware').toUpperCase());
    art += `<g transform="translate(64 136)" opacity="${restricted?.35:1}">${tracks}<path d="M13 0v-46h71l15 23V0M24-46v-18h41v18m-26-18v-27m-12 0h25M22-36h28v22H22zM64-34h13m-13 9h23M55-82h30m0 0v18"/></g>`;
    const requirements = data?.prerequisites || [];
    art += `<path d="M176 149h50m-7-5 7 5-7 5" ${restricted?'stroke-dasharray="3 5"':''}/>`;
    requirements.forEach((value,i)=>{
      const missing = (a.missing||[]).includes(value);
      art += `<path d="M240 ${78+i*53}h262v41H240z" opacity="${missing?.4:1}"/>`;
      art += text(250,95+i*53,missing?'MISSING':'PREREQUISITE DECLARED',8);
      art += text(250,111+i*53,value,9);
    });
    art += text(34,246,restricted?'NO EXECUTABLE MECHANISM':a.eligible?'CHECK ACTUAL INTERFACE BEFORE WORK':'SUPPORT INCOMPLETE',10);
  } else {
    art += text(34,43,'MATCHED WINDOW / METHANE PRODUCED');
    const cases = data?.cases || [];
    const max = Math.max(1,...cases.map(c=>c.methane_kg));
    cases.forEach((c,i)=>{
      art += text(34,78+i*40,c.policy,10);
      art += `<rect x="172" y="${65+i*40}" width="300" height="18" opacity=".25"/><rect x="172" y="${65+i*40}" width="${300*c.methane_kg/max}" height="18" fill="currentColor" opacity="${i===step?.55:.25}"/>`;
      art += text(178,78+i*40,c.methane_kg.toFixed(1)+' kg',10);
    });
    art += text(34,246,'Compare costs and ending obligations below',10);
  }
  return `<svg class="lc-diagram" viewBox="0 0 540 276" role="img" aria-label="${e(topic)} calculated lifecycle diagram"><g fill="none" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round">${art}</g></svg>`;
}

function lifecycleDesignForm(config) {
  const e = lifecycleEscape;
  return `<div class="lc-design" hidden><h2>Deployment and maintenance</h2><p>Changes remain in this design draft. Current operation and saved runs are unchanged.</p><label>Starting fixture<select data-lc="preset"><option value="commissioning">Commission a new plant</option><option value="maintenance">Condition of an operating plant</option><option value="none">No lifecycle model</option></select></label><button data-si="lifecycle-preset">Load fixture into draft</button><label>Maintenance policy<select data-lc="policy">${['none','periodic','condition','forecast-window'].map(p=>`<option ${p===(config.lifecycle?.maintenance_policy||'condition')?'selected':''}>${p}</option>`).join('')}</select></label><label>Work packages, condition and support assumptions<textarea data-lc="config" spellcheck="false">${e(JSON.stringify(config.lifecycle||null,null,2))}</textarea></label><button data-si="lifecycle-validate">Validate lifecycle draft</button><button data-si="lifecycle-model">Explore the mechanism</button><p class="lc-validation" role="status"></p><p class="si-meta">An additional project crew shares construction and condition replacement. Part prices and work rates are explicit assumptions. Acceptance, physical restoration and measured confirmation are separate.</p></div>`;
}

function lifecyclePeriodView(value, caseId=null) {
  if (!value) return '';
  const e=lifecycleEscape;
  const n=x=>typeof x==='number'?x.toLocaleString('en-GB',{maximumFractionDigits:2}):'—';
  return `<section class="lc-period"><h3>Deployment and maintenance</h3><p>Recorded expenditure €${n(value.cash_eur)} · additional project crew ${n(value.project_crew_hours)} h · verified procedures ${n(value.verified_replacements)}</p><p>Cash purchases, allocated cost and operating contribution are separate views.</p><table><thead><tr><th>Package</th><th>State</th><th>Accepted at</th><th>Departed at</th></tr></thead><tbody>${Object.entries(value.packages||{}).map(([k,v])=>`<tr><td>${e(k)}</td><td>${e(v.status)}</td><td>${n(v.accepted_at)}</td><td>${n(v.departed_at)}</td></tr>`).join('')}</tbody></table><p>${(value.unresolved_jobs||[]).length} unresolved or unsuccessful condition jobs remain in this window.</p>${caseId?`<button data-si="case-trace" data-case="${e(caseId)}">Trace lifecycle accounting</button>`:'<button data-model-topic="maintenance" data-model-context="This run">Trace lifecycle accounting</button>'}</section>`;
}
if(typeof module!=='undefined')module.exports={lifecycleArt,lifecycleDesignForm,lifecyclePeriodView};
