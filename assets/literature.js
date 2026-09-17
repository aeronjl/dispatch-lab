/* Source experiments are independent of project designs. Python owns all numerical results. */
function literaturePlot(v) {
 const esc=equipmentEscape, pts=[...v.curve,...v.rows], xmin=Math.min(...pts.map(p=>p.x)),xmax=Math.max(...pts.map(p=>p.x));
 const yy=pts.flatMap(p=>[p.predicted,p.observed,p.low,p.high]).filter(Number.isFinite), ymin=Math.min(...yy), ymax=Math.max(...yy),pad=Math.max((ymax-ymin)*.1,.01);
 const x=z=>55+(z-xmin)/(xmax-xmin||1)*540,y=z=>225-(z-ymin+pad)/(ymax-ymin+2*pad)*190;
 const line=v.curve.map(p=>`${x(p.x)},${y(p.predicted)}`).join(' '),band=[...v.curve.map(p=>`${x(p.x)},${y(p.low)}`),...v.curve.slice().reverse().map(p=>`${x(p.x)},${y(p.high)}`)].join(' ');
 return `<svg class="lt-plot" viewBox="0 0 640 280" role="img" aria-label="${esc(v.x_label)} against ${esc(v.unit)}. Fitted line, observed points and parameter sensitivity band. Exact values in the points table."><path d="M55 25V225H600" fill="none" stroke="currentColor" opacity=".5"/><polygon points="${band}" fill="currentColor" opacity=".12"/><polyline points="${line}" fill="none" stroke="currentColor" stroke-width="2"/>${v.rows.map(p=>`<circle cx="${x(p.x)}" cy="${y(p.observed)}" r="4" fill="${p.split==='evaluation'?'currentColor':'#17191b'}" stroke="currentColor"><title>${esc(p.split)}: ${p.x.toFixed(3)} → ${p.observed.toFixed(4)} ${esc(v.unit)}</title></circle>`).join('')}<path d="M${x(v.query.x)} 25V225" stroke="currentColor" stroke-dasharray="3 5" opacity=".6"/><text x="55" y="18">${esc(v.unit)} · ${ymin.toFixed(2)}–${ymax.toFixed(2)}</text><text x="55" y="245">${xmin.toFixed(1)}</text><text x="590" y="245" text-anchor="end">${xmax.toFixed(1)}</text><text x="325" y="272" text-anchor="middle">${esc(v.x_label)}</text></svg>`;
}
function createLiteraturePanel({host,api,status}) {
 const e=equipmentEscape,n=v=>Number.isFinite(v)?v.toLocaleString('en-GB',{maximumFractionDigits:5}):'—',q=s=>host.querySelector(s);
 let active=true,generation=0,catalogue=null,selected='csu-pem',result=null;
 const live=g=>active&&g===generation;
 const select=(key,label,choices,value)=>`<label>${label}<select name="${key}">${choices.map(([v,t])=>`<option value="${v}" ${value===v?'selected':''}>${t}</option>`).join('')}</select></label>`;
 const number=(key,label,value,min,max)=>`<label>${label}<input type="number" name="${key}" value="${value}" min="${min}" max="${max}" step="any" required></label>`;
 function render(inputs=null) {
  const p=catalogue.profiles.find(p=>p.id===selected),d=inputs||catalogue.defaults[selected];result=null;
  host.innerHTML=`<h1>Reference experiments</h1><p class="rq-muted">Current model · source devices. Exploring these examples leaves your project and saved runs unchanged.</p><label>Published experiment<select data-lt-profile>${catalogue.profiles.map(p=>`<option value="${p.id}" ${p.id===selected?'selected':''}>${e(p.title)}</option>`).join('')}</select></label><p>${e(p.conditions)}</p><form data-lt-form><fieldset><legend>Question and assumptions</legend>${selected==='csu-pem'?select('power','Electrical boundary',[['system_power','Whole-system AC'],['stack_power','Stack DC']],d.power)+select('channel','Original hydrogen channel',[['hydrogen_flow','hydrogen_flow'],['hydrogen_flow_cs','hydrogen_flow_cs']],d.channel)+select('model','Model form',[['affine','Affine power / flow'],['constant-specific','Constant specific electricity']],d.model)+number('query_kw','Inspect power · kW',d.query_kw,0,100)+number('flow_offset_bound','Assumed common flow offset bound · kg/h',d.flow_offset_bound,0,.1):number('query_minutes','Inspect elapsed time · min',d.query_minutes,0,40)+number('digitization_bound_k','Assumed digitization bound · K',d.digitization_bound_k,0,3)}</fieldset><p class="rq-muted">${selected==='csu-pem'?'Eight plateaus; first stable halves fit the model, second halves check it. Zero flow-offset bound means uncertainty is not assessed.':'Twelve manually read figure points, all used in fitting. The digitization bound describes a sensitivity scenario, not measured sensor error.'}</p><button type="button" data-lt="run">Run reference experiment</button> <button type="button" data-lt="reset">Reset</button></form><div class="lt-result" aria-live="polite"></div><p><button data-lt="source" aria-expanded="false">Source mapping and limitations</button></p><div class="lt-source" hidden></div><p><button data-lt="saved" aria-expanded="false">Saved reference experiments</button></p><div class="lt-saved" hidden></div>`;
  q('[data-lt-profile]').focus({preventScroll:true});
 }
 function showResult() {
  const v=result;
  q('.lt-result').innerHTML=`<h2>${e(v.model_identity)}</h2><p>${e(v.applicability||'Saved with the current implementation')} · ${e(v.dataset.technology)}</p><p>${e(v.equation)}</p>${literaturePlot(v)}<p>Line: prediction. Open points: development or digitized observations. Filled points: evaluation. Shading: parameter sensitivity, not a confidence interval.</p><p>At ${n(v.query.x)} ${selected==='csu-pem'?'kW':'min'}: <strong>${n(v.query.predicted)} ${e(v.unit)}</strong> predicted.</p>${v.query.measurement_low!==undefined?`<p>Paired parameter scenarios: ${n(v.query.parameter_low)}–${n(v.query.parameter_high)} ${e(v.unit)}. Common flow-offset scenarios: ${n(v.query.measurement_low)}–${n(v.query.measurement_high)} ${e(v.unit)}.</p>`:''}<div class="rq-scroll"><table><caption>Residual = predicted − observed · ${e(v.unit)}</caption><tr><th>Subset</th><th>Points</th><th>Bias</th><th>RMSE</th></tr>${Object.entries(v.statistics).map(([k,s])=>`<tr><td>${e(k)}</td><td>${s.n}</td><td>${n(s.bias)}</td><td>${n(s.rmse)}</td></tr>`).join('')}</table></div>${v.comparisons.length?`<div class="rq-scroll"><table><caption>Same evaluation points · model-form comparison</caption><tr><th>Model</th><th>Bias</th><th>RMSE · ${e(v.unit)}</th></tr>${v.comparisons.map(c=>`<tr><td>${e(c.model)}</td><td>${n(c.bias)}</td><td>${n(c.rmse)}</td></tr>`).join('')}</table></div>`:''}<p>${e(v.sensitivity.scope)}</p><p class="rq-muted">Transfer uncertainty remains unquantified. These coefficients are not available for plant dispatch.</p><button data-lt="details" aria-expanded="false">Calculation, uncertainty and evidence</button><div class="lt-details" hidden></div><label>Your interpretation<textarea data-lt-findings placeholder="What does this comparison establish, and what remains unknown?"></textarea></label><button data-lt="publish">Save readable report</button><div class="lt-export"></div>`;
 }
 function details() {
  const v=result;
  q('.lt-details').innerHTML=`<h3>Fitted parameters</h3><div class="rq-scroll"><table>${Object.entries(v.parameters).map(([k,z])=>`<tr><th>${e(k)}</th><td>${n(z)}</td></tr>`).join('')}</table></div>${v.claims.map(c=>`<p><strong>${e(c.claim)} · ${e(c.outcome)}</strong><br>${e(c.method)}</p>`).join('')}${Object.entries(v.uncertainty).map(([k,note])=>`<p>${e(k)}: ${e(note)}</p>`).join('')}<div class="rq-scroll"><table><caption>Exact comparison points · ${e(v.unit)}</caption><tr><th>Subset</th><th>Input</th><th>Observed</th><th>Predicted</th><th>Residual</th></tr>${v.rows.map(r=>`<tr>${['split','x','observed','predicted','residual'].map(k=>`<td>${typeof r[k]==='number'?n(r[k]):e(r[k])}</td>`).join('')}</tr>`).join('')}</table></div><p><small>Dataset ${e(v.dataset_id)}<br>Implementation ${e(v.implementation_source)}<br>Result ${e(v.id)}</small></p>`;
 }
 function sources() {
  const p=result?.dataset||catalogue.profiles.find(p=>p.id===selected);
  q('.lt-source').innerHTML=`<p>${e(p.technology)}</p><p>${e(p.timing)}</p><p>${e(p.protocol_status)}</p>${p.unavailable.map(t=>`<p>${e(t)}</p>`).join('')}<div class="rq-scroll"><table><tr><th>Channel</th><th>Unit</th><th>Mapping</th></tr>${p.mapping.map(m=>`<tr><td>${e(m.channel)}</td><td>${e(m.unit)}</td><td>${e(m.meaning)}</td></tr>`).join('')}</table></div>${p.sources.map(s=>`<p><a href="${e(s.url)}" target="_blank" rel="noopener">${e(s.title)}</a></p>`).join('')}<p>${e(p.redistribution)}</p>${p.raw_sources.map(s=>`<p><small>${e(s.filename)}<br>SHA-256 ${e(s.sha256)}</small></p>`).join('')}`;
 }
 function values() {
  const form=q('[data-lt-form]');if(!form.reportValidity())return null;
  const d=Object.fromEntries(new FormData(form));for(const k of ['query_kw','flow_offset_bound','query_minutes','digitization_bound_k'])if(k in d)d[k]=Number(d[k]);return {profile:selected,...d};
 }
 async function refreshSaved(g) {
  const v=await api('equipment-literature-catalogue');if(live(g)){catalogue=v;q('.lt-saved').innerHTML=v.results.length?v.results.slice().reverse().map(r=>`<p><button data-lt-result="${e(r.id)}">${e(r.title)} · ${e(r.created_at)} · ${e(r.model_identity)}</button></p>`).join(''):'<p>No saved reference experiments.</p>';}
 }
 function toggle(b,el,fill) {const show=el.hidden;el.hidden=!show;b.setAttribute('aria-expanded',String(show));if(show)fill();}
 async function click(ev) {
  ev.stopPropagation();const b=ev.target.closest('button');if(!b||b.disabled)return;const a=b.dataset.lt;
  if(a==='reset'){generation++;render();status('Reference inputs reset.');return;}
  if(a==='source'){toggle(b,q('.lt-source'),sources);return;}
  if(a==='details'){toggle(b,q('.lt-details'),details);return;}
  if(a==='saved'){toggle(b,q('.lt-saved'),()=>refreshSaved(generation).catch(err=>{if(active)status(err.message);}));return;}
  const g=++generation;b.disabled=true;
  try {
   if(a==='run') {const data=values();if(!data)return;result=null;q('.lt-result').innerHTML='';status('Fitting the reference model and recording a new result…');const v=await api('equipment-literature-run',data);if(live(g)){result=v;showResult();status('Reference experiment saved. Project design unchanged.');}}
   if(b.dataset.ltResult){const v=await api('equipment-literature-result',{},b.dataset.ltResult);if(live(g)){selected=v.inputs.profile;render(v.inputs);result=v;showResult();status('Original recorded result. No recomputation.');}}
   if(a==='publish'){const r=result,findings=q('[data-lt-findings]').value;status('Saving report…');const v=await api('publish',{kind:'literature-experiment',writeup:{title:r.title,question:'What does the published reference experiment support?',method:r.equation,findings,limitations:r.boundary+' '+r.dataset.unavailable.join(' '),next_questions:'Review technology and measurement boundaries before any plant transfer.'}},r.id);if(live(g)){q('.lt-export').innerHTML=`<p><a href="${e(v.download_url)}" target="_blank" rel="noopener">Open reference report</a></p><button data-lt="export" data-publication="${v.publication_id}">Export reference bundle</button>`;status('Report saved with original data and model identities.');}}
   if(a==='export'){const v=await api('lab-start',{operation:'export',arguments:{publication_id:b.dataset.publication}});if(live(g)){q('.lt-export').innerHTML+='<p>Preparing bundle… <button data-lt="cancel" data-job="'+v.id+'">Cancel export</button></p>';poll(v.id,g);}}
   if(a==='cancel'){await api('lab-job',{cancel:true},b.dataset.job);if(live(g)){status('Export cancellation requested.');poll(b.dataset.job,g);}}
  } catch(err){if(live(g))status(err.message);}finally{b.disabled=false;}
 }
 async function poll(id,g) {
  try{const v=await api('lab-job',{},id);if(!live(g))return;if(['running','pending','queued'].includes(v.status)){setTimeout(()=>{if(live(g))poll(id,g);},500);return;}q('[data-lt=cancel]')?.closest('p')?.remove();if(v.status==='complete')q('.lt-export').innerHTML+=`<p><a download href="${e(v.download_url)}">Download reference bundle</a></p>`;status(v.description||v.status);}catch(err){if(live(g))status(err.message);}
 }
 function change(ev) {ev.stopPropagation();if(ev.target.matches('[data-lt-profile]')){generation++;selected=ev.target.value;render();status();}}
 function input(ev) {ev.stopPropagation();if(ev.target.closest('[data-lt-form]')){generation++;result=null;q('.lt-result').innerHTML='';status('Inputs changed · run a new reference experiment.');}}
 host.addEventListener('click',click);host.addEventListener('change',change);host.addEventListener('input',input);
 host.innerHTML='<p>Loading reference experiments…</p>';
 const g=++generation;api('equipment-literature-catalogue').then(v=>{if(live(g)){catalogue=v;render();status();}}).catch(err=>{if(live(g))status(err.message);});
 return {destroy(){active=false;generation++;host.removeEventListener('click',click);host.removeEventListener('change',change);host.removeEventListener('input',input);}};
}
if(typeof module!=='undefined')module.exports={literaturePlot};
