const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),z=require('node:zlib');
const {fieldVisualState}=require('../assets/field-scene.js');
const fixtures=JSON.parse(z.gunzipSync(fs.readFileSync('tests/fixtures/portable-services.json.gz')));
const sample=(h,f,method='wet')=>fieldVisualState(fixtures[method].value,'Greedy',{hour:h,fraction:f,playing:f>0}).actors.find(a=>a.asset==='human');
test('portable tool follows the crew and appears only at the worksite',()=>{
  assert.equal(sample(2,.5).portableWork,false);
  assert.equal(sample(3,.25).phase,'prepare');assert.equal(sample(3,.25).toolTarget,null);
  const first=sample(3,.75),later=sample(4,.5);
  assert.equal(first.portableWork,true);assert.equal(first.wet,true);
  assert.notDeepEqual(first.toolTarget,later.toolTarget);
  assert.equal(sample(5,.5).portableWork,false);
});
test('dry method remains dry and interrupted work cannot animate active treatment',()=>{
  assert.equal(sample(3,.75,'dry').wet,false);
  const failed=sample(4,.5,'interrupted');
  assert.equal(failed.phase,'stranded');assert.equal(failed.working,false);assert.equal(failed.moving,false);
});
