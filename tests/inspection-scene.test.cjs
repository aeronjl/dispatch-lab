const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),z=require('node:zlib');
const {fieldVisualState}=require('../assets/field-scene.js');
const {renderFieldOperations}=require('../assets/field-operations.js');
const fixtures=JSON.parse(z.gunzipSync(fs.readFileSync('tests/fixtures/inspection-services.json.gz')));

test('paired readers retain their own mission poses when one acquisition is blocked',()=>{
 const result=structuredClone(fixtures['reader-drift'].value);
 const row=result.records.Greedy[4];
 const state=row.decision.field_operations;
 const mobile=state.orders.find(o=>o.reader==='mobile');mobile.status='queued';delete mobile.started_hour;
 state.executive.orders=state.executive.orders.filter(m=>m.order_id!==mobile.id);
 state.planned_missions=state.planned_missions.filter(m=>m.order.order_id!==mobile.id);
 const actors=fieldVisualState(result,'Greedy',{hour:4,fraction:.5,playing:true}).actors;
 assert.equal(actors.find(a=>a.asset==='fixed_reader').phase,'perform');
 assert.equal(actors.find(a=>a.asset==='rover').phase,'queued');
});
test('inspection rendering uses recorded evidence, escapes text and does not expose retrospective injection',()=>{
 const result=fixtures['reader-drift'].value,row=structuredClone(result.records.Greedy[5]);
 row.field_operations.state.inspection.reason='<script>not executable</script>';
 const html=renderFieldOperations(result,{hour:6,row},fixtures['reader-drift'].economics.controllers.Greedy[6]);
 assert.match(html,/Contact evidence/);assert.match(html,/channel isolated/);
 assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
 assert.doesNotMatch(html,/fixed_reader_drift_vph|inspection_samples|contact_stuck/);
});
