import {inferDirection} from '../dist/direction-model.js';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {windComponents,predictForecast,featuresFor,inferRow} from '../dist/inference.js';
import {airportWindow,nextScheduleChange,alertFor,landingWind,ALERT_POLICIES} from '../dist/operations.js';
import {nextDirectionChange} from '../dist/forecast-summary.js';
import {project,airfieldSVG} from '../dist/airfield.js';
const model=JSON.parse(fs.readFileSync(new URL('../dist/data/model.json',import.meta.url)));
const snapshot=JSON.parse(fs.readFileSync(new URL('../dist/data/forecast.json',import.meta.url)));
const directionModel=JSON.parse(fs.readFileSync(new URL('../dist/data/direction-model.json',import.meta.url)));
const metrics=JSON.parse(fs.readFileSync(new URL('../dist/data/metrics.json',import.meta.url)));
const issue='2026-10-30T10:00:00Z';
const observation={time:issue,windSpeed:6,windDirection:250,windGust:6};
const row=(windDirection,windSpeed,windGust=windSpeed,time='2026-10-30T11:00:00Z')=>({time,windDirection,windSpeed,windGust});
const run=(r,od='25')=>predictForecast([r],observation,od,model)[0];
assert.ok(Math.abs(windComponents(20,330,180).tailwind-17.320508)<1e-5,'330/20 gives 17.3kt tailwind');
assert.equal(run(row(0,15)).baselineRwy18Open,false,'15kt tailwind closes18');
assert.equal(run(row(0,14.99)).baselineRwy18Open,true,'Just below15kt permitted');
assert.equal(run(row(180,20)).baselineRwy18Open,true,'Southerly is headwind');
assert.equal(run(row(270,30,40)).baselineRwy18Open,true,'Exactly40kt crosswind permitted by challenge');
assert.equal(run(row(270,30,40.01)).baselineRwy18Open,false,'Crosswind greater40 closes');
assert.equal(run(row(90,20)).baselineOD,'07','20kt easterly forces immediate switch');
assert.equal(run(row(250,20),'07').baselineOD,'25','20kt westerly forces immediate switch');
const times=['11:00','11:15','11:30','11:45'].map(t=>row(70,3,3,`2026-10-30T${t}:00Z`));
assert.deepEqual(predictForecast(times,observation,'25',model).map(r=>r.baselineOD),['25','25','25','07'],'Adverse wind tolerated30min, switches after30min');
const calm=run(row(0,0));assert.equal(calm.baselineOD,'25','Calm retains direction');
const missing=predictForecast([{time:issue,windSpeed:null,windDirection:null}],observation,'25',model)[0];assert.equal(missing.available,false,'Missing wind not silently accepted');
assert.equal(snapshot.hourly.length,48,'Saved forecast has48hours');
for(let i=0;i<snapshot.hourly.length;i++){
 const r=snapshot.hourly[i];assert.ok([r.p07,r.p25,r.pRwy18Open].every(p=>Number.isFinite(p)&&p>=0&&p<=1));assert.ok(Math.abs(r.p07+r.p25-1)<1e-12);
 if(i)assert.equal(new Date(r.time)-new Date(snapshot.hourly[i-1].time),3600000,'Contiguous hours');
 assert.ok(new Date(r.time)>new Date(snapshot.generatedAt),'No past forecast rows');
 const p=inferDirection(featuresFor(r,snapshot.observation,snapshot.initialOD??snapshot.currentOperations?.direction??'25'),r.horizonHours,directionModel);assert.ok(Math.abs(p.p07-r.p07)<1e-9,'Stored/browser inference agrees');
}
for(const h of metrics.horizons){assert.ok(h.archiveLeadHours>h.horizonHours,'Archive lead predates forecast origin');for(const target of Object.values(h.targets)){const c=target.model.confusion;assert.equal(c.tp+c.tn+c.fp+c.fn,h.testRows);assert.ok(target.weatherRules);}}
const policies=JSON.parse(fs.readFileSync(new URL('../dist/data/alert-policies.json',import.meta.url)));
for(const [name,p] of Object.entries(ALERT_POLICIES))assert.equal(p.threshold,policies.policyDefinitions[name].threshold,'UI policy matches measured threshold');
// Explicit UTC offsets exercise local-clock boundaries in both seasons.
for(const offset of ['+01:00','+02:00']){
 const day=offset==='+01:00'?'2026-10-30':'2026-07-30';
 for(const [clock,scheduled,delayed,shoulder] of [['04:59',false,false,false],['05:00',true,false,true],['05:59',true,false,true],['06:00',true,false,false],['21:59',true,false,false],['22:00',true,false,true],['22:59',true,false,true],['23:00',false,true,false],['23:59',false,true,false],['00:00',false,false,false]]){
  const w=airportWindow(`${day}T${clock}:00${offset}`);
  assert.equal(w.scheduledDepartures,scheduled,`${day} ${clock} departure schedule`);assert.equal(w.scheduledArrivals,scheduled);
  assert.equal(w.delayedWindow,delayed);assert.equal(w.shoulder,shoulder);
 }
}
assert.equal(nextScheduleChange('2026-03-28T23:30:00Z').time,'2026-03-29T03:00:00.000Z','Spring clock skips hour; reopen at05CEST');
assert.equal(nextScheduleChange('2026-10-24T23:30:00Z').time,'2026-10-25T04:00:00.000Z','Autumn repeats hour; reopen at05CET');
assert.equal(airportWindow('2026-10-25T00:30:00Z').localTime,airportWindow('2026-10-25T01:30:00Z').localTime,'Both repeated02:30 times map correctly');
const calmPolicy={...row(180,5),pClosed18:0.03,pRwy18Open:0.97};
assert.equal(alertFor(calmPolicy,'catchMore').scheduledAlert,true);assert.equal(alertFor(calmPolicy,'reduceFalseAlarms').scheduledAlert,false);
for(const mode of Object.keys(ALERT_POLICIES)){
 const threshold=ALERT_POLICIES[mode].threshold;
 assert.equal(alertFor({...calmPolicy,pClosed18:threshold},mode).weatherAlert,true,'Threshold inclusive');
 assert.equal(alertFor({...calmPolicy,pClosed18:threshold-1e-8},mode).weatherAlert,false);
 assert.equal(alertFor({...row(0,15),pClosed18:0},mode).scheduledAlert,true,'Physics override regardless of model/mode');
 assert.equal(alertFor({...row(270,30,40),pClosed18:0},mode).weatherAlert,false,'Exactly40 crosswind still allowed');
 assert.equal(alertFor({...row(270,30,40.01),pClosed18:0},mode).weatherAlert,true);
 const night=alertFor({...row(0,20,20,'2026-10-30T22:00:00Z'),pClosed18:0.9},mode);
 assert.equal(night.weatherAlert,true);assert.equal(night.scheduledAlert,false);assert.equal(night.status,'night','Night is not a wind-closure event');
}
assert.equal(alertFor({...calmPolicy,windSpeed:null,pClosed18:null,pRwy18Open:null}).status,'unknown');
assert.equal(landingWind({...row(250,10),p07:1}).label,'Landing tailwind reaches immediate direction-switch limit');
for(const h of policies.horizons)for(const split of ['test','validation'])for(const scope of ['allHours','scheduledHours']){
 const g=h[split][scope];
 for(const p of Object.values(g.policies)){const c=p.confusion;assert.equal(c.tp+c.tn+c.fp+c.fn,g.n);assert.equal(c.tp+c.fn,g.positiveHours);}
 assert.ok(g.policies.catchMore.confusion.tp>=g.policies.reduceFalseAlarms.confusion.tp);
 for(const closure of g.closureProxyHours){
  if(scope==='scheduledHours')assert.equal(airportWindow(closure.timeUTC).scheduledDepartures,true);
  for(const [name,p] of Object.entries(ALERT_POLICIES))assert.equal(closure.alerts[name],closure.closureScore>=p.threshold||closure.forecastWindLimitExceeded);
 }
}
console.log('Passed: wind boundaries and inference parity; both alert modes and hard-limit overrides; missing data; schedule/arrival/departure boundaries; summer/winter/DST transitions; night alert suppression; policy metric integrity.');
const shifts=[{time:'2026-10-30T11:00Z',p07:.8},{time:'2026-10-30T12:00Z',p07:.9},{time:'2026-10-30T13:00Z',p07:.2}];
assert.equal(nextDirectionChange(shifts,'25').time,shifts[0].time,'First-hour transition compared with origin is included');
assert.equal(nextDirectionChange(shifts,'07').time,shifts[2].time,'Later transition detected');
assert.equal(nextDirectionChange(shifts,'07').directionScore,.8,'Direction score at transition is preserved');
assert.equal(nextDirectionChange(shifts.slice(0,2),'07'),null,'No crossing means no shift signalled');
assert.equal(nextDirectionChange([{time:shifts[0].time,p07:null},shifts[1]],'25'),null,'Missing forecast cannot establish a timed crossing');
const geo=JSON.parse(fs.readFileSync(new URL('../dist/data/fra-airfield.json',import.meta.url)));
assert.equal(geo.features.filter(f=>f.properties.kind==='runway').length,4);
const r18=geo.features.find(f=>f.id==='runway-18').geometry.coordinates.map(project);
assert.ok(r18[1][1]>r18[0][1],'Southbound 18 draws down on north-up map');
assert.ok(Math.abs(r18[1][0]-r18[0][0])<3,'18 remains nearly true north/south');
const north=geo.features.find(f=>f.id==='runway-07L-25R').geometry.coordinates.map(project);
assert.ok(north[1][0]>north[0][0]&&north[1][1]<north[0][1],'07 points east-northeast');
assert.ok(geo.features.some(f=>f.properties.terminal==='T3'),'Map includes Terminal3');
assert.ok(airfieldSVG(geo,{p07:.9,windSpeed:20,windDirection:0,windGust:20}).includes('exceeds challenge wind limits'),'Map flags northerly closure limit');
assert.ok(!airfieldSVG(geo,{p07:.1,windSpeed:5,windDirection:180,windGust:5}).includes('>36<'),'No operational RWY36 label');
console.log('Passed: first-hour and later direction changes, missing-hour handling, actual airport geometry orientation and wind-limit map.');
