const {test}=require('node:test');const assert=require('node:assert/strict');
const {serviceAlternativeKey,serviceAlternativeRows}=require('../assets/service-alternatives.js');
test('service response selection includes the input generation and unambiguous identifiers',()=>{
 const key=serviceAlternativeKey('a|b','c',3,'d');
 assert.notEqual(key,serviceAlternativeKey('a','b|c',3,'d'));
 assert.notEqual(key,serviceAlternativeKey('a|b','c',3,'next'));
 assert.deepEqual(JSON.parse(key),['a|b','c',3,'d']);
});
test('service table renders Python costs without replacing an unavailable value by zero',()=>{
 const values=serviceAlternativeRows({baseline:{summary:{prediction:{methane_kg:12},total_decision_eur:51}},alternative:{summary:{prediction:null,total_decision_eur:null}}});
 assert.deepEqual(values.find(r=>r[0]==='Methane'),['Methane','kg',12,undefined]);
 assert.deepEqual(values.find(r=>r[0]==='Total decision cost'),['Total decision cost','€',51,null]);
});
test('investigation comparison labels weighted outputs and keeps incomplete arms unavailable',()=>{
 const {investigationAlternativeRows}=require('../assets/service-alternatives.js');
 const rows=investigationAlternativeRows({baseline:{summary:{expected:{methane_kg:8.5,total_decision_eur:15,ending:{battery_kwh:20}}}},alternative:{summary:{expected:null}}});
 assert.deepEqual(rows.find(r=>r[0]==='Expected methane'),['Expected methane','kg',8.5,undefined]);
 assert.deepEqual(rows.find(r=>r[0]==='Expected total decision cost'),['Expected total decision cost','€',15,undefined]);
});
