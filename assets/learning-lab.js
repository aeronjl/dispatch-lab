/* An opt-in Sites workspace. All fitted values and comparisons come from Python. */
function createLearningLab({request, workspace, page, getIndex, openStudy, publish}) {
 const q=s=>workspace.querySelector(s), e=sitesEscape;
 const number=v=>Number.isFinite(v)?v.toLocaleString('en-GB',{maximumFractionDigits:3}):'Unavailable';
 let saved=null, episodes=[], timer=null, generation=0, selected=null;
 function show(html){generation++;clearTimeout(timer);page(`<nav class="si-actions"><button data-si="lab-open">Learning & policies</button><button data-si="studies">Production studies</button></nav>${html}`);}
 function options(rows){return rows.map(r=>`<option value="${e(r.id)}">${e(r.name||r.id.slice(0,12))}</option>`).join('');}
 async function open(){const value=await request('lab-index',{},null);if(!value)return;saved=value;
  show(`<h1>Learning & policies</h1><p>Freeze what the controller could know, evaluate an estimator, then compare an explicitly registered policy. Simulated channels remain assumptions.</p>
   <div class="si-actions"><button data-si="lab-data">Select observation episodes</button><button data-si="lab-teach">Try a constructed dataset</button><button data-si="lab-fit">Train & evaluate</button><button data-si="lab-deploy">Register a policy</button><button data-si="lab-compare">Build a matched study</button></div>
   <h2>Observation datasets</h2>${value.datasets.map(d=>`<p><button data-si="lab-view" data-kind="dataset" data-id="${d.id}">${e(d.name)}</button> · ${number(d.sample_count)} decision boundaries</p>`).join('')||'<p>No datasets frozen yet. Select completed episodes, or use the explicitly constructed teaching fixture.</p>'}
   <h2>Evaluations</h2>${value.evaluations.map(r=>`<p><button data-si="lab-evaluation" data-id="${r.id}">${e(r.name)}</button> · ${e(r.status)}</p>`).join('')||'<p>Training does not start until its data and protocol are selected.</p>'}
   <h2>Registered policies</h2>${value.deployments.map(d=>`<p><button data-si="lab-view" data-kind="deployment" data-id="${d.id}">${e(d.name)}</button> · ${e(d.mode)}</p>`).join('')||'<p>The reference controllers remain available without a learned model.</p>'}
   <h2>Worker history</h2>${value.jobs.map(j=>`<p><button data-si="lab-job-open" data-id="${j.id}">${e(j.operation)}</button> · ${e(j.status)}</p>`).join('')}
   <p>Heavy study, data, training and export jobs share one worker slot. Training is limited to 100,000 observations. No real plant control is connected.</p><button data-si="lab-session-form">Participant walkthrough</button>`);
 }
 async function dataForm(){const value=await request('lab-episodes',{},null);if(!value)return;episodes=value.episodes;
  show(`<h1>Freeze observation boundaries</h1><p>Choose complete episodes for training, validation and test. Overlapping site/weather windows cannot cross splits, even with different seeds or controllers. Incomplete episodes stay available in their original studies.</p><label>Dataset name<input data-lab="name" value="Observed operation dataset"></label>
   ${episodes.map((r,i)=>`<label>${e(r.name)} · ${e(r.start.slice(0,10))} → ${e(r.end.slice(0,10))}<select data-episode="${i}" ${r.complete?'':'disabled'}><option value="">${r.complete?'Exclude':'Incomplete episode'}</option><option value="train">Training</option><option value="validation">Validation</option><option value="test">Test</option></select></label>`).join('')}
   <p>Additional separation required:</p>${['site','design','equipment'].map(k=>`<label class="si-check"><input type="checkbox" data-holdout="${k}">Unseen ${e(k)} across splits</label>`).join('')}
   <button data-si="lab-freeze">Freeze dataset</button>`);
 }
 function trainingForm(){show(`<h1>Train and evaluate an estimator</h1><p>The split registry is frozen first. Training fits weights; validation sets an empirical error band; test results cannot select the model. Missing or unsupported channels produce an incomplete result.</p>
  <label>Dataset<select data-lab="dataset_id">${options(saved.datasets)}</select></label><label>Question<select data-lab="task">${saved.tasks.map(t=>`<option value="${t.id}">${e(t.name)} / ${e(t.unit)}</option>`).join('')}</select></label>
  <label>Model name<input data-lab="name" value="Observed channel estimator"></label><label>Ridge penalty<input type="number" min="0.000001" max="10000" step="any" data-lab="ridge" value="1"></label><label>Recorded seed<input type="number" data-lab="seed" value="7"></label>
  <p>The fit is deterministic; the seed is recorded for protocol provenance and does not manufacture independent samples. Duration regression scores completed phases; censored work remains excluded and disclosed. It is not a remaining-life model.</p><button data-si="lab-train" ${saved.datasets.length?'':'disabled'}>Fit baselines and model</button>`);}
 function deployForm(){show(`<h1>Register an experimental policy</h1><p>A registration pins the model and its dataset. Later training never updates it silently. Reserve preferences are editable assumptions; execution still enforces physical limits and service prerequisites.</p>
  <label>Policy name<input data-lab="name" value="Experimental planning aid"></label><label>Model<select data-lab="model_id"><option value="">No fitted model · reserve policy only</option>${options(saved.models)}</select></label>
  <label>Use<select data-lab="mode"><option value="shadow">Record predictions only</option><option value="forecast-aid">Revise the first future PV prediction</option><option value="homeostatic">Optimise reserve needs</option></select></label>
  <label>Inference budget / ms<input data-lab="budget_ms" type="number" min="0.01" max="100" step="any" value="20"></label>
  <button data-si="lab-reserves">Reserve assumptions</button><div data-lab-reserves hidden>${[['battery_fraction','Battery fraction',.2],['hydrogen_fraction','Hydrogen fraction',.2],['co2_fraction','CO₂ fraction',.1],['thermal_fraction','Idle thermal fraction',.2],['shortage_weight','Shortage penalty / objective units',.5],['service_hours','Service look-ahead / hours',2]].map(([key,label,value])=>`<label>${label}<input data-reserve="${key}" type="number" step="any" min="0" value="${value}"></label>`).join('')}</div>
  <button data-si="lab-register">Freeze registration</button>`);}
 function compareForm(){const index=getIndex();show(`<h1>Compare policy choices</h1><p>Build a reusable study with Greedy and both MPC objectives, then each selected experimental policy under methane and economic objectives. Every case uses the same design, environment and seed. Freezing it does not execute it.</p>
  <label>Design<select data-lab="design_id">${options(index.designs)}</select></label><label>Environment<select data-lab="environment_id">${index.environments.map(r=>`<option value="${r.id}">${e(r.start)} / ${e(r.information)}</option>`).join('')}</select></label>
  <label>Study name<input data-lab="name" value="Policy and reserve comparison"></label><label>Scenario seed<input data-lab="seed" type="number" value="7"></label>${saved.deployments.map(d=>`<label class="si-check"><input type="checkbox" data-deployment="${d.id}">${e(d.name)} · ${e(d.mode)}</label>`).join('')}
  <button data-si="lab-template" ${index.designs.length&&index.environments.length?'':'disabled'}>Freeze matched study and template</button>`);}
 async function job(id){const current=++generation;clearTimeout(timer);page(`<h1>Learning worker</h1><div data-lab-progress role="status">Starting…</div><button data-si="lab-cancel" data-id="${id}">Cancel worker</button><button data-si="lab-open">Back to learning</button>`);
  async function poll(){const value=await request('lab-job',{},id);if(!value||current!==generation)return;const target=q('[data-lab-progress]');if(!target)return;
   target.innerHTML=`<p>${e(value.status)} · ${e(value.description||'')}</p>${value.result?`<p>Saved ${e(value.result_kind)}. ${e(value.result.reason||'')}</p>${value.download_url?`<a href="${e(value.download_url)}">Download ZIP</a>`:''}${value.result_kind==='evaluation'?`<button data-si="lab-evaluation" data-id="${value.result.id}">Read comparison</button>`:''}<button data-si="lab-open">Continue</button>`:''}`;
   if(value.status==='running')timer=setTimeout(poll,750);
  }await poll();
 }
 async function start(operation,args){const value=await request('lab-start',{operation,arguments:args},null);if(value)await job(value.id);}
 async function evaluation(id){const v=await request('lab-get',{kind:'evaluation'},id);if(!v)return;selected=v;
  show(`<h1>${e(v.name)}</h1><p>${e(v.status)} · ${e(v.reason||v.scope)}</p>${v.comparisons?`<div class="si-table"><table><tr><th>Estimator</th><th>Absolute error</th><th>Band coverage</th><th>Unavailable</th></tr>${Object.entries(v.comparisons).map(([k,m])=>`<tr><td>${e(k)}</td><td>${number(m.mae)}</td><td>${number(m.coverage)}</td><td>${m.unavailable} / ${m.count}</td></tr>`).join('')}</table></div><p>Empirical bands from validation. Coverage is the observed fraction on supported test predictions; unavailable cases stay in the denominator shown separately. No field-performance claim.</p>`:''}
   <p>Examples: training ${v.rows_per_split.train}, validation ${v.rows_per_split.validation}, test ${v.rows_per_split.test}.</p><p>${e(v.decision_consequences||'No operating benefit is inferred.')}</p>
   <button data-si="lab-view" data-kind="evaluation" data-id="${id}">Trace data, operands and exclusions</button><button data-si="lab-publish" data-id="${id}">Write up this evaluation</button><button data-si="lab-deploy">Register a policy</button>`);
 }
 async function sessionForm(){const v=await request('lab-questions',{},null);if(!v)return;show(`<h1>Participant comprehension</h1><p>Record actual participant words separately from facilitator interpretations and scripted checks. Leave this session unrecorded until someone has taken part. Use a pseudonym.</p><label>Participant pseudonym<input data-lab="participant"></label><label>Facilitator<input data-lab="facilitator"></label><label>Basis<select data-lab="basis"><option value="participant-session">Actual participant session</option><option value="agent-rehearsal">Agent rehearsal only</option></select></label>${Object.entries(v.questions).map(([k,text])=>`<label>${e(text)}<textarea data-response="${k}"></textarea></label>`).join('')}<label>Misunderstandings and resolutions / JSON<textarea data-lab="issues">[]</textarea></label><p>Each issue names question, misunderstanding, severity (minor/material) and resolution (blank if unresolved). Revisions are separate sessions; original words are preserved.</p><button data-si="lab-session">Save session record</button><h2>Saved sessions</h2>${v.sessions.map(s=>`<p>${e(s.participant)} · ${e(s.basis)} · ${e(s.status)}</p>`).join('')||'<p>No participant evidence recorded.</p>'}`);}
 const field=k=>q(`[data-lab="${k}"]`).value;
 async function act(el){const action=el.dataset.si,id=el.dataset.id;if(!action?.startsWith('lab-'))return false;
  if(action==='lab-open')await open();
  else if(action==='lab-data')await dataForm();
  else if(action==='lab-teach')await start('fixture',{});
  else if(action==='lab-freeze')await start('dataset',{name:field('name'),selections:[...workspace.querySelectorAll('[data-episode]')].filter(x=>x.value).map(x=>({study_id:episodes[x.dataset.episode].study_id,case_id:episodes[x.dataset.episode].case_id,split:x.value})),holdout_axes:[...workspace.querySelectorAll('[data-holdout]:checked')].map(x=>x.dataset.holdout)});
  else if(action==='lab-fit')trainingForm();
  else if(action==='lab-train')await start('train',{dataset_id:field('dataset_id'),task:field('task'),name:field('name'),ridge:Number(field('ridge')),seed:Number(field('seed'))});
  else if(action==='lab-job-open')await job(id);
  else if(action==='lab-cancel'){await request('lab-job',{cancel:true},id);await job(id);}
  else if(action==='lab-deploy'){const v=await request('lab-index',{},null);if(!v)return true;saved=v;deployForm();}
  else if(action==='lab-reserves')q('[data-lab-reserves]').hidden=!q('[data-lab-reserves]').hidden;
  else if(action==='lab-register'){const v=await request('lab-register',{name:field('name'),model_id:field('model_id')||null,mode:field('mode'),budget_ms:Number(field('budget_ms')),reserves:{version:'homeostatic-reserves/1',...Object.fromEntries([...workspace.querySelectorAll('[data-reserve]')].map(x=>[x.dataset.reserve,Number(x.value)]))}},null);if(v)await open();}
  else if(action==='lab-compare')compareForm();
  else if(action==='lab-template'){const v=await request('lab-template',{name:field('name'),design_id:field('design_id'),environment_id:field('environment_id'),seed:Number(field('seed')),deployment_ids:[...workspace.querySelectorAll('[data-deployment]:checked')].map(x=>x.dataset.deployment)},null);if(v){close();await openStudy(v.study_id);}}
  else if(action==='lab-evaluation')await evaluation(id);
  else if(action==='lab-view'){const v=await request('lab-get',{kind:el.dataset.kind},id);if(v){selected=v;show(`<h1>Recorded ${e(el.dataset.kind)}</h1><p>This is a saved record. Missing original provenance is not reconstructed.</p><pre>${e(JSON.stringify(v,null,2))}</pre>${el.dataset.kind==='dataset'&&v.episodes.every(x=>x.study_id)?`<button data-si="lab-reconstruct" data-id="${id}">Reconstruct from original partitions</button>`:''}`);}}
  else if(action==='lab-reconstruct'){const v=await request('lab-reconstruct',{},id);if(v)show(`<h1>Dataset reconstruction</h1><p>${e(v.status)} · ${e(v.dataset_id)}</p>`);}
  else if(action==='lab-publish'){close();await publish('evaluation',id);}
  else if(action==='lab-session-form')await sessionForm();
  else if(action==='lab-session'){const v=await request('lab-session',{participant:field('participant'),facilitator:field('facilitator'),basis:field('basis'),responses:Object.fromEntries([...workspace.querySelectorAll('[data-response]')].map(x=>[x.dataset.response,x.value])),issues:JSON.parse(field('issues'))},null);if(v)await sessionForm();}
  return true;
 }
 function close(){clearTimeout(timer);generation++;}
 return {open,act,close};
}
