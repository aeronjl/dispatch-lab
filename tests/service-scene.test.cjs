const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const {gunzipSync}=require('node:zlib');
const {fieldVisualState,fieldPoint,fieldSectionBrush,FIELD_ROUTES}=require('../assets/field-scene.js');
const data=JSON.parse(gunzipSync(readFileSync('tests/fixtures/fractional-services.json.gz')));
const sample=(h,f=0,mode='mobile',result=data[mode].value)=>fieldVisualState(result,'Greedy',{hour:h,fraction:f,playing:f>0});
const get=(v,key)=>v.actors.find(a=>a.asset===key);

test('fractional schedules cross multiple phases within an hourly plant interval',()=>{
  assert.equal(get(sample(0,.25),'cleaner').phase,'travel');
  assert.equal(get(sample(0,.75),'cleaner').phase,'perform');
  assert.equal(get(sample(2,.6),'cleaner').phase,'verify');
  assert.equal(get(sample(2,.9),'cleaner').phase,'return');
  assert.equal(get(sample(3,.5),'cleaner').phase,'docked');
  const pose=get(sample(3,.5),'cleaner');
  assert.deepEqual([pose.x,pose.y],FIELD_ROUTES.cleaner[0]);
});
test('fixed sensing replaces the rover on screen and retains a selectable actor',()=>{
  assert.equal(get(sample(0,0,'fixed'),'rover'),undefined);
  assert.equal(get(sample(0,0,'fixed'),'fixed_reader').phase,'docked');
  assert.equal(get(sample(4,.5,'fixed'),'fixed_reader').phase,'perform');
  assert.equal(get(sample(4,.5,'fixed'),'fixed_reader').moving,false);
});
test('fractional drawing cannot promote later repair outcomes into present movement',()=>{
  const altered=structuredClone(data.mobile.value);
  const reference=sample(2,.6);
  altered.records.Greedy[2].field_operations.state={orders:[]};
  altered.records.Greedy[2].field_operations.mission_events=[];
  altered.retrospective_truth_by_controller={Greedy:[{capacity_kw:0}]};
  for(let h=3;h<altered.records.Greedy.length;h++)altered.records.Greedy[h]={};
  assert.deepEqual(sample(2,.6,'mobile',altered),reference);
});
test('task-specific human work has a return journey and leaves the worksite',()=>{
  const rows=data.fixed.value.records.Greedy;
  const mission=rows.flatMap(r=>r.decision.field_operations.planned_missions).find(p=>p.order.action==='module-replacement');
  assert.ok(mission);
  const returning=mission.timeline.find(t=>t.phase==='return');
  const h=Math.floor(returning.start),f=returning.start-h+.1;
  assert.equal(get(sample(h,f,'fixed'),'human').phase,'return');
  const after=Math.ceil(returning.end);
  // A later independent visit may exist; the completed one must not remain at the panel.
  const finished=get(sample(after,0,'fixed'),'human');
  if(finished.order===mission.order.order_id)assert.equal(finished.visible,false);
});

test('interrupted travel retains its recorded location rather than jumping to the worksite',()=>{
  const r=structuredClone(data.mobile.value),s=r.records.Greedy[0].decision.field_operations;
  const q=s.orders.find(o=>o.kind==='cleaning'),m=s.executive.orders.find(o=>o.order_id===q.id);
  q.status='failed';m.status='stranded';m.phase='travel';m.progress=.2;
  const a=sample(0,.8,'mobile',r),b=sample(0,.9,'mobile',r);
  const x=get(a,'cleaner'),y=get(b,'cleaner');
  assert.equal(x.phase,'stranded');assert.equal(x.moving,false);
  assert.deepEqual([x.x,x.y],[y.x,y.y]);
  assert.notDeepEqual([x.x,x.y],FIELD_ROUTES.cleaner.at(-1));
});

test('interrupted section work preserves the recorded partial sweep position',()=>{
  const r=structuredClone(data.mobile.value),s=r.records.Greedy[0].decision.field_operations;
  const q=s.orders.find(o=>o.kind==='cleaning'),m=s.executive.orders.find(o=>o.order_id===q.id);
  q.section='PV-03';q.status='failed';m.status='stranded';m.phase='perform';m.progress=.3;
  const x=get(sample(0,.8,'mobile',r),'cleaner');
  assert.equal(x.phase,'stranded');assert.equal(x.working,false);
  const expected=fieldPoint(fieldSectionBrush('PV-03'),.3);
  assert.deepEqual([x.x,x.y],[expected.x,expected.y]);
  assert.notDeepEqual(fieldSectionBrush('PV-01'),fieldSectionBrush('PV-03'));
});
