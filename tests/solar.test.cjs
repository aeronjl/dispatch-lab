const test=require('node:test');
const assert=require('node:assert/strict');
const {solarPanelGeometry}=require('../assets/solar.js');
test('capacity changes schematic rows; tilt and orientation change panel geometry',()=>{
 const base={capacity_kw:333,tilt:30,azimuth:0};
 const a=solarPanelGeometry(base);
 assert.equal(a.rows,3);
 assert.equal(solarPanelGeometry({...base,capacity_kw:600}).rows,5);
 assert.equal(solarPanelGeometry({...base,capacity_kw:0}).tiles.length,0);
 assert.notDeepEqual(solarPanelGeometry({...base,tilt:70}).tiles,a.tiles);
 assert.notDeepEqual(solarPanelGeometry({...base,azimuth:90}).tiles,a.tiles);
});
test('all supported orientation extremes produce finite bounded geometry',()=>{
 for(const tilt of [0,30,90])for(const azimuth of [-180,-90,0,90,180]){
  const g=solarPanelGeometry({capacity_kw:1500,tilt,azimuth});
  for(const tile of g.tiles)for(const point of tile.corners)for(const n of point)assert.ok(Number.isFinite(n)&&Math.abs(n)<400);
 }
});
