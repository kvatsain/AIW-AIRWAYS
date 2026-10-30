import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import {featuresFor,predictForecast} from '../dist/inference.js';
import {directionFeatures,inferDirection} from '../dist/direction-model.js';
const read=p=>JSON.parse(fs.readFileSync(new URL('../'+p,import.meta.url)));
const legacy=read('dist/data/model.json'),model=read('dist/data/direction-model.json'),metrics=read('dist/data/direction-metrics.json');
assert.equal(crypto.createHash('sha256').update(fs.readFileSync(new URL('../dist/data/model.json',import.meta.url))).digest('hex'),model.legacyClosureModelSha256);
for(const f of read('model/dfld-parity-fixture.json')){
 const base=featuresFor(f.row,f.observation,f.initialOD),features=directionFeatures(base,model.models[f.horizon].featureSet);
 features.forEach((v,i)=>assert.ok(Math.abs(v-f.features[i])<1e-10,`Feature parity ${i}`));
 assert.ok(Math.abs(inferDirection(base,f.horizon,model).p07-f.p07)<1e-12,'Python / browser probability parity');
}
const issue='2026-10-30T10:00:00Z',obs={time:issue,windSpeed:6,windDirection:250,windGust:8};
const weather=Array.from({length:48},(_,i)=>({time:new Date(Date.parse(issue)+(i+1)*3600000).toISOString(),windSpeed:2+i,windGust:3+i,windDirection:i*30%360}));
const old=predictForecast(weather,obs,'25',legacy,issue),updated=predictForecast(weather,obs,'25',legacy,issue,model);
updated.forEach((r,i)=>{assert.equal(r.pRwy18Open,old[i].pRwy18Open);assert.equal(r.pClosed18,old[i].pClosed18);assert.equal(r.baselineOD,old[i].baselineOD);assert.equal(r.directionModelVersion,'2.0.0');assert.ok(r.p07>=0&&r.p07<=1);});
const predictions=read('dist/data/direction-test-predictions.json'),labels=new Map(read('dist/data/dfld.json').days.flatMap(d=>d.directionBins.filter(b=>b.eligibleForModel).map(b=>[Date.parse(b.timeUtc),b.operatingDirection])));
for(const h of metrics.horizons){
 const rows=predictions.filter(r=>r.horizonHours===h.horizonHours);assert.equal(rows.length,h.testRows);
 for(const r of rows){assert.equal(Date.parse(r.validTimeUtc)-Date.parse(r.originUtc),r.horizonHours*3600000);assert.ok(Date.parse(r.validTimeUtc)>=Date.parse(metrics.split.testUtc[0])&&Date.parse(r.validTimeUtc)<Date.parse(metrics.split.testUtc[1]));assert.equal(labels.get(Date.parse(r.validTimeUtc)),r.actualDirection);}
 for(const [name,key] of [['dfldModel','p07'],['legacyModel','legacyP07'],['weatherRules','weatherRuleDirection']]){
  let loss=0,correct=0;const cm={tp:0,tn:0,fp:0,fn:0};
  for(const r of rows){const y=+(r.actualDirection==='07'),p=key==='weatherRuleDirection'?+(r[key]==='07'):r[key],pred=p>=.5;loss+=(p-y)**2;correct+=pred===Boolean(y);cm[pred?(y?'tp':'fp'):(y?'fn':'tn')]++;}
  assert.ok(Math.abs(loss/rows.length-h.targets[name].brier)<1e-12);assert.equal(correct/rows.length,h.targets[name].accuracy);assert.deepEqual(cm,h.targets[name].confusion);
 }
 assert.equal(h.validationBrier,Math.min(...h.validationCandidates.map(c=>c.brier)));
 assert.ok(h.nominalMinimumForecastAgeAtOriginHours>=18);
}
assert.equal(read('dist/data/forecast.json').hourly.every(r=>r.directionModelVersion==='2.0.0'),true);
console.log('Direction v2: 20 Python/browser parity cases, closure isolation, actual-label test metrics and chronology passed');
