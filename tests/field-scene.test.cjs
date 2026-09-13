const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const {gunzipSync}=require('node:zlib');
const {FIELD_ROUTES,fieldPoint,fieldVisualState}=require('../assets/field-scene.js');
const fixture=JSON.parse(gunzipSync(readFileSync('tests/fixtures/field-motion.json.gz'))).props.value;
const visual=(hour,fraction=0,playing=false,result=fixture,controller='Greedy')=>fieldVisualState(result,controller,{hour,fraction,playing});
const actor=(v,asset)=>v.actors.find(a=>a.asset===asset);
const position=a=>[a.x,a.y];

test('initial assets stay docked and begin to travel only on playback',()=>{
  assert.equal(actor(visual(0),'cleaner').phase,'docked');
  const start=actor(visual(0,0,true),'cleaner'),half=actor(visual(0,.5,true),'cleaner');
  assert.equal(start.phase,'travel');assert.deepEqual(position(start),FIELD_ROUTES.cleaner[0]);
  assert.notDeepEqual(position(start),position(half));
  assert.deepEqual(position(actor(visual(1),'cleaner')),FIELD_ROUTES.brush[0]);
});
test('multi-hour phases keep their progress when seeking or pausing at a boundary',()=>{
  const van=actor(visual(15),'human');assert.equal(van.phase,'travel');assert.equal(van.progress,.5);
  assert.deepEqual(position(van),position(actor(visual(15,0,true),'human')));
  const cleaner=actor(visual(2),'cleaner');assert.equal(cleaner.progress,.5);
  assert.deepEqual(position(cleaner),position(actor(visual(2,0,true),'cleaner')));
  const end=actor(visual(17),'human');assert.equal(end.working,true);assert.equal(end.walking,false);
  assert.equal(actor(visual(18),'human').phase,'awaiting verification');
});
test('inspection patrol and return follow the recorded work chain',()=>{
  assert.equal(actor(visual(12,.4,true),'rover').phase,'travel');
  const scan=actor(visual(13,.4,true),'rover');assert.equal(scan.phase,'perform');assert.equal(scan.working,true);
  assert.equal(actor(visual(14),'rover').phase,'verify');
  assert.equal(actor(visual(15,.5,true),'rover').phase,'return');
  assert.deepEqual(position(actor(visual(16),'rover')),FIELD_ROUTES.rover[0]);
});
test('current movement cannot use future work outcomes or simulator truth',()=>{
  const changed=structuredClone(fixture),before=JSON.stringify(fixture);
  changed.records.Greedy[13].field_operations.state.orders=[];
  changed.records.Greedy[13].field_operations.retrospective_effects=[{success:false}];
  changed.retrospective_truth={anything:'changed'};
  for(let i=14;i<changed.records.Greedy.length;i++)changed.records.Greedy[i]={};
  assert.deepEqual(visual(13,.7,true,changed),visual(13,.7,true));
  assert.equal(JSON.stringify(fixture),before);
});
test('blocked work does not move; failed missions remain at the worksite',()=>{
  const r=structuredClone(fixture),row=r.records.Greedy[0];
  const order=row.decision.field_operations.orders[0];
  order.status='blocked';order.phase='queued';
  let a=actor(visual(0,.5,true,r),'cleaner');assert.equal(a.moving,false);assert.deepEqual(position(a),FIELD_ROUTES.cleaner[0]);
  order.status='failed';order.phase='stranded';
  a=actor(visual(0,.9,true,r),'cleaner');assert.equal(a.failed,true);assert.equal(a.working,false);
  assert.deepEqual(position(a),FIELD_ROUTES.brush.at(-1));
  row.field_operations.state=structuredClone(row.decision.field_operations);
  assert.deepEqual(position(actor(visual(1,0,false,r),'cleaner')),position(a));
});
test('fixed reset actuator does not move or imply a successful repair',()=>{
  const r=structuredClone(fixture),state=r.records.Greedy[0].decision.field_operations;
  state.orders.push({id:'RESET',kind:'reset',status:'active',phase:'perform',remaining:1});
  let a=actor(visual(0,.5,true,r),'reset');assert.equal(a.working,true);assert.equal(a.moving,false);
  assert.deepEqual(position(a),[622,194]);
  state.orders.at(-1).status='failed';a=actor(visual(0,.5,true,r),'reset');
  assert.equal(a.phase,'failed');assert.equal(a.working,false);
});
test('controller selection uses separate work history; legacy scenes stay empty',()=>{
  const r=structuredClone(fixture);r.records['MPC · methane'][0].decision.field_operations.orders=[];
  assert.equal(actor(visual(0,.5,true,r,'MPC · methane'),'cleaner').phase,'docked');
  assert.equal(actor(visual(0,.5,true,r,'Greedy'),'cleaner').phase,'travel');
  r.config.field_operations.enabled=false;assert.equal(visual(0,0,false,r).enabled,false);
  delete r.config.field_operations;assert.deepEqual(visual(0,0,false,r).actors,[]);
});
test('path interpolation clamps endpoints and follows corners by distance',()=>{
  const path=[[0,0],[3,0],[3,4]];
  assert.deepEqual(position(fieldPoint(path,-1)),[0,0]);
  assert.deepEqual(position(fieldPoint(path,3/7)),[3,0]);
  assert.deepEqual(position(fieldPoint(path,5/7)),[3,2]);
  assert.deepEqual(position(fieldPoint(path,2)),[3,4]);
});
