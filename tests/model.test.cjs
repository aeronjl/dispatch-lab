const {test}=require('node:test');const assert=require('node:assert/strict');
const {modelEscape,modelNumber,modelRows}=require('../assets/model.js');
test('documentation escapes untrusted labels and source values',()=>{assert.equal(modelEscape('<script>"'), '&lt;script&gt;&quot;');assert.equal(modelNumber(null),'Undefined');});
test('recorded quantities render as readable paths without performing physics',()=>{assert.deepEqual(modelRows({observed:{power:42}}),[['observed / power','42']]);});
