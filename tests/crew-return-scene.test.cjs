const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),z=require('node:zlib');
const {fieldVisualState}=require('../assets/field-scene.js');
const {renderFieldOperations}=require('../assets/field-operations.js');
const result=JSON.parse(z.gunzipSync(fs.readFileSync('tests/fixtures/crew-return.json.gz')));
const actor=(hour,fraction=0)=>fieldVisualState(result,'Greedy',{hour,fraction,playing:fraction>0}).actors.find(a=>a.asset==='human');

test('interrupted crew packs at the recorded position then travels home',()=>{
 const stopped=actor(4),packing=actor(4,.1),a=actor(4,.3),b=actor(4,.8);
 assert.equal(stopped.phase,'stranded');assert.equal(packing.kind,'crew-return');
 assert.equal(packing.phase,'prepare');assert.equal(packing.x,stopped.x);assert.equal(packing.y,stopped.y);
 assert.equal(a.phase,'return');assert.equal(a.moving,true);assert.equal(a.working,false);
 assert.notDeepEqual([a.x,a.y],[b.x,b.y]);
 const arrival=actor(5,.4);assert.equal(arrival.kind,'crew-return');
 assert.equal(arrival.phase,'perform');assert.equal(arrival.working,false);assert.equal(arrival.walking,false);
 assert.equal(actor(6).visible,false);
});
test('rendering a return leaves numerical records intact and keeps scope in the inspector',()=>{
 const before=JSON.stringify(result),row=result.records.Greedy[4];
 const html=renderFieldOperations(result,{hour:5,row},null);
 assert.match(html,/Returning interrupted crews/);assert.match(html,/vehicle fuel/);
 for(let i=0;i<20;i++)actor(4,i/20);
 assert.equal(JSON.stringify(result),before);
});
test('a blocked arrival uses the latest reported vehicle location, not the old failed job',()=>{
 const copy=structuredClone(result),state=copy.records.Greedy[4].field_operations.state;
 const order=state.orders.findLast(q=>q.kind==='crew-return');
 order.status='failed';order.execution_status='blocked';order.phase='perform';
 const report=state.executive.orders.find(q=>q.order_id===order.id);
 Object.assign(report,{status:'blocked',phase:'perform',from_point:'site-gate',to_point:'site-gate',progress:0});
 const a=fieldVisualState(copy,'Greedy',{hour:5,fraction:0,playing:false}).actors.find(a=>a.asset==='human');
 assert.equal(a.order,order.id);assert.equal(a.x,1318);assert.equal(a.y,379);
 assert.equal(a.moving,false);assert.equal(a.working,false);assert.equal(a.walking,false);
});
