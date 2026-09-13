const {test,expect}=require('@playwright/test');
const fs=require('node:fs');

async function openServices(page){
 await page.goto('/');await page.locator('.m-plant').waitFor();
 await page.locator('[data-do=menu]').click();await page.locator('[data-panel=services]').click();
 await page.locator('[data-sa=open]').focus();await page.keyboard.press('Enter');
}
const description={status:'available',hours:6,orders:[{order_id:'WORK-1',kind:'routine-service',action:'routine-service',shared_visit:['WORK-1','WORK-2']}],robots:[],reserve_available:false,energy_targets:[],note:'Original forecast and dispatch prices; complete itinerary moves together.'};
const summary=n=>({state:'feasible',prediction:{methane_kg:n,reactor_starts:1,ending:{battery_kwh:300,h2_kg:10,co2_kg:480,temperature_c:260},temperature_c:[20,100,180,250,260,260]},solver:{status:'optimal',fallback_used:false},service_decision_eur:530,total_decision_eur:600,assumed_contribution_eur:n-600,ending_service_stocks:{'stock:maintenance':6},unselected_work:[],original_obligations:[],terminal_work:[],scope:'Conditional continuation. No future repair benefit is inferred.'});
const answer={status:'complete',controller:'Greedy',hour:0,hours:6,note:'Complete shared itinerary postponed.',same_application_source:true,same_service_source:true,baseline:{summary:summary(30),evaluation:{constraints:[]}},alternative:{summary:summary(31),evaluation:{constraints:[]}},recorded:{process_prediction:{methane_kg:29},process_solver:{status:'greedy'},service_status:'local rule'},forecast_source:{id:'saved-issue',available_at:'2026-04-10T00:00:00Z'},snapshot_id:'recorded-snapshot',comparison_id:'ui-rendering-fixture',original_source:'saved-source',replanner_source:'saved-source',cost_version:'original-prices',service_cost_version:'original-service-prices',context_note:'Recorded original is separate from the recalculated baseline.'};

test('older decisions explicitly lack original service context and return by keyboard',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await openServices(page);
 await expect(page.locator('[data-sa=status]')).toContainText('not saved');
 await page.keyboard.press('Escape');await expect(page.locator('[data-sa=workspace]')).toBeHidden();await expect(page.locator('[data-sa=open]')).toBeFocused();
 await page.keyboard.press('Escape');await expect(page.locator('.m-utility')).toBeHidden();
 await expect(page.locator('[data-do=menu]')).toBeFocused();expect(errors).toEqual([]);
});

test('an older menu render cannot steal focus from the next keyboard interaction',async({page})=>{
 await page.goto('/');await page.locator('.m-plant').waitFor();
 await page.evaluate(()=>{
  const original=window.requestAnimationFrame, pending=[];
  window.requestAnimationFrame=callback=>{pending.push(callback);return 0;};
  try{
   document.querySelector('[data-do=menu]').click();
   document.querySelector('[data-panel=services]').click();
   document.querySelector('[data-sa=open]').focus();
  }finally{window.requestAnimationFrame=original;}
  for(const callback of pending)callback(performance.now());
 });
 await expect(page.locator('[data-sa=open]')).toBeFocused();
 await page.keyboard.press('Enter');
 await expect(page.locator('[data-sa=workspace]')).toBeVisible();
 await expect(page.locator('[data-sa=status]')).toContainText('not saved');
});

