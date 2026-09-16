const {test}=require('node:test');const assert=require('node:assert/strict');
const {requirementsEscape,requirementsCurrent}=require('../assets/requirements.js');
test('requirements markup escapes authored names and discarded requests cannot render',()=>{
 assert.equal(requirementsEscape('<img onerror="x">'), '&lt;img onerror=&quot;x&quot;&gt;');
 assert.equal(requirementsCurrent(true,3,2),false);assert.equal(requirementsCurrent(false,2,2),false);assert.equal(requirementsCurrent(true,2,2),true);
});
