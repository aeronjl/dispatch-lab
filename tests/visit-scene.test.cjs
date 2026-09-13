const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),z=require('node:zlib');
const {fieldVisualState}=require('../assets/field-scene.js');
const {renderFieldOperations}=require('../assets/field-operations.js');
const fixtures=JSON.parse(z.gunzipSync(fs.readFileSync('tests/fixtures/visit-services.json.gz')));
const actor=(name,h,f=0)=>fieldVisualState(fixtures[name].value,'Greedy',{hour:h,fraction:f,playing:f>0}).actors.find(a=>a.asset==='human');

test('one vehicle follows successive jobs without a premature future pose',()=>{
 assert.equal(actor('supplies',2,.5).order,'SVC-0001');
 assert.equal(actor('supplies',3,.49).order,'SVC-0001');
 assert.equal(actor('supplies',3,.51).order,'SVC-0002');
 assert.equal(actor('supplies',4,.25).order,'SVC-0003');
 const a=actor('supplies',3,.49),b=actor('supplies',3,.51);
 assert.equal(a.x,b.x);assert.equal(a.y,b.y);assert.equal(b.phase,'perform');
 assert.equal(actor('supplies',4,.75).phase,'return');
});
test('on-site transfer leads to the original technician pose and failed later jobs do not hide the crew',()=>{
 const transfer=actor('interventions',9,.625),work=actor('interventions',10,.4);
 assert.equal(transfer.kind,'module-replacement');assert.equal(transfer.phase,'travel');
 assert.equal(work.technicianFacing,1);assert.deepEqual(work.technician,{x:414,y:207,heading:1});
 for(const hour of [5,12,20]){
  const stopped=actor('interrupted-portable',hour);
  assert.equal(stopped.kind,'portable-cleaning');assert.equal(stopped.phase,'stranded');
  assert.equal(stopped.visible,true);assert.equal(stopped.working,false);assert.equal(stopped.moving,false);
 }
});
test('visit explanations show saved plans, actual return and escaped job text',()=>{
 const result=fixtures.supplies.value,row=structuredClone(result.records.Greedy[5]);
 row.field_operations.state.executive.visits[0].reason='<script>unsafe</script>';
 const html=renderFieldOperations(result,{hour:6,row},fixtures.supplies.economics.controllers.Greedy[6]);
 assert.match(html,/Shared crew visits/);assert.match(html,/Returned H5.5/);
 assert.match(html,/3.5 crew-hours/);assert.match(html,/&lt;script&gt;/);
 assert.doesNotMatch(html,/<script>/);
});
