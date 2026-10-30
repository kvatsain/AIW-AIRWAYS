// Historical DFLD context is deliberately independent of forecast inference.
const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const count = v => Number.isInteger(v) && v >= 0;
const dateLabel = value => new Intl.DateTimeFormat('en-GB',{day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(value+'T12:00:00Z'));
const utcLabel = value => new Intl.DateTimeFormat('en-GB',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',timeZone:'UTC'}).format(new Date(value))+' UTC';
export function validateDfld(data){
 if(data?.schemaVersion!==2||data.sourceTimezone!=='Europe/Berlin'||!Array.isArray(data.days)||!data.days.length)throw Error('Unsupported DFLD snapshot');
 const dates=new Set();
 for(const d of data.days){
  if(!/^\d{4}-\d{2}-\d{2}$/.test(d.date)||dates.has(d.date)||d.directionBins?.length!==48)throw Error('Incomplete DFLD day');
  dates.add(d.date);
  if(d.movementCoverage&&![d.totalMovements,d.rwy18Departures,d.departures,d.arrivals].every(count))throw Error('Invalid DFLD totals');
  d.directionBins.forEach((b,i)=>{
   if(b.sourceTime!==`${String(Math.floor(i/2)).padStart(2,'0')}:${i%2?'30':'00'}`||![null,'07','25'].includes(b.operatingDirection)||!(b.windDirectionDeg===null||Number.isFinite(b.windDirectionDeg)&&b.windDirectionDeg>=0&&b.windDirectionDeg<=360))throw Error('Invalid DFLD direction bin');
  });
  if(d.movementCoverage){
  if(d.hourlyMovements?.length!==24)throw Error('Incomplete movements');
  d.hourlyMovements.forEach((h,i)=>{
   if(h.sourceTime!==`${String(i).padStart(2,'0')}:00`||![h.departures,h.arrivals,h.rwy18Departures,h.arrivals07,h.arrivals25,h.otherArrivals].every(count)||h.rwy18Departures>h.departures||h.arrivals07+h.arrivals25+h.otherArrivals!==h.arrivals||h.rwy18Closed!==null)throw Error('Invalid DFLD movement counts');
  });
  if(d.hourlyMovements.reduce((s,h)=>s+h.arrivals+h.departures,0)!==d.totalMovements||d.hourlyMovements.reduce((s,h)=>s+h.rwy18Departures,0)!==d.rwy18Departures||d.arrivals+d.departures!==d.totalMovements)throw Error('DFLD totals do not reconcile');
  }else if([d.hourlyMovements,d.runways,d.totalMovements,d.rwy18Departures,d.departures,d.arrivals].some(v=>v!==null))throw Error('Unimported movements must stay unknown');
  for(const b of d.directionBins){if(d.dstTransitionExcluded){if(b.timeUtc!==null||b.eligibleForModel!==false)throw Error('Ambiguous DST time');}else if(b.eligibleForModel&&(!Number.isFinite(Date.parse(b.timeUtc))||b.operatingDirection===null))throw Error('Invalid UTC target');}
  for(const source of Object.values(d.sources)){if(new URL(source.url).hostname!=='www.dfld.de'||!Number.isFinite(Date.parse(source.retrievedAt)))throw Error('Invalid DFLD provenance');}
 }
 return data;
}
export function observedHour(day,hour){
 const movement=day.hourlyMovements?.[hour]??null,bins=day.directionBins.slice(hour*2,hour*2+2);
 return {movement,bins,rwy18Status:!movement?'Movement detail not imported':movement.rwy18Departures?'Departures recorded':'No recorded departures',closureStatus:'Unknown'};
}
export async function initDfld(){
 const root=document.getElementById('dfld-content'),summary=document.getElementById('dfld-summary');
 try{
  const response=await fetch('data/dfld.json');if(!response.ok)throw Error('Snapshot unavailable');
  const data=validateDfld(await response.json());let dayIndex=data.days.length-1,selectedHour=10;
  summary.textContent=`Six months of DFLD · ${data.days.length} days · ${data.days.reduce((n,d)=>n+d.directionCoverageBins,0).toLocaleString()} reports · now used by the direction model`;
  root.innerHTML=`<article class="panel dfld-intro"><div><div class="eyebrow">SIX MONTHS OF REPORTED OPERATIONS</div><h2>History that improves the forecast.</h2><p>30 April–29 October 2026: explore 8,784 half-hour direction reports and their wind context. Direction labels now train and test the model. Movement detail is available for 27–29 October only.</p></div><label>Observation date<input type="date" id="dfld-day" aria-label="DFLD observation date" min="${data.days[0].date}" max="${data.days.at(-1).date}" value="${data.days.at(-1).date}"></label></article>
  <div class="dfld-provenance"><span id="dfld-retrieved"></span><span>Frankfurt local time · empirically verified</span><span><a href="data/dfld-time-audit.json" target="_blank">Clock audit: 240 / 240 matches ↗</a></span></div>
  <div class="dfld-kpis" id="dfld-kpis"></div>
  <article class="panel dfld-directions"><div class="panel-heading"><div><div class="eyebrow">30-MINUTE REPORTS</div><h2>Operating direction through the day</h2></div><div class="dfld-legend"><span><i class="west"></i>25 · west</span><span><i class="east"></i>07 · east</span></div></div><div id="dfld-direction-strip" class="dfld-direction-strip"></div><div class="dfld-axis"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span></div><p id="dfld-change" class="dfld-copy"></p></article>
  <div class="dfld-grid"><article class="panel dfld-activity"><div class="panel-heading"><div><div class="eyebrow">SELECT AN HOUR TO INSPECT</div><h2>Recorded runway activity</h2></div></div><div class="dfld-legend dfld-chart-key"><span><i class="arrivals"></i>Arrivals</span><span><i class="departures"></i>Other departures</span><span><i class="rwy18"></i>RWY 18 departures</span></div><div id="dfld-chart" class="dfld-chart"></div><p class="dfld-copy">Column height = recorded movements per source-clock hour. Empty hours show no recorded activity; they do not establish a closure.</p></article><article class="panel dfld-hour"><div class="eyebrow">SELECTED HISTORICAL HOUR</div><h2 id="dfld-hour-title"></h2><div id="dfld-hour-detail"></div></article></div>
  <details class="panel dfld-table"><summary>Runway totals &amp; downloadable records</summary><div class="table-scroll"><table><thead><tr><th>Runway</th><th>Departures</th><th>Arrivals</th><th>Total</th></tr></thead><tbody id="dfld-runways"></tbody></table></div><div class="audit-links"><a href="data/dfld.json" download>Six-month history + provenance JSON ↓</a><a href="data/dfld-direction.csv" download>Direction history CSV ↓</a></div></details>
  <article class="panel dfld-limits"><h2>How this evidence is used</h2><p>DFLD describes Frankfurt’s direction history since March 2004 as based on Fraport data. This import uses its reported direction rows, not the separate wind-rule calculation. Wind bearings come from its METAR-based statistics, displayed in 30° steps; 0° can include variable wind. Training uses original METAR wind observations and excludes variable directions.</p><p><strong>RWY 18 closure status remains unknown.</strong> Recorded departures demonstrate use at those movement times. A zero count cannot establish whether departures were possible. A changed direction bin gives a 30-minute report, not an exact switch instant.</p><p>These direction reports train and test a separate classifier. April–August is training; September contains validation and 72-hour split gaps; 30 September–29 October is held-out testing. DFLD is a target only, never a forecast-time feature: publication timestamps are unavailable. The Europe/Berlin clock is supported by 240 exact METAR matches across summer and winter, rather than an explicit provider declaration. The ambiguous 25 October DST date is excluded from model joins. RWY 18 coefficients and both alert modes are unchanged. Saved history does not update with weather refresh.</p><div id="dfld-source-links" class="dfld-source-links"></div><p class="dfld-small">Source: Deutscher Fluglärmdienst e.V. · Selected factual values and derived aggregates only. Raw pages, flight identifiers and DFLD graphics are not republished. <a href="https://www.dfld.de/DFLDimprint.php?L=G" target="_blank" rel="noopener">DFLD reuse notice ↗</a></p></article>`;
  function render(){
   const d=data.days[dayIndex],latest=Object.values(d.sources).map(s=>s.retrievedAt).sort().at(-1);
   document.getElementById('dfld-retrieved').textContent=`Retrieved ${utcLabel(latest)} · observed ${dateLabel(d.date)}`;
   const east=d.directionBins.filter(b=>b.operatingDirection==='07').length,west=d.directionBins.filter(b=>b.operatingDirection==='25').length;
   document.getElementById('dfld-kpis').innerHTML=[['RECORDED MOVEMENTS',d.totalMovements?.toLocaleString()??'—',d.movementCoverage?`${d.arrivals} arrivals · ${d.departures} departures`:'Movement detail not imported'],['RWY 18 DEPARTURES',d.rwy18Departures??'—','Closure status remains unknown'],['DIRECTION REPORTS',`${west/2}h / ${east/2}h`,'25 west / 07 east · source-clock bins'],['WITHIN-DAY CHANGES',d.directionChanges.length,d.dstTransitionExcluded?'DST date excluded from model joins':`${d.directionCoverageBins} / 48 direction bins available`]].map(([label,value,caption])=>`<article class="panel dfld-kpi"><span>${label}</span><strong>${value}</strong><p>${caption}</p></article>`).join('');
   document.getElementById('dfld-direction-strip').innerHTML=d.directionBins.map((b,i)=>`<button class="${b.operatingDirection==='25'?'west':b.operatingDirection==='07'?'east':'unknown'}" data-dfld-hour="${Math.floor(i/2)}" aria-label="${b.sourceTime}–${b.sourceEndTime}: direction ${b.operatingDirection??'unknown'}" title="${b.sourceTime}–${b.sourceEndTime} · OD ${b.operatingDirection??'unknown'}">${i%4===0?b.operatingDirection??'?':''}</button>`).join('');
   document.getElementById('dfld-change').textContent=d.directionChanges.length?d.directionChanges.map(c=>`${c.from} → ${c.to}: first changed bin ${c.sourceTime}–${c.sourceEndTime} (DFLD displayed time).`).join(' '):'No within-day change between consecutive known direction bins.';
   const max=Math.max(1,...(d.hourlyMovements??[]).map(h=>h.arrivals+h.departures));
   document.getElementById('dfld-chart').innerHTML=!d.movementCoverage?'<p class="dfld-empty">Movement detail not imported for this date.<br>Select 27–29 October for runway counts. Direction history is available above.</p>':d.hourlyMovements.map((h,i)=>`<button class="dfld-hour-bar" data-dfld-hour="${i}" aria-label="${h.sourceTime}: ${h?.arrivals??'—'} arrivals, ${h?.departures??'—'} departures, including ${h?.rwy18Departures??'—'} on runway 18"><span class="dfld-column"><i class="rwy18" style="height:${100*h.rwy18Departures/max}%"></i><i class="departures" style="height:${100*(h.departures-h.rwy18Departures)/max}%"></i><i class="arrivals" style="height:${100*h.arrivals/max}%"></i></span><span class="dfld-hour-tick">${i%3===0?String(i).padStart(2,'0'):''}</span></button>`).join('');
   document.getElementById('dfld-runways').innerHTML=!d.movementCoverage?'<tr><td colspan="4">Movement detail not imported</td></tr>':d.runways.map(r=>`<tr><td>${r.runway==='unknown'?'Unassigned':esc(r.runway)}</td><td>${r.departures}</td><td>${r.arrivals}</td><td>${r.departures+r.arrivals}</td></tr>`).join('');
   document.getElementById('dfld-source-links').innerHTML=`<a href="${esc(d.sources.directionAndWind.url)}" target="_blank" rel="noopener">DFLD direction &amp; wind ↗</a>${d.sources.movements?`<a href="${esc(d.sources.movements.url)}" target="_blank" rel="noopener">DFLD movement records ↗</a>`:''}<a href="https://www.dfld.de/Mess/Language/MessHelpG.html" target="_blank" rel="noopener">Source methodology ↗</a>`;
   renderHour();
  }
  function renderHour(){
   const d=data.days[dayIndex],{movement:h,bins,rwy18Status}=observedHour(d,selectedHour);
   document.getElementById('dfld-hour-title').textContent=`${String(selectedHour).padStart(2,'0')}:00–${String(selectedHour+1).padStart(2,'0')}:00`;
   document.getElementById('dfld-hour-detail').innerHTML=`<p class="dfld-small">${dateLabel(d.date)} · DFLD displayed time</p><div class="dfld-hour-numbers"><div><strong>${h?.arrivals??'—'}</strong><span>arrivals</span></div><div><strong>${h?.departures??'—'}</strong><span>departures</span></div><div><strong>${h?.rwy18Departures??'—'}</strong><span>RWY 18</span></div></div><p class="dfld-use">${rwy18Status}<small>RWY 18 closure status: unknown</small></p><div class="dfld-bin-detail">${bins.map(b=>`<div><span>${b.sourceTime}–${b.sourceEndTime}</span><strong>OD ${b.operatingDirection??'unknown'}</strong><span>Wind bearing ${b.windDirectionDeg===null?'unavailable':b.windDirectionDeg===0?'0° / variable':b.windDirectionDeg+'°'}<small>30° display bins · speed unavailable</small></span></div>`).join('')}</div><p class="dfld-small">Arrival runway directions: ${h?.arrivals25??'—'} west / ${h?.arrivals07??'—'} east${h?.otherArrivals?` / ${h.otherArrivals} other`:''}. Movement directions are counts, not an inferred airport-wide state.</p>`;
   root.querySelectorAll('[data-dfld-hour]').forEach(b=>{const on=Number(b.dataset.dfldHour)===selectedHour;b.classList.toggle('selected',on);b.setAttribute('aria-pressed',String(on));});
  }
  root.addEventListener('click',e=>{const b=e.target.closest('[data-dfld-hour]');if(b){selectedHour=Number(b.dataset.dfldHour);renderHour();}});
  document.getElementById('dfld-day').addEventListener('change',e=>{const i=data.days.findIndex(d=>d.date===e.target.value);if(i<0){e.target.value=data.days[dayIndex].date;return;}dayIndex=i;render();});
  render();
 }catch(error){
  summary.textContent='DFLD history unavailable';
  root.innerHTML='<article class="panel dfld-limits"><h2>DFLD history could not load</h2><p>The forecast remains available. No observations have been fabricated.</p><a href="https://www.dfld.de/Mess/Language/MessR001.php" target="_blank" rel="noopener">Open DFLD Frankfurt ↗</a></article>';
  console.warn('DFLD context unavailable:',error.message);
 }
}
