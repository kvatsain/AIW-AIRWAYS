// Independent direction classifier: the legacy closure model is never rescaled.
const indices=[0,1,2,3,4,5,6,7,8,9,10,11,13,14];
export function directionFeatures(base,kind){
 const x=indices.map(i=>base[i]);if(kind==='weather-linear')return x;
 if(kind!=='weather-nonlinear')throw Error('Unknown direction feature set');
 const originHead=base[7]*Math.sin(70*Math.PI/180)+base[8]*Math.cos(70*Math.PI/180);
 return [...x,Math.tanh(base[6]/5),Math.max(-25,Math.min(25,base[6]*originHead/25)),Math.abs(base[0]),Math.abs(base[1]),Math.max(-100,Math.min(100,base[0]*base[3]/20))];
}
export function inferDirection(base,lead,model){
 const horizon=Object.keys(model.models).map(Number).reduce((best,h)=>Math.abs(h-lead)<Math.abs(best-lead)?h:best,1),spec=model.models[horizon];
 const features=directionFeatures(base,spec.featureSet),z=features.map((v,i)=>(v-spec.mean[i])/spec.scale[i]);
 if(z.some(v=>!Number.isFinite(v)))throw Error('Invalid direction features');
 const logit=spec.intercept+z.reduce((sum,v,i)=>sum+v*spec.weights[i],0),p07=1/(1+Math.exp(-Math.max(-35,Math.min(35,logit))));
 return {p07,p25:1-p07,directionModelHorizonHours:horizon,directionModelVersion:model.version,directionTargetBasis:model.targetBasis,directionOutOfDistribution:z.some(v=>Math.abs(v)>6)};
}
