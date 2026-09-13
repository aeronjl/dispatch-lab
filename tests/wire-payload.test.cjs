const test=require('node:test');
const assert=require('node:assert/strict');
const {decodeMethanePayload}=require('../assets/methane.js');
test('scalar live payload and legacy offline objects decode without changing data',()=>{
  const original={run_id:'saved',records:{Greedy:[{value:0,missing:null,label:'CO₂'}]}};
  const decoded=decodeMethanePayload(JSON.stringify(original));
  assert.deepEqual(decoded,original);
  decoded.records.Greedy[0].value=1;
  assert.equal(original.records.Greedy[0].value,0);
  assert.equal(decodeMethanePayload(original),original);
  assert.throws(()=>decodeMethanePayload('{broken'),SyntaxError);
});
