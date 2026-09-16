const {test}=require('node:test');const assert=require('node:assert/strict');
const {equipmentEscape,equipmentCurrent}=require('../assets/equipment.js');
test('evidence text cannot introduce markup',()=>assert.equal(equipmentEscape('<img src="x">&'), '&lt;img src=&quot;x&quot;&gt;&amp;'));
test('equipment responses must belong to the current open context',()=>{assert.equal(equipmentCurrent(true,3,3),true);assert.equal(equipmentCurrent(false,3,3),false);assert.equal(equipmentCurrent(true,4,3),false);});
