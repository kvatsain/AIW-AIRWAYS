import assert from 'node:assert/strict';
import fs from 'node:fs';
import {camera3D,windFlowVector,airfield3DSVG} from '../dist/airfield-3d.js';
const load=name=>JSON.parse(fs.readFileSync(new URL(`../dist/data/${name}.json`,import.meta.url)));
const geo=load('fra-airfield'),context=load('fra-context');
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-9);
for(const [from,expected] of [[0,[0,1]],[90,[-1,0]],[180,[0,-1]],[270,[1,0]]]){
 const flow=windFlowVector(from);flow.forEach((v,i)=>near(v,expected[i]));
}
const cam=camera3D(0,48),ground=cam.point([350,285]),roof=cam.point([350,285],20);
near(ground[0],roof[0]);assert.ok(roof[1]<ground[1],'Elevation moves the roof above its footprint');
assert.ok(cam.point([350,200])[1]<ground[1],'North projects upward with zero yaw');
assert.ok(cam.point([400,285])[0]>ground[0],'East projects right with zero yaw');
const row={p07:.9,windSpeed:15,windDirection:0,windGust:15};
const scene=airfield3DSVG(geo,row,context);
assert.ok(scene.includes('Runway 18 exceeds challenge wind limits.'));
assert.ok(scene.includes('illustrative building heights'));
assert.equal((scene.match(/data-scene-runway=/g)||[]).length,4);
assert.ok(!/NaN|Infinity/.test(scene),'All projected geometry stays finite');
assert.ok(!airfield3DSVG(geo,{...row,windSpeed:14.99},context).includes('Runway 18 exceeds challenge wind limits.'));
assert.ok(!airfield3DSVG(geo,{...row,windSpeed:0,windGust:0},context).includes('class="wind-streams"'),'Calm wind has no misleading direction animation');
assert.ok(!airfield3DSVG(geo,row,context,{wind:false}).includes('class="wind-streams"'));
assert.ok(!airfield3DSVG(geo,{...row,windSpeed:null},context).includes('class="wind-streams"'));
for(const yaw of [-16,44,164,269])for(const elevation of [35,48,65]){
 const rendered=airfield3DSVG(geo,row,context,{yaw,elevation});assert.ok(!/NaN|Infinity/.test(rendered));
}
assert.ok(airfield3DSVG(geo,{...row,p07:.1},null).includes('Forecast direction 25'),'Scene works without optional context');
console.log('Passed: meteorological FROM-to-flow direction, 3D projection axes/elevation, all runway IDs, limit edge, calm/missing wind, layer toggle, supported camera angles, context fallback.');
