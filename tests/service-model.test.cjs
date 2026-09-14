const test=require('node:test'),assert=require('node:assert/strict');
const {serviceLearningArt}=require('../assets/model.js');
const topics=['cleaning','inspection','recovery','charging','logistics','service_costs','service_uncertainty'];
for(const topic of topics)test(topic+' draws recorded quantities without executable input',()=>{
 const data={inputs:{loose:.12,coverage:.5},patches:[{start_m2:0,end_m2:100,removable:.08}],metrics:[{label:'Ending kits',value:2}],observation:{quality:'<unsafe>',value:null},steps:[{hour:2,stock:2,outcome:'<unsafe>'}],posterior:{persistent_factors:[1],posterior_weights:[1],status:'observed'}};
 const s=serviceLearningArt(topic,data);assert.match(s,/<svg/);assert.match(s,/role="img"/);assert.ok(!s.includes('<unsafe>'));assert.ok(!s.includes('NaN'));
});
test('service art follows changed result',()=>{
 const a={inputs:{loose:.12,coverage:.2},patches:[],metrics:[]},b=structuredClone(a);b.inputs.coverage=.8;
 assert.notEqual(serviceLearningArt('cleaning',a),serviceLearningArt('cleaning',b));
 assert.equal(serviceLearningArt('battery',a),null);
});

const {modelLearningChart}=require('../assets/model.js');
test('missing readings are not rendered as zero and categorical channels have correct labels',()=>{
 const svg=modelLearningChart([{label:'Contact',points:[null,null,null]}],'V','inspection');assert.match(svg,/No eligible numerical readings/);assert.ok(!svg.includes('<path'));assert.match(svg,/Signal/);assert.match(svg,/Span/);assert.ok(!svg.includes('First interval'));
});
