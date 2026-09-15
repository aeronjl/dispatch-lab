const {test}=require('node:test');const assert=require('node:assert/strict');
const {controlSelectionKey,controlValue,controlSegments}=require('../assets/control-view.js');
test('control responses are bound to run, policy, decision and generation',()=>{
 const original=controlSelectionKey('r','p',12,1);
 for(const args of [['x','p',12,1],['r','x',12,1],['r','p',13,1],['r','p',12,2]])assert.notEqual(original,controlSelectionKey(...args));
});
test('missing state stays missing and lines never bridge absent data',()=>{
 assert.equal(controlValue(null,'battery'),null);
 assert.equal(controlValue({state:{}},'battery'),undefined);
 assert.equal(controlValue({state:{battery_kwh:0}},'battery'),0);
 assert.equal(controlValue({pv_kw:100},'solar'),100);
 assert.equal(controlSegments([10,20,null,40,50],500,100).length,2);
 assert.deepEqual(controlSegments([null,undefined]),[]);
});
test('subzero reactor temperatures are plotted against the disclosed range',()=>{
 assert.deepEqual(controlSegments([-10,0,10],300,118,10,-10),['50,112 150,62 250,12']);
});
