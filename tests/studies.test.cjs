const test=require('node:test');const assert=require('node:assert/strict');
const {studyEscape,studyAccept}=require('../assets/studies.js');
test('study responses require the active generation and open workspace',()=>{
 assert.equal(studyAccept(true,3,'3',{key:'3'}),true);
 assert.equal(studyAccept(true,4,'3',{key:'3'}),false);
 assert.equal(studyAccept(false,3,'3',{key:'3'}),false);
 assert.equal(studyAccept(true,3,'3',{key:'4'}),false);
});
test('study labels and source descriptions remain text',()=>{assert.equal(studyEscape('<img src=x>'), '&lt;img src=x&gt;');});
