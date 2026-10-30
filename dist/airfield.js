import {windComponents} from './inference.js';

const escape = value => String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// Local equirectangular projection; equal metre scale, true north up.
const METRES_PER_DEGREE = 111320, SCALE = 0.075;
export function project([lon,lat]) {
  return [42 + (lon - 8.49) * METRES_PER_DEGREE * Math.cos(50.03 * Math.PI / 180) * SCALE,
    28 + (50.058 - lat) * METRES_PER_DEGREE * SCALE];
}
const xy = p => project(p).map(v=>v.toFixed(2)).join(' ');
const interpolate = (a,b,f) => a.map((n,i)=>n+(b[i]-n)*f);
const label = (x,y,text,cls='',anchor='middle') => `<text x="${x}" y="${y}" text-anchor="${anchor}" class="map-label ${cls}">${escape(text)}</text>`;

export function airfieldSVG(geo,row) {
  const direction = row.p07 >= 0.5 ? '07' : '25', east = direction === '07';
  const color = east ? '#3878bd' : '#548b39';
  const wind = windComponents(row.windSpeed,row.windDirection,180,row.windGust);
  const restricted = wind.tailwind >= 15 || wind.crosswindGust > 40;
  const parallelRestricted = windComponents(row.windSpeed,row.windDirection,70,row.windGust).crosswindGust > 40;
  let svg = `<svg viewBox="0 0 700 570" role="img" aria-labelledby="airfield-title airfield-description"><title id="airfield-title">Frankfurt Airport geographic airfield map. Forecast direction ${direction}.</title><desc id="airfield-description">Four runways at their geographic coordinates. Northwest runway for landings only. Runway 18 permits southbound departures only and ${restricted?'exceeds':'is within'} challenge wind limits. Terminal 1 and 3 footprints and Terminal 2 location. True north up. Not for navigation.</desc><defs><pattern id="airfield-grid" width="75" height="75" patternUnits="userSpaceOnUse"><path d="M75 0H0V75" stroke="#dce5df" stroke-width="0.6" fill="none"/></pattern><marker id="flow-arrow" markerWidth="7" markerHeight="7" refX="5" refY="3.5" orient="auto"><path d="M0 0L7 3.5L0 7Z" fill="${color}"/></marker><marker id="south-arrow" markerWidth="7" markerHeight="7" refX="5" refY="3.5" orient="auto"><path d="M0 0L7 3.5L0 7Z" fill="#548b39"/></marker></defs><rect width="700" height="570" fill="#f2f6f2"/><rect width="700" height="570" fill="url(#airfield-grid)"/>`;
  // Terminal polygons are the source footprints; no invented taxiway network.
  for (const f of geo.features.filter(f=>f.geometry.type==='Polygon')) {
    svg += `<path d="${f.geometry.coordinates.map(r=>`M${r.map(xy).join('L')}Z`).join(' ')}" class="terminal-footprint"><title>${escape(f.properties.name)} · OpenStreetMap</title></path>`;
  }
  for (const f of geo.features.filter(f=>f.properties.kind==='runway')) {
    const [a,b] = f.geometry.coordinates.map(project), is18 = f.id === 'runway-18';
    const limited = is18 ? restricted : parallelRestricted;
    const stroke = limited ? '#b76e3d' : '#667b80';
    const path = `M${a.join(' ')}L${b.join(' ')}`;
    const width = Math.max(5,f.properties.widthM*SCALE);
    const mid = interpolate(a,b,0.5), angle = Math.atan2(b[1]-a[1],b[0]-a[0])*180/Math.PI;
    svg += `<g><title>${escape(f.properties.name)} · ${f.properties.lengthM} m · ${escape(f.properties.usage)}</title><path d="${path}" stroke="white" stroke-width="${width+5}"/><path d="${path}" stroke="${stroke}" stroke-width="${width}"/><path d="${path}" stroke="#fafffc" stroke-width="0.8" stroke-dasharray="6 5"/>`;
    if (is18) {
      svg += label(a[0]-16,a[1]-8,'18','runway-end');
      svg += `<g transform="translate(${mid[0]-23} ${mid[1]}) rotate(-90)">${label(0,0,'WEST · 4,000 m','runway-name')}</g>`;
      svg += label(mid[0]+25,mid[1]+38,'SOUTHBOUND ONLY','map-small','start');
    } else {
      const [low,high] = f.properties.name.split(' / ');
      svg += label(a[0]-8,a[1]+13,low,'runway-end','end')+label(b[0]+9,b[1]+3,high,'runway-end','start');
      const name = low==='07L'?'NORTHWEST · 2,800 m':low==='07C'?'CENTRE · 4,000 m':'SOUTH · 4,000 m';
      const offset = low==='07R'?21:-13;
      svg += `<g transform="translate(${mid[0]} ${mid[1]}) rotate(${angle})">${label(0,offset,name,'runway-name')}</g>`;
    }
    if (limited) {
      svg += `<g transform="translate(${mid[0]} ${mid[1]})"><circle r="12" fill="#fff3e6" stroke="#b76e3d"/><path d="M-5 -5L5 5M-5 5L5 -5" stroke="#b76e3d" stroke-width="2"/></g>`;
    } else {
      const start = interpolate(a,b,is18||east?0.25:0.75), end = interpolate(a,b,is18||east?0.75:0.25);
      const dx = is18?17:0, dy = is18?0:0;
      svg += `<path d="M${start[0]+dx} ${start[1]+dy}L${end[0]+dx} ${end[1]+dy}" stroke="${is18?'#548b39':color}" stroke-width="2.6" fill="none" marker-end="url(#${is18?'south-arrow':'flow-arrow'})"/>`;
    }
    svg += '</g>';
  }
  const t1 = project([8.568,50.052]), t2 = project([8.586,50.0535]), t3 = project([8.578,50.0265]);
  svg += label(t1[0],t1[1],'TERMINAL 1','terminal-label');
  svg += label(t2[0],t2[1],'T2 · CLOSED*','terminal-label inactive');
  for(const f of geo.features.filter(f=>f.geometry.type==='Point')) {const [x,y]=project(f.geometry.coordinates);svg+=`<circle cx="${x}" cy="${y}" r="3" fill="#a3aeb4"/>`;}
  svg += label(t3[0],t3[1],'TERMINAL 3','terminal-label');
  svg += `<g transform="translate(41 46)"><path d="M0 28V-5M-5 3L0-7L5 3" stroke="#526b63" stroke-width="2" fill="none"/>${label(0,-15,'N','runway-end')}</g>`;
  svg += label(94,27,'TAUNUS · N/NW, OFF MAP','map-small','start');
  svg += `<g transform="translate(62 521)"><path d="M0-5V0H75V-5M37.5 0V-4" stroke="#62766d" fill="none" stroke-width="1.5"/>${label(0,17,'0','map-small')}${label(75,17,'1 km','map-small')}</g>`;
  svg += `<g transform="translate(528 408)"><circle r="40" fill="white" stroke="#d7e1dc"/><g transform="rotate(${row.windDirection})"><path d="M0-26V22M-6 13L0 24L6 13" stroke="#496879" stroke-width="2.5" fill="none"/></g>${label(0,-54,'WIND FLOW','map-small')}${label(0,62,`FROM ${Math.round(row.windDirection)}° · ${row.windSpeed.toFixed(1)} kt`,'runway-name')}${label(0,82,`OD ${direction} · ${east?'EASTBOUND':'WESTBOUND'}`,'runway-name')}</g>`;
  svg += label(254,544,'GEOGRAPHIC CONTEXT · NOT FOR NAVIGATION','map-small','start');
  return svg+'</svg>';
}
