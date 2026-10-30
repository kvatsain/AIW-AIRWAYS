import assert from 'node:assert/strict';
import fs from 'node:fs';
import {validateDfld,observedHour} from '../dist/dfld.js';
const data=JSON.parse(fs.readFileSync(new URL('../dist/data/dfld.json',import.meta.url)));
assert.equal(validateDfld(data),data);
for(const day of data.days){
 assert.equal(day.runways.reduce((n,r)=>n+r.departures+r.arrivals,0),day.totalMovements);
 assert.equal(day.runways.find(r=>r.runway==='18').departures,day.rwy18Departures);
 const empty=day.hourlyMovements.findIndex(h=>h.rwy18Departures===0);
 assert.notEqual(empty,-1);
 assert.equal(observedHour(day,empty).closureStatus,'Unknown','No movements must never become a closure label');
 assert.equal(observedHour(day,empty).rwy18Status,'No recorded departures');
}
const bad=structuredClone(data);bad.days[0].hourlyMovements[0].rwy18Closed=true;
assert.throws(()=>validateDfld(bad),/movement counts/);
const missing=structuredClone(data);missing.days[0].directionBins[0].operatingDirection=null;
assert.equal(validateDfld(missing).days[0].directionBins[0].operatingDirection,null,'Missing direction stays unknown');
const zero=structuredClone(data);zero.days[0].directionBins[0].windDirectionDeg=0;
assert.equal(validateDfld(zero).days[0].directionBins[0].windDirectionDeg,0,'Zero bearing must not become missing');
const broken=structuredClone(data);broken.days[0].totalMovements++;
assert.throws(()=>validateDfld(broken),/reconcile/);
const dup=structuredClone(data);dup.days.push(dup.days[0]);assert.throws(()=>validateDfld(dup),/Incomplete/);
const timezone=structuredClone(data);timezone.sourceTimezone='UTC';assert.throws(()=>validateDfld(timezone),/Unsupported/);
console.log('DFLD: totals, missing values, provenance contract and no-use/closure distinction passed');
