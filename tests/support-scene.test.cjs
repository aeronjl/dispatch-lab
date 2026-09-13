const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),z=require('node:zlib');
const {fieldVisualState,fieldSupportGeometry,FIELD_ROUTES}=require('../assets/field-scene.js');
const r=JSON.parse(z.gunzipSync(fs.readFileSync('tests/fixtures/support-services.json.gz'))).retrieval.value;
const sample=(h,f=0)=>fieldVisualState(r,'Greedy',{hour:h,fraction:f,playing:f>0});
const actor=(h,f,k)=>sample(h,f).actors.find(a=>a.asset===k);

test('recovery uses reported location, a loading pause and the same robot on the carrier',()=>{
  const failed=actor(2,0,'cleaner'),pack=actor(4,.25,'human');
  assert.equal(failed.phase,'stranded');assert.equal(pack.phase,'prepare');
  assert.equal(pack.technician.x,failed.x+24);
  const loading=actor(4,.55,'human'),early=actor(4,.52,'human');
  assert.equal(loading.moving,false);assert.deepEqual([loading.x,loading.y],[early.x,early.y]);
  const van=actor(4,.75,'human'),robot=actor(4,.75,'cleaner');
  assert.equal(van.towing,true);assert.equal(robot.phase,'retrieval');
  assert.equal(robot.x,van.x-van.heading*94);assert.equal(robot.y,van.y-5);
  assert.equal(robot.working,false);
});
test('drive test stays at the dock without brushing and later work leaves the dock',()=>{
  const test=actor(6,.1,'cleaner');
  assert.equal(test.kind,'self-test');assert.equal(test.working,false);
  assert.deepEqual([test.x,test.y],FIELD_ROUTES.cleaner[0]);
  const next=actor(7,.2,'cleaner');
  assert.equal(next.phase,'travel');assert.notEqual(next.x,test.x);
  assert.equal(actor(7,.2,'human').visible,false);
});
test('a later-started queued job owns the pose after interruption, not a newer-created completed test',()=>{
  const second=actor(8,0,'cleaner');
  assert.equal(second.order,'SVC-0003');assert.equal(second.phase,'stranded');
  assert.equal(second.working,false);assert.notDeepEqual([second.x,second.y],FIELD_ROUTES.cleaner[0]);
});
test('loading-to-transport interpolation is continuous at the phase boundary',()=>{
  const order=r.records.Greedy[4].decision.field_operations.orders.find(o=>o.kind==='retrieve');
  const span={from_point:'recovery/'+order.origin_order,to_point:'dock',phase:'return'};
  const left=fieldSupportGeometry(order,span,.25-1e-8),right=fieldSupportGeometry(order,span,.25);
  assert.ok(Math.abs(left.passenger.x-right.passenger.x)<.001);
  assert.ok(Math.abs(left.passenger.y-right.passenger.y)<.001);
});
