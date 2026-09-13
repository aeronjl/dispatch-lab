const test=require('node:test');
const assert=require('node:assert/strict');
const {renderFieldOperations}=require('../assets/field-operations.js');
test('conditional confidence and a historical work gate remain distinct from confirmation',()=>{
 const control={status:'selected',investigation:{episodes:[{id:'INV-1',status:'awaiting operating verification',due_hour:30,requests:['SVC-1'],recovery_belief:{status:'conditioned',restoration_probability:0.8,inputs:{impaired_capacity_kw:225,success_probability:0.8},scope:'Declared <assumptions>'},followup_belief_gate:{at_hour:13,after_order_id:'SVC-2',impairment_probability:0.6,threshold:0.5,eligible:true}}]}};
 const record={assets:{},state:{robots:{},orders:[]},decision:{service_control:control}};
 let out=renderFieldOperations({config:{}},{hour:16,row:{field_operations:record}},null);
 assert.match(out,/<details class="m-investigation"><summary>Investigation and recovery/);
 assert.match(out,/80% assumed restoration/);
 assert.match(out,/Impaired-capacity assumption 225 kW/);
 assert.match(out,/Follow-up decision at H13 after SVC-2/);
 assert.match(out,/Actual operating confirmation remains separate/);
 assert.match(out,/&lt;assumptions&gt;/);
 control.investigation.episodes[0].recovery_belief.restoration_probability=null;
 out=renderFieldOperations({config:{}},{hour:16,row:{field_operations:record}},null);
 assert.match(out,/probability unavailable/);
 assert.doesNotMatch(out,/0% assumed restoration/);
});
test('accepted recovery windows stay behind a disclosure and retain interruption reasons',()=>{
 const record={assets:{},state:{robots:{},orders:[]}};
 const recovery={version:'scheduled-load-tests/2',status:'scheduled',commitment:{start_hour:2,end_hour:4,target_kw:270,due_hour:12},commitment_changes:['Earlier window <interrupted>']};
 const out=renderFieldOperations({config:{}},{hour:2,row:{field_operations:record,decision:{recovery_planning:recovery}}},null);
 assert.match(out,/<details class="m-recovery-commitment"><summary>Reserved recovery test/);
 assert.match(out,/H2 → H4/);assert.match(out,/270 kW/);assert.match(out,/H12/);
 assert.match(out,/&lt;interrupted&gt;/);assert.match(out,/does not establish recovery/);
 assert.doesNotMatch(out,/<details[^>]*open/);
});
test('investigation disclosures preserve uncertainty and escape findings',()=>{
 const investigation={scope:'Original information only',episodes:[{id:'INV-1',status:'awaiting operating verification',due_hour:20,requests:['read-1','reset-1'],reason:'Cause <unknown>',selection:{selection_id:'saved-selection',candidates:[{strategy:'inspect-first',status:'feasible',restoration_probability:.3,eligible:true}],selected:{strategy:'inspect-first'},full_calculation_path:'/original/selection'},finding:{reason:'Closed contact; damage remains possible'},belief_after_intervention:'Prior no longer applicable'}]};
 const record={assets:{},state:{robots:{},orders:[]},decision:{service_control:{status:'selected',investigation}}};
 const out=renderFieldOperations({config:{}},{hour:7,row:{field_operations:record}},null);
 assert.match(out,/<details class="m-investigation"><summary>Investigation and recovery/);
 assert.match(out,/30%/);assert.match(out,/H20/);assert.match(out,/saved-selection/);
 assert.match(out,/Cause &lt;unknown&gt;/);assert.match(out,/Prior no longer applicable/);
 assert.doesNotMatch(out,/Observer confirmation at/);
});
test('old archives and initial service state are explicitly labelled',()=>{
  assert.match(renderFieldOperations({config:{}},{hour:2},null),/no recorded field operations/);
  assert.match(renderFieldOperations({config:{field_operations:{enabled:true}}},{hour:0},null),/Step forward/);
});
test('post-service evidence is disclosed and cannot turn a shortfall into a successful repair',()=>{
 const verification={at_hour:8,required_tests:2,maximum_age_hours:8,attempts:[{order_id:'repair-1',status:'follow-up supported',qualifying:[{},{}],reason:'Cause <unknown>'}],previous_test:{outcome:'tracking shortfall',reason:'Load did not track',inputs:{packet:{hour:7,available_at:8}},operands:{requested_kw:300,measured_kw:225,balance_hydrogen_kg:4.32,expected_hydrogen_kg:4.32},resource_check:{status:'feasible at recorded estimate'},scope:'No hidden repair success'}};
 const control={status:'selected',scope:'Observed work only',verification};
 const record={version:'plant-service-contracts/11',assets:{},state:{robots:{},orders:[]},decision:{service_control:control}};
 const out=renderFieldOperations({config:{}},{hour:8,row:{field_operations:record}},null);
 assert.match(out,/<details class="m-load-verification"><summary>Post-service load tests/);
 assert.match(out,/2 qualifying test\(s\), 2 required within 8 h/);
 assert.match(out,/300 \/ 225 kW/);assert.match(out,/tracking shortfall/);
 assert.match(out,/Cause &lt;unknown&gt;/);assert.doesNotMatch(out,/<unknown>/);
 assert.match(out,/does not establish recovery/);
});
test('service renderer escapes recorded reasons, includes energy and costs, and distinguishes verification',()=>{
  const out=renderFieldOperations({run_id:'r',config:{},field_operations_model:{assumptions:[]}}, {hour:3,row:{field_operations:{version:'field-operations/1',assets:{rover:true},state:{robots:{rover:{energy_kwh:1,status:'available'}},orders:[{id:'wo',kind:'reset',status:'awaiting verification',phase:'perform',reason:'<script>bad</script>',reported:'Tracking required'}],service_kits:1,cleaning_kits:2},charge_input_kwh:.1,charging_loss_kwh:.01,robot_use_kwh:.2,soiling_loss_kw:4}}}, {field_operations:{components:{rover:2},total_eur:2,variable_and_wear_eur:1,basis:'Recorded work'}});
  assert.match(out,/awaiting verification/);assert.match(out,/&lt;script&gt;/);assert.doesNotMatch(out,/<script>/);
  assert.match(out,/0.1 kWh/);assert.match(out,/€2/);assert.match(out,/m-cost/);
});
test('coordinated service evidence stays in the utility and preserves original deadlines',()=>{
 const control={status:'selected-with-unmet-obligations', selected_candidate_id:'repair-2', input_id:'recorded-input', scope:'Bounded saved-information comparison', unmet_deadlines:['repair-1'], obligations:[{id:'repair-1',kind:'repair',status:'queued',due_hour:6,attempts:['repair-1','repair-2'],deadline_missed_at:6}],energy_targets:{rover:{robot:'rover',energy_kwh:2,due_hour:5}}, candidates:[{candidate_id:'<bad>',status:'unresolved',evaluation:{constraints:[{reason:'<script>unsafe</script>'}]}},{candidate_id:'repair-2',status:'feasible',evaluation:{process_plan:{predicted:{methane_kg:12}},mission_decision_eur:30}}]};
 const record={version:'plant-service-contracts/11',assets:{rover:true},state:{robots:{},orders:[]},decision:{service_control:control}};
 const out=renderFieldOperations({config:{}},{hour:7,row:{field_operations:record}},null);
 assert.match(out,/Recorded service decision/);assert.match(out,/original deadline H6/);
 assert.match(out,/2 attempt\(s\); missed at H6/);assert.match(out,/original H5/);
 assert.match(out,/<summary>Candidate calculations<\/summary>/);
 assert.match(out,/predicted 12 kg CH₄/);assert.match(out,/recorded-input/);
 assert.match(out,/&lt;script&gt;/);assert.doesNotMatch(out,/<script>|<bad>/);
 delete record.decision;
 assert.doesNotMatch(renderFieldOperations({config:{}},{hour:7,row:{field_operations:record}},null),/Recorded service decision/);
});
test('uncertain service evidence stays in the inspector and does not imply verified repair',()=>{
 const belief={scope:'Conditional <model>',durations:{cleaning:{completed_phases:1,censored_phases:2,mean_factor:1.5,bounds:[.5,2],status:'insufficient evidence'}},reliability:{cleaning:{returned:1,interrupted:1,pending_verifications:1}}};
 const record={assets:{},state:{robots:{},orders:[]},decision:{uncertainty_beliefs:belief}};
 const out=renderFieldOperations({config:{}},{hour:4,row:{field_operations:record}},null);
 assert.match(out,/What remains uncertain/);assert.match(out,/Conditional &lt;model&gt;/);assert.match(out,/insufficient evidence/);assert.match(out,/Recovery awaiting verification/);
});
