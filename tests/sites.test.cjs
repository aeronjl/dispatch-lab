const {test}=require('node:test');
const assert=require('node:assert/strict');
const {sitesEscape,sitesAccept}=require('../assets/sites.js');
test('site responses cannot replace a later selection or closed workspace',()=>{
 assert.equal(sitesAccept(true,4,'4',{key:'4'}),true);
 assert.equal(sitesAccept(false,4,'4',{key:'4'}),false);
 assert.equal(sitesAccept(true,5,'4',{key:'4'}),false);
 assert.equal(sitesAccept(true,4,'4',{key:'3'}),false);
});
test('source and place text is escaped',()=>{
 assert.equal(sitesEscape('<img onerror="x">'), '&lt;img onerror=&quot;x&quot;&gt;');
});