test('paired response renders, changed inputs stay labelled, and a late response is ignored',async({page})=>{
 const errors=[],requests=[];let delayResolve,hold=false;page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/dispatch/service-alternative',async route=>{
  const r=route.request().postDataJSON();requests.push(r);
  if(r.operation==='describe')return route.fulfill({json:{...description,key:r.key}});
  if(r.operation==='cancel')return route.fulfill({json:{status:'cancelled',key:r.key}});
  if(hold&&r.operation==='start')await new Promise(resolve=>delayResolve=resolve);
  return route.fulfill({json:{...answer,key:r.key}});
 });
 await openServices(page);await expect(page.locator('[data-sa=order]')).toHaveValue('WORK-1');
 await page.locator('[data-sa=calculate]').click();await expect(page.locator('[data-sa=status]')).toContainText('Comparison complete');
 await expect(page.locator('[data-sa=result]')).toContainText('530');
 await page.locator('[data-sa=details]').click();await expect(page.locator('[data-sa=evidence]')).toContainText('29 kg methane');
 await page.setViewportSize({width:390,height:844});
 await page.locator('[data-sa=delay]').fill('2');await expect(page.locator('[data-sa=status]')).toContainText('previous inputs');
 await expect(page.locator('[data-sa=result]')).toHaveAttribute('data-stale','true');
 await expect(page.locator('[data-sa=previous]')).toBeVisible();
 hold=true;await page.locator('[data-sa=calculate]').click();await expect(page.locator('[data-sa=cancel]')).toBeVisible();
 await expect.poll(()=>typeof delayResolve).toBe('function');
 await page.locator('[data-sa=delay]').fill('3');delayResolve();
 await expect(page.locator('[data-sa=status]')).toContainText('previous inputs');
 await expect(page.locator('[data-sa=delay]')).toHaveValue('3');
 await expect.poll(()=>requests.filter(r=>r.operation==='cancel').length).toBeGreaterThan(0);
 await page.locator('[data-sa=workspace]').scrollIntoViewIfNeeded();
 fs.mkdirSync('build/services/alternatives/browser',{recursive:true});
 await page.locator('.m-utility').screenshot({path:'build/services/alternatives/browser/narrow-comparison.png'});
 const sizes=await page.locator('.m-utility').evaluate(n=>[n.scrollWidth,n.clientWidth]);expect(sizes[0]).toBeLessThanOrEqual(sizes[1]);
 await page.keyboard.press('Escape');await expect(page.locator('[data-sa=open]')).toBeFocused();expect(errors).toEqual([]);
});

test('closing a pending comparison cancels its generation and reopening ignores it',async({page})=>{
 let release;const calls=[];
 await page.route('**/dispatch/service-alternative',async route=>{
  const r=route.request().postDataJSON();calls.push(r);
  if(r.operation==='describe')return route.fulfill({json:{...description,key:r.key}});
  if(r.operation==='cancel')return route.fulfill({json:{status:'cancelled',key:r.key}});
  await new Promise(resolve=>release=resolve);return route.fulfill({json:{...answer,key:r.key}});
 });
 await openServices(page);await page.locator('[data-sa=calculate]').click();await expect.poll(()=>typeof release).toBe('function');
 await page.keyboard.press('Escape');await page.locator('[data-sa=open]').click();
 await expect(page.locator('[data-sa=status]')).toContainText('Original forecast');release();
 await expect(page.locator('[data-sa=result]')).toBeEmpty();
 await expect.poll(()=>calls.filter(r=>r.operation==='cancel').length).toBe(1);
});

