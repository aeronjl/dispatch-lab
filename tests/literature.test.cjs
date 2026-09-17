const {test}=require('node:test');const assert=require('node:assert/strict');
global.equipmentEscape=require('../assets/equipment.js').equipmentEscape;
const {literaturePlot}=require('../assets/literature.js');
test('reference graph uses recorded predictions, explicit observation distinction and escaped units',()=>{
 const v={unit:'<unsafe>',x_label:'Power & load',query:{x:2},curve:[{x:1,predicted:3,low:2.5,high:3.5},{x:3,predicted:4,low:3.5,high:4.5}],rows:[{x:2,observed:3.8,split:'evaluation'}]};const svg=literaturePlot(v);assert(svg.includes('Power &amp; load'));assert(svg.includes('&lt;unsafe&gt;'));assert(!svg.includes('<unsafe>'));assert(svg.includes('Exact values in the points table'));assert(svg.includes('3.8000'));assert(svg.includes('stroke-dasharray'));assert(!svg.includes('NaN'));
});
