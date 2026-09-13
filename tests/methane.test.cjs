const test=require('node:test');
const assert=require('node:assert/strict');
const {methaneSelectionKey,methaneFrame}=require('../assets/methane.js');
test('response key changes across run/controller/decision/alternative',()=>{
 const key=methaneSelectionKey('run','mpc',3,'battery');
 for(const args of [['next','mpc',3,'battery'],['run','greedy',3,'battery'],['run','mpc',4,'battery'],['run','mpc',3,'co2']])assert.notEqual(methaneSelectionKey(...args),key);
});
test('playhead exposes only the completed row and its original decision',()=>{
 const result={records:{MPC:[{decision:{id:0}},{decision:{id:1}}]},frames:{MPC:[{methane_kg:0},{methane_kg:3},{methane_kg:6}]}};
 assert.equal(methaneFrame(result,0,'MPC').row,null);
 assert.equal(methaneFrame(result,0,'MPC').decision.id,0);
 assert.equal(methaneFrame(result,1,'MPC').decision.id,0);
 assert.equal(methaneFrame(result,1,'MPC').totals.methane_kg,3);
 assert.equal(methaneFrame(result,100,'MPC').hour,2);
});
test('returning to the same selection still rejects the earlier request generation',()=>{
 assert.notEqual(methaneSelectionKey('run','mpc',3,'battery','session-1'),methaneSelectionKey('run','mpc',3,'battery','session-2'));
});