test('compatible procedures retain original identities, reveal restrictions, and preserve infeasible outcomes',async({page})=>{
 const calls=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
 const choices={...description,orders:[
  {order_id:'CLEAN-1',kind:'cleaning',action:'clean-section',procedures:[{procedure_id:'wet-original',label:'Portable wet brush',scope:'Uses water and crew. Permanent damage remains.',unavailable:null}]},
  {order_id:'READ-1',kind:'inspection',action:'read-trip-contact',procedures:[{procedure_id:'rover-original',label:'Ground inspector',scope:'Same contact; no finding is credited.',unavailable:'Awaiting retrieval'}]},
 ]};
 await page.route('**/dispatch/service-alternative',async route=>{
  const r=route.request().postDataJSON();calls.push(r);
  if(r.operation==='describe')return route.fulfill({json:{...choices,key:r.key}});
  if(r.operation==='cancel')return route.fulfill({json:{status:'cancelled',key:r.key}});
  return route.fulfill({json:{...answer,key:r.key,status:'incomplete',note:'Original restriction retained.',alternative:{summary:{state:'infeasible',prediction:null},evaluation:{constraints:[{reason:'Awaiting retrieval'}]}}}});
 });
 await openServices(page);await page.locator('[data-sa=kind]').selectOption('procedure');
 await expect(page.locator('[data-sa=procedure]')).toHaveValue('wet-original');
 await expect(page.locator('[data-sa=procedure-scope]')).toContainText('Uses water and crew');
 await expect(page.locator('[data-sa=delay]')).toHaveCount(0);
 await page.locator('[data-sa=order]').selectOption('READ-1');
 await expect(page.locator('[data-sa=procedure]')).toHaveValue('rover-original');
 await expect(page.locator('[data-sa=procedure-scope]')).toContainText('Original restriction: Awaiting retrieval');
 await page.locator('[data-sa=calculate]').click();
 await expect(page.locator('[data-sa=status]')).toContainText('Comparison incomplete');
 expect(calls.find(c=>c.operation==='start').alternative).toEqual({kind:'procedure',order_id:'READ-1',procedure_id:'rover-original'});
 await expect(page.locator('[data-sa=result]')).toContainText('Awaiting retrieval');
 await expect(page.locator('[data-sa=result]')).toContainText('530');
 await page.locator('[data-sa=order]').selectOption('CLEAN-1');
 await expect(page.locator('[data-sa=procedure]')).toHaveValue('wet-original');
 await expect(page.locator('[data-sa=previous]')).toBeVisible();
 await page.setViewportSize({width:390,height:844});
 const sizes=await page.locator('.m-utility').evaluate(n=>[n.scrollWidth,n.clientWidth]);expect(sizes[0]).toBeLessThanOrEqual(sizes[1]);
 await page.keyboard.press('Escape');await expect(page.locator('[data-sa=open]')).toBeFocused();
 expect(errors).toEqual([]);
});

