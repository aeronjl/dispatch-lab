const {test}=require('node:test');const assert=require('node:assert/strict');
const {lifecycleArt,lifecycleDesignForm,lifecyclePeriodView}=require('../assets/lifecycle.js');
test('lifecycle illustrations are recorded renderers and handle missing values',()=>{
 for(const topic of ['deployment','condition','hardware','maintenance']){
  const svg=lifecycleArt(topic,{});assert.match(svg,/role="img"/);assert.doesNotMatch(svg,/NaN|undefined/);
 }
 assert.equal(lifecycleArt('battery',{}),null);
});
test('restricted machinery cannot render as an executable capability',()=>{
 const data={assessment:{family:'<script>',status:'evidence restricted'},prerequisites:['<reference>']};
 const a=lifecycleArt('hardware',data);assert.match(a,/NO EXECUTABLE MECHANISM/);assert.match(a,/&lt;reference&gt;/);assert.doesNotMatch(a,/<script>/);
});
test('departed commissioning machinery leaves the illustration',()=>{
 const a=lifecycleArt('deployment',{steps:[{package:{status:'departed',accepted_at:3},capacity_kw:500}]});
 assert.match(a,/EQUIPMENT DEPARTED/);assert.doesNotMatch(a,/class="lc-machine"/);
});
test('lifecycle editors start hidden and period reports preserve scope',()=>{
 assert.match(lifecycleDesignForm({}),/lc-design" hidden/);assert.equal(lifecyclePeriodView(null),'');
 assert.match(lifecyclePeriodView({cash_eur:100,packages:{'<script>':{status:'waiting'}}}),/&lt;script&gt;/);
});
