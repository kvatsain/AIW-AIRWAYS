import { predictForecast, normalizeWeather } from './inference.js';
import {airfieldSVG} from './airfield.js';
import {nextDirectionChange} from './forecast-summary.js';
import { airportWindow, nextScheduleChange, alertFor, landingWind } from './operations.js';

const $ = id => document.getElementById(id);
const state = { hours:48, selected:0, timezone:'Europe/Berlin', rows:[], snapshot:null, model:null, metrics:null, citations:[], mode:'snapshot', alertMode:'catchMore', policies:null, evidenceScope:'scheduledHours', audit:null, airfield:null };
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = (n,d=1) => Number.isFinite(Number(n)) ? Number(n).toFixed(d) : '—';
const percent = p => !Number.isFinite(p) ? '—' : p===0 ? '0%' : p===1 ? '100%' : p>0.999 ? '>99.9%' : p<0.001 ? '<0.1%' : `${(p*100).toFixed(1)}%`;
const utc = s => /(?:Z|[+-]\d\d:\d\d)$/.test(s) ? s : `${s}Z`;
const fmt = (s,opts={}) => new Intl.DateTimeFormat('en-GB',{timeZone:state.timezone,hour:'2-digit',minute:'2-digit',...opts}).format(new Date(utc(s)));
const full = s => /^\d{4}-\d{2}-\d{2}$/.test(s) ? new Intl.DateTimeFormat('en-GB',{timeZone:'UTC',year:'numeric',month:'short',day:'2-digit'}).format(new Date(s)) : fmt(s,{day:'2-digit',month:'short'});
const heading = r => r.p07>=0.5 ? '07' : '25';
const rows = () => state.rows.slice(0,state.hours);
const notice = (message,warn=false) => {$('notice').textContent=message;$('notice').classList.toggle('warning',warn);};
let toastTimer;
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,5500);}
function comp(direction,speed,gust,runway){const a=(direction-runway)*Math.PI/180;return {head:speed*Math.cos(a),tail:Math.max(0,-speed*Math.cos(a)),cross:Math.abs(Math.max(speed,gust)*Math.sin(a))};}
function currentRow(){return state.rows[state.selected];}
const policyFor = (r,mode=state.alertMode) => alertFor(r,mode,state.policies.policyDefinitions);
function describeStatus(){
 const age=(Date.now()-new Date(state.snapshot.weatherRetrievedAt??state.snapshot.generatedAt))/3600000;
 const mode=state.mode==='live' ? 'Weather refreshed' : 'Saved weather snapshot';
 const stale=age>3 ? ` · ${Math.floor(age)}h old — refresh recommended` : '';
 const originNote=state.snapshot.observation?.source?.includes('modeled')||state.snapshot.observation?.source?.includes('model current') ? ' Origin weather uses modeled current conditions; no fresh observation.' : '';
 const directionNote=state.snapshot.initialODSource==='wind-derived assumption' ? ' Initial direction is assumed from wind.' : '';
 notice(`${mode} ${full(state.snapshot.generatedAt)} ${state.timezone==='UTC'?'UTC':'Frankfurt'}${stale}.${originNote}${directionNote} Experimental weather-proxy probabilities; RWY 18 closure detection remains weak. Inspect wind-limit baseline before interpreting availability.`,age>3||Boolean(originNote));
}
function render(){
 if(!state.rows.length)return;
 state.selected=Math.min(state.selected,rows().length-1);
 const r=currentRow(),od=heading(r),conf=Math.max(r.p07,r.p25),c=comp(r.windDirection,r.windSpeed,r.windGust,180);
 $('forecast-date').textContent=`${full(state.rows[0].time)} — ${full(rows().at(-1).time)}`;
 $('selected-time').textContent=full(r.time);$('slider-label').textContent=`Hour ${state.selected+1} · ${full(r.time)}`;
 $('hour-slider').max=rows().length-1;$('hour-slider').value=state.selected;
 $('rwy-value').textContent=percent(r.pRwy18Open);$('rwy-bar').style.width=`${r.pRwy18Open*100}%`;
 $('rwy-caption').textContent=r.baselineRwy18Open===false ? 'Wind-limit baseline: NOT USABLE' : 'Weather proxy · closure skill limited';
 $('rwy-value').style.color=r.baselineRwy18Open===false ? '#edb888' : '';
 $('od-value').innerHTML=`${od} <small>${od==='07'?'Eastbound':'Westbound'}</small>`;
 $('od-caption').textContent=`${percent(conf)} model score · ${airportWindow(r.time).nightRestricted?'night: wind direction only':'weather proxy'}`;
 $('wind-value').innerHTML=`${num(r.windSpeed)} <small>kt · ${Math.round(r.windDirection)}°</small>`;
 $('wind-caption').textContent=`Gust ${num(r.windGust)} kt · from ${compass(r.windDirection)}`;
 const change=nextDirectionChange(rows(),state.snapshot.initialOD??state.snapshot.currentOperations?.direction);
 $('change-value').textContent=change?full(change.time):'No shift signalled';
 $('change-caption').textContent=change?`${change.from} → ${change.to} · ${percent(change.directionScore)} direction score; hourly estimate`:`No 50% crossing within ${rows().length} hours`;
 $('runway-callout-title').textContent=r.baselineRwy18Open===false ? 'RWY 18 exceeds a challenge wind limit' : 'RWY 18 within challenge wind limits';
 $('runway-callout-text').textContent=`Tailwind ${num(c.tail)} / 15 kt · crosswind incl. gust ${num(c.cross)} / 40 kt. Actual availability unverified.`;
 renderPlanning(r);renderMap(r);renderChart();renderStrips();renderTable();
}
function renderPlanning(r){
 const a=policyFor(r),w=a.window,next=nextScheduleChange(r.time),landing=landingWind(r);
 document.querySelectorAll('[data-policy]').forEach(b=>{const selected=b.dataset.policy===state.alertMode;b.classList.toggle('selected',selected);b.setAttribute('aria-pressed',String(selected));});
 $('policy-status').textContent=a.label;$('policy-status').className=`planning-status ${a.status}`;
 const upcoming=rows().filter(x=>policyFor(x).scheduledAlert===true).length;
 $('policy-detail').textContent=`Closure score ${percent(a.closureScore)} · alert threshold ${percent(a.threshold)}. ${a.reason}.${w.nightRestricted?' Weather signal retained; scheduled-flight wind alert suppressed at night.':''}`;
 $('policy-count').textContent=`${upcoming} scheduled-flight wind alert ${upcoming===1?'hour':'hours'} in this ${state.hours}h forecast`;
 $('airport-window').textContent=w.label;$('airport-window').className=`planning-status ${w.nightRestricted?'night':'clear'}`;
 $('airport-local-time').textContent=`Selected forecast · ${w.localTime} Frankfurt`;
 $('schedule-next').textContent=`Scheduled flight window ${next.opens?'reopens':'closes'} at ${next.localTime.slice(11)} Frankfurt${next.localTime.slice(0,10)!==w.localTime.slice(0,10)?' next day':''}.`;
 $('arrival-window').textContent=w.arrivals;$('departure-window').textContent=w.departures;
 $('landing-wind').textContent=`OD ${landing.direction??'—'} · ${landing.label}${Number.isFinite(landing.tailwind)?` (tailwind ${num(landing.tailwind)} kt; gust crosswind ${num(landing.crosswind)} kt)`:''}.`;
 $('schedule-footnote').textContent=w.shoulder?'Shoulder-hour movements are restricted. The 133-movement limit across 22–23 / 05–06 is averaged over the calendar year; slot availability is not modeled.':w.delayedWindow?'23:00–24:00: delayed landing eligibility is conditional; delay must not be built into the schedule. Departure permission is never inferred.':w.nightRestricted?'00:00–05:00: ordinary delayed and early flights are not admitted. Legally exempt flights remain possible.':'Daily scheduled takeoffs and landings: 05:00–23:00 Frankfurt local time. Night restrictions are independent of wind.';
}
function compass(d){return ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'][Math.round(d/22.5)%16];}
function renderMap(r){ $('airport-map').innerHTML=airfieldSVG(state.airfield,r); }
function renderChart(){
 const data=rows(),w=600,h=170,left=31,right=12,top=13,bottom=25,max=Math.max(20,Math.ceil(Math.max(...data.map(r=>r.windGust))/10)*10),x=i=>left+i*(w-left-right)/(data.length-1||1),y=v=>h-bottom-v*(h-top-bottom)/max;
 let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Wind speed, gust and runway 18 tailwind forecast in knots"><defs><linearGradient id="wind-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#c3df9d" stop-opacity=".25"/><stop offset="1" stop-color="#c3df9d" stop-opacity="0"/></linearGradient></defs>`;
 for(let tick=0;tick<=max;tick+=max/4)svg+=`<line x1="${left}" x2="${w-right}" y1="${y(tick)}" y2="${y(tick)}" stroke="#edf0f2"/><text x="${left-9}" y="${y(tick)+3}" text-anchor="end" fill="#9ca6af" font-size="8">${tick}</text>`;
 const path=fn=>data.map((r,i)=>`${i?'L':'M'}${x(i).toFixed(1)} ${y(fn(r)).toFixed(1)}`).join(' ');
 svg+=`<path d="${path(r=>r.windSpeed)} L${x(data.length-1)} ${y(0)} L${x(0)} ${y(0)}Z" fill="url(#wind-fill)"/><path d="${path(r=>r.windGust)}" stroke="#8faede" stroke-width="1.6" stroke-dasharray="4 4" fill="none"/><path d="${path(r=>r.windSpeed)}" stroke="#8eb959" stroke-width="2.5" fill="none"/><path d="${path(r=>comp(r.windDirection,r.windSpeed,r.windGust,180).tail)}" stroke="#dfad84" stroke-width="1.4" fill="none"/>`;
 for(let i=0;i<data.length;i+=Math.max(1,Math.floor(data.length/6)))svg+=`<text x="${x(i)}" y="${h-7}" text-anchor="middle" fill="#939fa9" font-size="8">${fmt(data[i].time)}</text>`;
 svg+=`<line x1="${x(state.selected)}" x2="${x(state.selected)}" y1="${top}" y2="${y(0)}" stroke="#83967a" stroke-dasharray="3 3"/><circle cx="${x(state.selected)}" cy="${y(currentRow().windSpeed)}" r="4" fill="#8eb959" stroke="white" stroke-width="2"/></svg>`;
 $('wind-chart').innerHTML=svg;
}
function renderStrips(){
 for(const id of ['rwy-strip','od-strip','schedule-strip'])$(id).style.setProperty('--hours',rows().length);
 $('rwy-strip').innerHTML=rows().map((r,i)=>`<button data-index="${i}" class="${i===state.selected?'is-selected':''}" style="background:${r.baselineRwy18Open===false?'#df9c72':`hsl(${45+r.pRwy18Open*45} 44% ${77-r.pRwy18Open*12}%)`}" aria-label="${esc(full(r.time))}: RWY 18 ${percent(r.pRwy18Open)}" title="${esc(full(r.time))} · ${percent(r.pRwy18Open)}${r.baselineRwy18Open===false?' · wind limit exceeded':''}"></button>`).join('');
 $('od-strip').innerHTML=rows().map((r,i)=>`<button data-index="${i}" class="${i===state.selected?'is-selected':''}" style="background:${heading(r)==='07'?'#91b3df':'#b3d98c'}" aria-label="${esc(full(r.time))}: direction ${heading(r)}" title="${esc(full(r.time))} · OD ${heading(r)} · ${percent(Math.max(r.p07,r.p25))}"></button>`).join('');
 $('schedule-strip').innerHTML=rows().map((r,i)=>{const a=policyFor(r);return `<button data-index="${i}" class="${a.status} ${i===state.selected?'is-selected':''}" aria-label="${esc(full(r.time))}: ${a.label}" title="${esc(full(r.time))} · ${a.label} · ${a.window.localTime.slice(11)} Frankfurt"></button>`;}).join('');
 $('strip-times').innerHTML=[0,Math.floor(rows().length/2),rows().length-1].map(i=>`<span>${esc(full(rows()[i].time))}</span>`).join('');
}
function renderTable(){
 $('hourly-rows').innerHTML=rows().map((r,i)=>{const a=policyFor(r);return `<tr class="${state.selected===i?'selected':''} ${a.window.nightRestricted?'night-row':''}" data-index="${i}" tabindex="0" aria-label="Inspect forecast for ${esc(full(r.time))}"><td><strong>${esc(full(r.time))}</strong></td><td>${num(r.windSpeed)} / ${num(r.windGust)} kt <span class="muted">${Math.round(r.windDirection)}°</span></td><td><span class="prob-badge ${r.baselineRwy18Open===false?'caution':''}">${percent(r.pRwy18Open)}</span></td><td><span class="od-badge ${heading(r)==='07'?'east':''}">${heading(r)}</span> &nbsp;${percent(Math.max(r.p07,r.p25))}</td><td><span class="status-badge ${a.status}">${a.label}</span>${a.window.delayedWindow?'<small>Conditional delays before midnight</small>':''}</td></tr>`;}).join('');
}
function scenario(){
 const direction=+$('scenario-direction').value,speed=+$('scenario-speed').value;
 $('scenario-gust').min=speed;if(+$('scenario-gust').value<speed)$('scenario-gust').value=speed;
 const gust=+$('scenario-gust').value;
 $('direction-out').textContent=`${direction}° · ${compass(direction)}`;$('speed-out').textContent=`${speed} kt`;$('gust-out').textContent=`${gust} kt`;
 const c=comp(direction,speed,gust,180),e=comp(direction,speed,gust,70),allowed=c.tail<15&&c.cross<=40,od=Math.abs(e.head)<1e-7?'Retain current':e.head>0?'07 · east':'25 · west';
 $('scenario-results').innerHTML=`<div class="scenario-line"><span>RWY 18 wind usability</span><strong class="${allowed?'good':'bad'}">${allowed?'Permitted':'Not permitted'}</strong></div><div class="scenario-line"><span>18 tailwind / gust crosswind</span><strong>${num(c.tail)} / ${num(c.cross)} kt</strong></div><div class="scenario-line"><span>Steady-wind direction</span><strong>${esc(od)}</strong></div>${e.cross>40?'<div class="bad">Parallel runways also exceed crosswind limit.</div>':''}`;
}
function renderEvidence(){
 const m=state.metrics,hs=m.horizons.filter(h=>[1,6,24].includes(h.horizonHours));
 const brier=v=>v==null?'—':v.toFixed(4);
 const rule=x=>x.rules??x.ruleBaseline??x.weatherRules??x.deterministic??x.baseline;
 $('metrics-content').innerHTML=`<div class="metric-note"><strong>${Number(m.counts.rawMetarReports).toLocaleString()} METAR reports</strong> · ${m.split.trainPeriod.join(' to ')} training.<br>Test: ${m.split.testPeriod.join(' to ')} · ${m.split.purgeHours}h split gap.<br>Scores below measure <strong>weather-derived direction</strong>.</div><div class="table-scroll"><table><thead><tr><th>Lead</th><th>Test n</th><th>OD accuracy</th><th>ML Brier ↓</th><th>Rules Brier ↓</th></tr></thead><tbody>${hs.map(h=>`<tr><td>${h.horizonHours}h</td><td>${h.testRows.toLocaleString()}</td><td>${percent(h.targets.od07.model.accuracy)}</td><td>${brier(h.targets.od07.model.brier)}</td><td>${brier(rule(h.targets.od07)?.brier)}</td></tr>`).join('')}</tbody></table></div><p class="metric-note">Brier score measures probability error; lower is better. The rule baseline applies challenge limits to the same archived weather inputs.</p><div class="rule-difference"><strong>RWY 18: rare-event limitation</strong><p class="metric-note">Only ${hs[0].targets.closed18.model.positiveEvents} closure-proxy hours in the 1h test set. At a 50% threshold, the model detected ${hs[0].targets.closed18.model.confusion.tp}/${hs[0].targets.closed18.model.positiveEvents}. High overall accuracy would conceal this failure.</p></div><div class="table-scroll"><table><thead><tr><th>Lead</th><th>18 ML Brier ↓</th><th>Rules Brier ↓</th><th>Closure recall</th></tr></thead><tbody>${hs.map(h=>`<tr><td>${h.horizonHours}h</td><td>${brier(h.targets.closed18.model.brier)}</td><td>${brier(rule(h.targets.closed18)?.brier)}</td><td>${percent(h.targets.closed18.model.recall)}</td></tr>`).join('')}</tbody></table></div><p class="metric-note">Archive forecast ages at valid time: 24h for 1h/6h, 48h for 24h, and 72h for 48h. The live dashboard uses fresher ICON forecasts; these test results do not establish live performance.</p>`;
 $('model-method').textContent=state.model.algorithm+'. Uses forecast wind components, recent observed wind, direction state, and season/time.';
 $('model-card').innerHTML=[['Purpose','48-hour research forecasts for RWY 18 wind usability and airport-wide OD 07/25.'],['Data & target',`${m.counts.rawMetarReports.toLocaleString()} EDDF METAR reports; DWD ICON Previous Runs. Weather-derived challenge targets; actual operations remain unvalidated.`],['Training & validation',`${m.split.trainPeriod.join(' to ')} training. ${m.split.validationPeriod.join(' to ')} validation. ${m.split.purgeHours}h separation before each later split.`],['Key drivers',state.model.featureNames.filter(n=>/nwp|obs/.test(n)).join(', ')],['Interpreting the probabilities','Regularized logistic scores, assessed with held-out Brier scores. Operational calibration is unverified. Nearest tested horizon is used between 1, 6, 24 and 48 hours.'],['Known limits',m.limitations.join(' ')],['Weather rules','True headings: 070°, 250°, 180°. Tailwind 18 ≥15 kt; gust crosswind >40 kt. OD switch ≥10 kt or adverse wind lasting >30 minutes. Hourly forecasts cannot time a switch to the minute.'],['Next validation step','Add time-stamped actual operating direction and RWY 18 availability. Score held-out jury days using only forecasts and observations available at issue time.']].map(([k,v])=>`<div><strong>${esc(k)}</strong>${esc(v)}</div>`).join('');
 renderPolicyEvidence();renderSources();renderAudit();
}
function renderPolicyEvidence(){
 const p=state.policies,scope=state.evidenceScope;
 $('policy-evidence').innerHTML=p.horizons.map(h=>{
   const test=h.test[scope],v=h.validation[scope],c=test.policies.catchMore,f=test.policies.reduceFalseAlarms;
   return `<tr><td><strong>${h.horizonHours}h</strong></td><td>${test.n.toLocaleString()} / ${test.positiveHours}</td><td>${c.confusion.tp}/${test.positiveHours}<small>${c.confusion.fn} missed</small></td><td>${c.confusion.fp}<small>${num(c.precision*100)}% precision</small></td><td>${f.confusion.tp}/${test.positiveHours}<small>${f.confusion.fn} missed</small></td><td>${f.confusion.fp}<small>${f.precision===null?'No alerts':`${num(f.precision*100)}% precision`}</small></td><td>${v.policies.catchMore.confusion.tp}/${v.positiveHours} · ${v.policies.reduceFalseAlarms.confusion.tp}/${v.positiveHours}</td></tr>`;
 }).join('');
 $('policy-evidence-caption').textContent=`Test: ${p.split.testPeriod.join(' to ')}. ${scope==='scheduledHours'?'Only 05:00–23:00 Europe/Berlin; night hours excluded from every denominator.':'All hours: weather-only diagnostics; night restrictions never added to closure targets.'} Counts are hourly weather proxies, not independent airport closure events. Validation column shows detected / positive hours for catch / reduce modes.`;
}
function renderSources(){
 const snapshot=state.snapshot,obs=snapshot.observation,ops=snapshot.currentOperations;
 const extra=[{title:'Fraport operating-direction guidance',url:'https://www.fraport.com/en/business-areas/operations/airside-and-terminal-operations/easterly-and-westerly-operations.html',role:'Public guidance describes a 5 kt landing tailwind threshold. Challenge assumptions deliberately follow the supplied 10 kt brief.'},{title:'Problem2 audio briefing',url:null,role:'User-provided 6m29s explanation. Transcribed locally. Confirms the 48-hour horizon and the two forecast targets; numeric rules come from the PDF.'}];
 extra.push({title:'Fraport flight operating hours',url:'https://www.fraport.com/en/sustainability/dialog-with-neighbors/noise-and-air/flight-operations/runway-system-and-operating-hours.html',role:'Scheduled flights 05:00–23:00 local; night restriction 23:00–05:00. Shoulder hours 22:00–23:00 and 05:00–06:00 have movement restrictions. Uses Europe/Berlin, including daylight saving time.'},{title:'Hessen: delayed takeoffs and landings',url:'https://wirtschaft.hessen.de/Verkehr/Luftverkehr/Verspaetete-Starts-und-Landungen',role:'Before midnight, eligible delayed landings scheduled before 23:00 may arrive; delayed departures need individual permission. No ordinary delayed or early flights 00:00–05:00. Statutory exemptions remain possible. Verified 30 October 2026.'});
 $('sources-content').innerHTML=[...state.citations,...extra].map((s,i)=>`<article class="panel source-card"><div class="source-type">${i<4?'WEATHER DATA':i===4||s.title.includes('hours')||s.title.includes('Hessen')?'OPERATIONAL CONTEXT':'CHALLENGE CONTEXT'}</div><h2>${esc(s.title)}</h2><p>${esc(s.role)}</p>${s.url?`<a href="${esc(s.url)}" target="_blank" rel="noopener">Open original source ↗</a>`:'<span class="source-meta">User-provided reference</span>'}${s.title.includes('NOAA')&&obs?`<div class="source-meta">Observation: ${esc(full(obs.time))}<br>${esc(obs.rawMetar||'Model-based origin; no fresh METAR available')}</div>`:''}${s.title.includes('Umwelthaus')&&ops?`<div class="source-meta">Saved report: OD ${esc(ops.direction)}, checked ${esc(full(ops.verifiedAt))}. This is a saved snapshot; weather refresh does not refresh the operations report.</div>`:''}</article>`).join('');
}
async function refresh(){
 $('refresh').disabled=true;$('refresh').textContent='↻ Fetching weather…';
 try{
 const params=new URLSearchParams({latitude:'50.0379',longitude:'8.5622',hourly:'wind_speed_10m,wind_direction_10m,wind_gusts_10m,temperature_2m,relative_humidity_2m,pressure_msl,precipitation',current:'wind_speed_10m,wind_direction_10m,wind_gusts_10m',wind_speed_unit:'kn',timezone:'UTC',forecast_days:'4',past_days:'1'});
 const res=await fetch(`https://api.open-meteo.com/v1/dwd-icon?${params}`,{signal:AbortSignal.timeout(20000)});if(!res.ok)throw Error(`Weather service returned ${res.status}`);
 const data=await res.json();if(!data.hourly?.time||!data.current)throw Error('Incomplete weather response');
 const now=new Date(),old=state.snapshot.observation,freshObs=old&&now-new Date(old.time)<90*60000;
 const observation=freshObs?old:{time:utc(data.current.time),windSpeed:data.current.wind_speed_10m,windDirection:data.current.wind_direction_10m,windGust:data.current.wind_gusts_10m,eastTrend3h:0,northTrend3h:0,source:'DWD ICON model current conditions (not an observation)'};
 if([observation.windSpeed,observation.windDirection,observation.windGust].some(x=>!Number.isFinite(x)))throw Error('Missing origin wind values');
 const latestOps=state.snapshot.currentOperations,opsFresh=latestOps&&now-new Date(latestOps.verifiedAt)<3600000;
 const initialOD=opsFresh?latestOps.direction:(comp(observation.windDirection,observation.windSpeed,observation.windGust,70).head>=0?'07':'25');
 const future=normalizeWeather(data.hourly).filter(r=>new Date(utc(r.time))>now).slice(0,48);
 if(future.some(r=>![r.windSpeed,r.windDirection,r.windGust].every(Number.isFinite)))throw Error('Forecast wind or gust data are missing');
 const result=predictForecast(future,observation,initialOD,state.model,now.toISOString());
 const nextRows=(Array.isArray(result)?result:result.hourly).filter(r=>new Date(utc(r.time))>now).slice(0,48);
 if(nextRows.length<48)throw Error(`Only ${nextRows.length} future hours returned; keeping prior snapshot`);
 validateRows(nextRows);
 state.rows=nextRows;state.snapshot={...state.snapshot,generatedAt:now.toISOString(),issuedAt:now.toISOString(),weatherRetrievedAt:now.toISOString(),weatherTimestamp:utc(data.current.time),observation,hourly:nextRows,weather:data,initialOD,initialODSource:opsFresh?'saved recent operations report':'wind-derived assumption'};state.mode='live';state.selected=0;
 describeStatus();render();renderSources();
 if(!freshObs)notice('Weather refreshed. Origin wind now uses ICON model current conditions because the saved METAR is older than 90 minutes. Initial operating direction is assumed from wind unless a recent operations snapshot exists. Weather-proxy model only.',true);
 toast('48-hour weather forecast updated.');
 }catch(error){notice(`Weather refresh failed: ${error.message}. Displaying the saved forecast from ${full(state.snapshot.generatedAt)}.`,true);toast('Saved forecast retained; no values were fabricated.');}
 finally{$('refresh').disabled=false;$('refresh').textContent='↻  Refresh weather';}
}
function validateRows(rr){if(!rr.length||rr.some(r=>![r.windSpeed,r.windDirection,r.windGust,r.pRwy18Open,r.p07,r.p25].every(Number.isFinite)||r.pRwy18Open<0||r.pRwy18Open>1||Math.abs(r.p07+r.p25-1)>1e-5))throw Error('Forecast data validation failed');}
function exportCSV(){
 const change=nextDirectionChange(state.rows,state.snapshot.initialOD??state.snapshot.currentOperations?.direction);
 const cols=['issued_at_utc','valid_time_utc','valid_time_frankfurt','schedule_timezone','lead_hours','p_rwy18_wind_usable','p_od07','p_od25','predicted_od','od_certainty_score','next_change_time_utc','next_change_to','change_direction_score','change_resolution_hours','wind_speed_kt','wind_direction_true_deg','gust_kt','baseline_rwy18_usable','baseline_od','scheduled_departures_window','scheduled_arrivals_window','night_restriction','conditional_delay_window','departure_rule','arrival_rule','closure_score','catch_threshold','reduce_threshold','catch_weather_alert','reduce_weather_alert','catch_scheduled_alert','reduce_scheduled_alert','selected_alert_mode','selected_planning_status','target_basis','source'];
 const lines=state.rows.map((r,i)=>{const c=policyFor(r,'catchMore'),f=policyFor(r,'reduceFalseAlarms'),w=c.window;return [state.snapshot.issuedAt??state.snapshot.generatedAt,utc(r.time),w.localTime,w.timeZone,r.leadHours??r.horizonHours??i+1,r.pRwy18Open,r.p07,r.p25,heading(r),Math.max(r.p07,r.p25),change?.time??'',change?.to??'',change?.directionScore??'',1,r.windSpeed,r.windDirection,r.windGust,r.baselineRwy18Open,r.baselineOD,w.scheduledDepartures,w.scheduledArrivals,w.nightRestricted,w.delayedWindow,w.departures,w.arrivals,c.closureScore,c.threshold,f.threshold,c.weatherAlert,f.weatherAlert,c.scheduledAlert,f.scheduledAlert,state.alertMode,policyFor(r).label,'weather-derived proxy; flight window does not establish permission',state.snapshot.source].map(x=>`"${String(x??'').replaceAll('"','""')}"`).join(',');});
 const blob=new Blob([cols.join(',')+'\n'+lines.join('\n')],{type:'text/csv;charset=utf-8'}),a=document.createElement('a'),url=URL.createObjectURL(blob);a.href=url;a.download=`fra-windlab-${state.snapshot.generatedAt.slice(0,10)}-48h.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('48-hour forecast exported with probabilities and provenance.');
}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>{
 document.querySelectorAll('[data-view]').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.view').forEach(x=>x.hidden=x.id!==b.dataset.view);
 const text={overview:['A clearer view of the next 48 hours.','Wind-based runway availability and operating-direction forecasts.'],model:['Understand what the model knows.','Measured results, baseline comparisons, and the limits of the evidence.'],sources:['Every forecast has a source.','Weather observations, numerical forecasts, and the challenge assumptions.']};
 $('view-title').textContent=text[b.dataset.view][0];$('view-subtitle').textContent=text[b.dataset.view][1];
}));
document.querySelectorAll('[data-hours]').forEach(b=>b.addEventListener('click',()=>{state.hours=+b.dataset.hours;document.querySelectorAll('[data-hours]').forEach(x=>x.classList.toggle('selected',x===b));render();}));
$('hour-slider').addEventListener('input',e=>{state.selected=+e.target.value;render();});
for(const id of ['rwy-strip','od-strip','schedule-strip','hourly-rows'])$(id).addEventListener('click',e=>{const el=e.target.closest('[data-index]');if(el){state.selected=+el.dataset.index;render();}});
document.querySelectorAll('[data-policy]').forEach(b=>b.addEventListener('click',()=>{state.alertMode=b.dataset.policy;render();}));
$('evidence-scope').addEventListener('change',e=>{state.evidenceScope=e.target.value;renderPolicyEvidence();});
$('hourly-rows').addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();state.selected=+e.target.closest('[data-index]').dataset.index;render();}});
['scenario-direction','scenario-speed','scenario-gust'].forEach(id=>$(id).addEventListener('input',scenario));
$('timezone').addEventListener('change',e=>{state.timezone=e.target.value;render();renderSources();describeStatus();});
$('expand-map').addEventListener('click',()=>{const expanded=$('airfield-grid').classList.toggle('map-expanded');$('expand-map').textContent=expanded?'Compact map':'Expand map';$('expand-map').setAttribute('aria-expanded',String(expanded));});
$('refresh').addEventListener('click',refresh);$('export').addEventListener('click',exportCSV);
$('clock').textContent=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Berlin',day:'2-digit',month:'short',year:'numeric'}).format(new Date())+' · Frankfurt';
async function init(){
 try{const files=await Promise.all(['forecast','model','metrics','citations','alert-policies','deliverables','fra-airfield'].map(async name=>{const r=await fetch(`data/${name}.json`);if(!r.ok)throw Error(`Missing ${name}.json`);return r.json();}));
 [state.snapshot,state.model,state.metrics,state.citations,state.policies,state.audit,state.airfield]=files;state.rows=state.snapshot.hourly;
 if(!state.rows.length){const future=normalizeWeather(state.snapshot.weather.hourly).filter(r=>new Date(utc(r.time))>new Date(state.snapshot.generatedAt)).slice(0,48);const result=predictForecast(future,state.snapshot.observation,state.snapshot.currentOperations?.direction??'25',state.model,state.snapshot.issuedAt??state.snapshot.generatedAt);state.rows=Array.isArray(result)?result:result.hourly;}
 validateRows(state.rows);describeStatus();render();renderEvidence();scenario();
 }catch(error){notice(`Dashboard could not load: ${error.message}. Check that the trained data artifacts are available.`,true);$('export').disabled=true;$('refresh').disabled=true;console.error(error);}
}
init();

function renderAudit(){
 const a=state.audit;
 $('delivery-cards').innerHTML=a.deliverables.map(d=>`<article class="delivery-card"><span class="delivery-status ${d.status}">${d.status==='met'?'REACHED':'PARTIAL'}</span><h3>${d.id}. ${esc(d.title)}</h3><p>${esc(d.reached)}</p><p class="delivery-gap"><strong>Still needed:</strong> ${esc(d.remaining)}</p></article>`).join('');
 $('baseline-comparison').innerHTML=a.horizons.map(h=>{const t=h.targets.od07;return `<tr><td>${h.horizonHours}h</td><td>${t.comparisonRows.toLocaleString()}</td><td>${(t.modelAccuracy*100).toFixed(2)}%</td><td>${(t.rulesAccuracy*100).toFixed(2)}%</td><td class="${t.accuracyGainPercentagePoints>0?'good':'bad'}">${t.accuracyGainPercentagePoints>0?'+':''}${t.accuracyGainPercentagePoints.toFixed(2)} pp</td><td>${(t.brierSkillVsRules*100).toFixed(1)}% lower</td></tr>`;}).join('');
 $('audit-method').textContent=a.method;
}
