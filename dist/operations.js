// Flight scheduling is an independent layer; it never changes weather probabilities.
// Europe/Berlin resolves the airport's summer/winter clock, including DST transitions.
const localClock = new Intl.DateTimeFormat('en-GB', {
  timeZone:'Europe/Berlin', year:'numeric', month:'2-digit', day:'2-digit',
  hour:'2-digit', minute:'2-digit', hourCycle:'h23'
});
export const ALERT_POLICIES = {
  catchMore:{label:'Catch more closures',threshold:0.01},
  reduceFalseAlarms:{label:'Reduce false alarms',threshold:0.10}
};
const toDate = value => value instanceof Date ? value : new Date(/(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`);
export function airportWindow(time) {
  const date=toDate(time);
  if(!Number.isFinite(date.getTime())) throw new Error('Invalid airport schedule timestamp');
  const parts=Object.fromEntries(localClock.formatToParts(date).map(p=>[p.type,p.value]));
  const hour=Number(parts.hour), scheduled=hour>=5&&hour<23;
  const shoulder=scheduled&&(hour===5||hour===22), delayedWindow=hour===23;
  return {
    timeZone:'Europe/Berlin', localTime:`${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`,
    hour, scheduledDepartures:scheduled, scheduledArrivals:scheduled,
    shoulder, delayedWindow, nightRestricted:!scheduled,
    label:scheduled?(shoulder?'Scheduled flights · shoulder hour':'Scheduled flight window'):'Night restriction',
    departures:scheduled?'Scheduled departures permitted by time window.':delayedWindow?'Delayed departures need individual authority permission.':'No routine departures; exceptional permissions only.',
    arrivals:scheduled?'Scheduled landings permitted by time window.':delayedWindow?'Eligible delayed landings scheduled before 23:00 may arrive before midnight.':'No routine or early landings before 05:00; exceptional permissions only.',
    exceptionNote:'Emergency, medical and other legally exempt flights may operate. This dashboard does not establish eligibility or permission.'
  };
}
export function nextScheduleChange(time) {
  const date=toDate(time), before=airportWindow(date).scheduledDepartures;
  for(let ms=Math.floor(date.getTime()/3600000)*3600000+3600000;ms<date.getTime()+27*3600000;ms+=3600000){
    const next=airportWindow(new Date(ms));
    if(next.scheduledDepartures!==before) return {time:new Date(ms).toISOString(),localTime:next.localTime,opens:next.scheduledDepartures};
  }
  throw new Error('No airport schedule boundary found');
}
export function alertFor(row, mode='catchMore', policies=ALERT_POLICIES) {
  const policy=policies[mode];
  if(!policy||!Number.isFinite(policy.threshold))throw new Error('Unknown alert policy');
  const window=airportWindow(row.time);
  const closureScore=Number.isFinite(row.pClosed18)?row.pClosed18:Number.isFinite(row.pRwy18Open)?1-row.pRwy18Open:null;
  const windKnown=[row.windSpeed,row.windDirection,row.windGust].every(Number.isFinite);
  const angle=(row.windDirection-180)*Math.PI/180;
  const windLimitExceeded=windKnown?Math.max(0,-row.windSpeed*Math.cos(angle))>=15||Math.abs(Math.max(row.windSpeed,row.windGust)*Math.sin(angle))>40:null;
  const modelTriggered=closureScore===null?null:closureScore>=policy.threshold;
  const weatherAlert=windLimitExceeded===true||modelTriggered===true?true:windLimitExceeded===null||modelTriggered===null?null:false;
  const scheduledAlert=window.scheduledDepartures?weatherAlert:false;
  return {
    mode,threshold:policy.threshold,closureScore,windLimitExceeded,modelTriggered,weatherAlert,scheduledAlert,window,
    reason:windLimitExceeded===true?'Forecast exceeds a challenge wind limit':modelTriggered===true?'Closure score reaches the selected threshold':weatherAlert===null?'Weather data incomplete':'Below threshold and within challenge wind limits',
    status:window.nightRestricted?'night':weatherAlert===null?'unknown':weatherAlert?'alert':'clear',
    label:window.nightRestricted?'Night restriction':weatherAlert===null?'Weather unknown':weatherAlert?'Wind alert':'No wind alert'
  };
}
export function landingWind(row) {
  if(![row.windSpeed,row.windDirection,row.windGust,row.p07].every(Number.isFinite))return {label:'Landing wind unknown'};
  const direction=row.p07>=0.5?'07':'25',angle=(row.windDirection-(direction==='07'?70:250))*Math.PI/180;
  const tailwind=Math.max(0,-row.windSpeed*Math.cos(angle)),crosswind=Math.abs(Math.max(row.windSpeed,row.windGust)*Math.sin(angle));
  return {direction,tailwind,crosswind,label:crosswind>40?'Parallel-runway crosswind limit exceeded':tailwind>=10?'Landing tailwind reaches immediate direction-switch limit':'Landing wind within immediate challenge limits'};
}
