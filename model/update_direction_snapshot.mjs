import fs from 'node:fs';
import {featuresFor} from '../dist/inference.js';
import {inferDirection} from '../dist/direction-model.js';
const root=new URL('../dist/data/',import.meta.url),read=n=>JSON.parse(fs.readFileSync(new URL(n,root)));
const snapshot=read('forecast.json'),model=read('direction-model.json');
const before=snapshot.hourly.map(r=>r.pRwy18Open),initial=snapshot.initialOD??snapshot.currentOperations?.direction??'25';
snapshot.hourly=snapshot.hourly.map(r=>{
 const direction=inferDirection(featuresFor(r,snapshot.observation,initial),r.leadHours??r.horizonHours,model);
 return {...r,...direction,predictedOD:direction.p07>=.5?'07':'25',targetBasis:'RWY18 weather proxy; direction DFLD-reported operations'};
});
if(snapshot.hourly.some((r,i)=>r.pRwy18Open!==before[i]))throw Error('Closure probability changed');
snapshot.directionModelVersion=model.version;snapshot.directionModelAppliedAt=new Date().toISOString();
fs.writeFileSync(new URL('forecast.json',root),JSON.stringify(snapshot,null,2)+'\n');
console.log('Updated 48 direction predictions; closure probabilities and weather issue time unchanged.');