test('investigation choice reveals branch predictions, original assumptions and incomplete outcomes',async({page})=>{
 const errors=[],calls=[];page.on('pageerror',e=>errors.push(e.message));
 const investigation={origin_hour:0,selection_id:'original-investigation',selected_strategy:'inspect-first',selected_label:'Inspect first',strategies:[{value:'direct-intervention',label:'Intervene directly'}],note:'Original belief, forecast and prices. No later repair outcomes.'};
 const branch=(id,finding,probability)=>({branch_id:id,finding,probability,mechanism_hypothesis:'equipment-damage',restoration_hypothesis:true,requested_remedy:'module-replacement',test_start_hour:4,test_end_hour:6,test_target_kw:300,ending_diagnostic_state:'Unverified in this prediction',required_followup:'Actual operating observations required',conditional_ending_service_stocks:{'stock:repair':2},unselected_requests:[],outstanding_recovery:[]});
 const original={status:'feasible',cases:[branch('closed','closed',.7),branch('open','open',.3)],process:{branches:[{branch_id:'closed',predicted:summary(20).prediction,service_decision_eur:50},{branch_id:'open',predicted:summary(18).prediction,service_decision_eur:60}],expected:{methane_kg:19.4},solver:{status:'solved'}}};
 const value={...answer,kind:'investigation',status:'incomplete',selection_id:'original-investigation',objective:'methane',risk_weight:.2,service_stock_units:{'stock:repair':'kit'},original_prices:{process:'dispatch-price-v1',service:'service-price-v1'},comparison:{inputs:{belief:{assumptions:{source:'illustrative-fixture-prior'}}},strategies:{'inspect-first':original,'direct-intervention':{status:'incomplete',cases:[]}}},recorded:{strategies:{'inspect-first':original}},baseline:{strategy:'inspect-first',label:'Inspect first',summary:{state:'feasible',expected:{methane_kg:19.4,total_decision_eur:55},restoration_probability:.8,restoration_requirement:.3,eligible:true,solver:{status:'time-limit'}}},alternative:{strategy:'direct-intervention',label:'Intervene directly',summary:{state:'incomplete',expected:null,restoration_probability:null,restoration_requirement:.3,eligible:false,conditions:['Crew arrives after the prediction boundary']}}};
 await page.route('**/dispatch/service-alternative',async route=>{
  const r=route.request().postDataJSON();calls.push(r);
  if(r.operation==='describe')return route.fulfill({json:{...description,orders:[],investigation,key:r.key}});
  return route.fulfill({json:{...value,key:r.key}});
 });
 await openServices(page);
 await expect(page.locator('[data-sa=kind]')).toHaveValue('investigation');
 await expect(page.locator('[data-sa=parameters]')).toContainText('Originally selected: Inspect first');
 await page.locator('[data-sa=calculate]').click();
 await expect(page.locator('[data-sa=status]')).toContainText('Comparison incomplete');
 expect(calls.find(c=>c.operation==='start').alternative).toEqual({kind:'investigation',selection_id:'original-investigation',strategy:'direct-intervention'});
 await expect(page.locator('[data-sa=result]')).toContainText('Expected methane');
 await expect(page.locator('[data-sa=result]')).toContainText('Crew arrives after');
 await expect(page.locator('[data-sa=evidence]')).toBeHidden();
 await page.locator('[data-sa=details]').click();
 await expect(page.locator('[data-sa-branch=baseline-0]')).toBeVisible();
 await page.locator('[data-sa=branch][data-arm=baseline]').selectOption('1');
 await expect(page.locator('[data-sa-branch=baseline-0]')).toBeHidden();
 await expect(page.locator('[data-sa-branch=baseline-1]')).toBeVisible();
 await expect(page.locator('[data-sa=evidence]')).toContainText('Unverified');
 await expect(page.locator('[data-sa=evidence]')).toContainText('stock:repair / kit');
 await expect(page.locator('[data-sa=evidence]')).toContainText('illustrative-fixture-prior');
 await expect(page.locator('[data-sa=evidence]')).toContainText('dispatch-price-v1');
 await expect(page.locator('[data-sa=result]')).toHaveAttribute('data-stale','false');
 await page.setViewportSize({width:390,height:844});
 const sizes=await page.locator('.m-utility').evaluate(n=>[n.scrollWidth,n.clientWidth]);expect(sizes[0]).toBeLessThanOrEqual(sizes[1]);
 fs.mkdirSync('build/services/investigation-alternatives/browser',{recursive:true});
 await page.locator('.m-utility').screenshot({path:'build/services/investigation-alternatives/browser/narrow-rendering-fixture.png'});
 await page.keyboard.press('Escape');await expect(page.locator('[data-sa=open]')).toBeFocused();expect(errors).toEqual([]);
});

test('a later service interval returns to the recorded investigation selection before replanning',async({page})=>{
 const calls=[];
 await page.route('**/dispatch/service-alternative',async route=>{
  const r=route.request().postDataJSON();calls.push(r);
  return route.fulfill({json:{...description,key:r.key,orders:[],investigation:r.hour===3?{origin_hour:3,selection_id:'at-hour-3',selected_strategy:'inspect-first',selected_label:'Inspect first',strategies:[{value:'direct-intervention',label:'Intervene directly'}],note:'Original decision H3.'}:{origin_hour:3,note:'Return to original investigation'}}});
 });
 await openServices(page);await page.locator('[data-sa=origin]').click();
 await expect(page.locator('[data-sa=kind]')).toHaveValue('investigation');
 await expect(page.locator('[data-sa=origin]')).toHaveCount(0);
 expect(calls.at(-1).hour).toBe(3);
 await expect(page.locator('[data-sa=parameters]')).toContainText('Original decision H3');
 await page.keyboard.press('Escape');await expect(page.locator('[data-sa=open]')).toBeFocused();
});
