const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {createHash}=require('node:crypto');
test('full-screen shell preserves every original plant SVG element and label',()=>{
  const source=fs.readFileSync('assets/methane.html','utf8');
  const svg=source.match(/<svg class="m-plant plant-drawing"[\s\S]*?<\/svg>/)[0];
  const before=fs.readFileSync('tests/fixtures/plant-artwork.sha256','utf8').trim();
  assert.equal(createHash('sha256').update(svg).digest('hex'),before);
});
