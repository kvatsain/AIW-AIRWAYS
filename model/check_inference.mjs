import assert from 'node:assert/strict';
import fs from 'node:fs';
import { inferRow, featuresFor, predictForecast, windComponents } from '../dist/inference.js';
const model=JSON.parse(fs.readFileSync(new URL('../dist/data/model.json',import.meta.url),'utf8'));
const sample=JSON.parse(fs.readFileSync(new URL('./parity_fixture.json',import.meta.url),'utf8'));
for(const item of sample){
  const actual=featuresFor(item.row,item.observation,item.initialOD);
  actual.forEach((v,i)=>assert.ok(Math.abs(v-item.features[i])<1e-10,`Feature ${i} differs`));
  const result=inferRow(actual,item.horizon,model);
  assert.ok(Math.abs(result.p07-item.p07)<1e-10);
  assert.ok(Math.abs(result.pClosed18-item.pClosed18)<1e-10);
}
const obs={time:'2026-10-30T10:00:00Z',windSpeed:0,windDirection:0,windGust:0};
const rows=(direction,speed,gust=speed)=>Array.from({length:3},(_,i)=>({time:`2026-10-30T${11+i}:00:00Z`,windDirection:direction,windSpeed:speed,windGust:gust}));
assert.equal(predictForecast(rows(0,15),obs,'25',model)[0].baselineRwy18Open,false);
assert.equal(predictForecast(rows(0,14.99),obs,'25',model)[0].baselineRwy18Open,true);
assert.equal(predictForecast(rows(90,5,40),obs,'25',model)[0].baselineRwy18Open,true);
assert.equal(predictForecast(rows(90,5,40.01),obs,'25',model)[0].baselineRwy18Open,false);
assert.equal(predictForecast(rows(70,10),obs,'25',model)[0].baselineOD,'07');
assert.deepEqual(predictForecast(rows(70,3),obs,'25',model).map(x=>x.baselineOD),['25','07','07']);
assert.ok(Math.abs(windComponents(10,180).headwind-10)<1e-12);
const snap=JSON.parse(fs.readFileSync(new URL('../dist/data/forecast.json',import.meta.url),'utf8'));
assert.equal(snap.hourly.length,48);
for(const row of snap.hourly){assert.ok(row.p07>=0&&row.p07<=1);assert.ok(row.pRwy18Open>=0&&row.pRwy18Open<=1);assert.ok(Math.abs(row.p07+row.p25-1)<1e-12);}
console.log('PASS: Python/JS parity, runway threshold boundaries, immediate/persistent direction switches, and48-hour snapshot.');
