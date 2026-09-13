const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),z=require('node:zlib');
const {fieldVisualState,fieldSupportGeometry}=require('../assets/field-scene.js');
const {renderFieldOperations}=require('../assets/field-operations.js');
const cases=JSON.parse(z.gunzipSync(fs.readFileSync('tests/fixtures/routine-services.json.gz')));

test('routine crew animation follows recorded tasks without claiming repair',()=>{
 const r=cases.routine.value;
 let work,travel;
 for(let h=0;h<r.records.Greedy.length;h++)for(const f of [.1,.4,.7,.9]){
  const a=fieldVisualState(r,'Greedy',{hour:h,fraction:f,playing:true}).actors.find(a=>a.asset==='human');
  if(a?.kind==='routine-service'&&a.phase==='perform')work=a;
  if(a?.kind==='routine-service'&&a.phase==='travel')travel=a;
 }
 assert.ok(work?.working);assert.ok(work.technician);assert.ok(travel?.moving);
 assert.notDeepEqual([work.x,work.y],[travel.x,travel.y]);
});
test('fixed hardware routine work uses its plant-side technician route',()=>{
 const order={kind:'routine-service',target:'fixed_reader'};
 const a=fieldSupportGeometry(order,{phase:'perform',from_point:'electrolyser',to_point:'electrolyser'},.1);
 const b=fieldSupportGeometry(order,{phase:'perform',from_point:'electrolyser',to_point:'electrolyser'},.8);
 assert.ok(a.walking);assert.equal(b.walking,false);assert.notDeepEqual(a.technician,b.technician);
});
test('standby state and inspector use the saved grant and overdue clocks',()=>{
 const r=cases['night-reserve'].value,rows=r.records.Greedy;
 const index=rows.findIndex(r=>r.field_operations.standby.unserved_kwh>0);
 assert.ok(index>=0);
 const v=fieldVisualState(r,'Greedy',{hour:index+1,fraction:0,playing:false});
 assert.equal(v.standby.control_available,false);
 const html=renderFieldOperations(r,{hour:index+1,row:rows[index]},null,v);
 assert.match(html,/Dock controls/);assert.match(html,/unserved/);assert.match(html,/Scheduled routine work/);
 assert.match(html,/no quantified avoided-failure benefit/);
});

test('routine dock visits park clear of the CO2 vessel and the dock controls',()=>{
 const a=fieldSupportGeometry({kind:'routine-service',target:'dock'},{phase:'perform',from_point:'dock',to_point:'dock'},.6);
 assert.equal(a.x,715);assert.equal(a.y,528);assert.ok(a.x+48<788);assert.ok(a.y-42>471);
});
