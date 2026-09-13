const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),z=require('node:zlib');
const {fieldVisualState}=require('../assets/field-scene.js');
const {renderFieldOperations}=require('../assets/field-operations.js');
const fixtures=JSON.parse(z.gunzipSync(fs.readFileSync('tests/fixtures/hardware-services.json.gz')));
const state=(name,h,f=0)=>fieldVisualState(fixtures[name].value,'Greedy',{hour:h,fraction:f,playing:f>0});
const actor=(name,asset,h,f=0)=>state(name,h,f).actors.find(a=>a.asset===asset);

test('remote tests hold their reported position and only guided return moves',()=>{
 const stopped=actor('control-hold','cleaner',2),release=actor('control-hold','cleaner',2,.125);
 assert.equal(release.kind,'remote-release');assert.equal(release.testing,true);
 assert.equal(release.working,false);assert.equal(release.moving,false);
 assert.equal(release.x,stopped.x);assert.equal(release.y,stopped.y);
 const travelling=actor('control-hold','cleaner',5,.25),later=actor('control-hold','cleaner',5,.4);
 assert.equal(travelling.kind,'guided-return');assert.equal(travelling.moving,true);assert.equal(travelling.working,false);
 assert.notEqual(travelling.x,later.x);
 assert.deepEqual([actor('control-hold','cleaner',6).x,actor('control-hold','cleaner',6).y],[705,471]);
});
test('portable packing and compatible module work reuse the operator and tool without treatment',()=>{
 const pack=actor('pump-power-loss','human',4,.25),work=actor('pump-power-loss','human',13,.5);
 assert.equal(pack.kind,'pack-return');assert.equal(pack.packing,true);assert.equal(pack.wet,false);
 assert.deepEqual(pack.toolPosition,{x:358,y:255});
 assert.equal(work.kind,'hardware-replacement');assert.equal(work.packing,true);assert.equal(work.working,true);
 assert.ok(work.toolPosition.x<1280&&work.toolPosition.y<550);
 const interrupted=actor('interrupted-return','cleaner',8);
 assert.equal(interrupted.phase,'stranded');assert.equal(interrupted.moving,false);
 assert.ok(interrupted.x>263&&interrupted.x<705);assert.equal(interrupted.y,521);
});
test('recovery explanations escape text, retain procedure outcomes and do not inspect private fault truth',()=>{
 const input=structuredClone(fixtures['drive-power-loss']);
 const row=input.value.records.Greedy.at(-1);
 row.field_operations.state.support.equipment.incidents[0].reason='<script>untrusted</script>';
 const html=renderFieldOperations(input.value,{hour:36,row},input.economics.controllers.Greedy.at(-1));
 assert.match(html,/Service hardware recovery/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
 assert.match(html,/remote-release/);assert.match(html,/awaiting verification/);
 assert.doesNotMatch(html,/private_state|drive-power-loss/);
 const before=fieldVisualState(input.value,'Greedy',{hour:2,fraction:.125,playing:true});
 input.value.config.faults={cleaner_service_fault:'none'};input.value.retrospective_truth_by_controller={};
 assert.deepEqual(fieldVisualState(input.value,'Greedy',{hour:2,fraction:.125,playing:true}),before);
});
