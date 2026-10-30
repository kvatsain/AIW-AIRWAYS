import {project} from './airfield.js';
import {windComponents} from './inference.js';

// Orthographic XYZ projection: actual footprint coordinates, illustrative heights.
// No external renderer, map tiles, or GPU requirement. Wind is one forecast point.
const rad = d => d*Math.PI/180;
const safe = v => String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fixed = n => Number(n).toFixed(2);
const groundCorners = [[30,20],[670,20],[670,550],[30,550]];
const mix = (a,b,t) => a.map((n,i)=>n+(b[i]-n)*t);
const groundCache = new WeakMap();

export function camera3D(yaw=-16,elevation=48) {
  const c=Math.cos(rad(yaw)),s=Math.sin(rad(yaw)),p=Math.sin(rad(elevation)),q=Math.cos(rad(elevation));
  const rotate=([x,y])=>[c*(x-350)-s*(y-285),s*(x-350)+c*(y-285)];
  const corners=groundCorners.map(rotate);
  const span=i=>Math.max(...corners.map(p=>p[i]))-Math.min(...corners.map(p=>p[i]));
  const scale=Math.min(820/span(0),500/(span(1)*p));
  return {
    point:([x,y],z=0)=>{const [u,v]=rotate([x,y]);return [470+u*scale,330+v*p*scale-z*q*scale];},
    depth:pt=>rotate(pt)[1], scale,
  };
}
export function windFlowVector(fromDegrees) {
  return [-Math.sin(rad(fromDegrees)),Math.cos(rad(fromDegrees))];
}
function polygons(g) { return g.type==='Polygon'?[g.coordinates]:g.type==='MultiPolygon'?g.coordinates:[]; }
function lines(g) { return g.type==='LineString'?[g.coordinates]:g.type==='MultiLineString'?g.coordinates:polygons(g).flat(); }
function pathOf(coords,camera,z=0,close=false) {
  return 'M'+coords.map(p=>camera.point(p,z).map(fixed).join(' ')).join('L')+(close?'Z':'');
}
function geoPath(g,camera,z=0) {
  return lines(g).map(line=>pathOf(line.map(project),camera,z,!g.type.includes('LineString'))).join(' ');
}
function worldRing(g) { return polygons(g).map(poly=>poly.map(r=>r.map(project))); }
function label(camera,position,text,cls='',z=0,anchor='middle') {
  const [x,y]=camera.point(position,z);return `<text x="${fixed(x)}" y="${fixed(y)}" text-anchor="${anchor}" class="scene-label ${cls}">${safe(text)}</text>`;
}
function inside(point,ring) {
  let hit=false;const [x,y]=point;
  for(let i=0,j=ring.length-1;i<ring.length;j=i++){
    const [xi,yi]=ring[i],[xj,yj]=ring[j];
    if((yi>y)!==(yj>y)&&x<(xj-xi)*(y-yi)/(yj-yi)+xi)hit=!hit;
  }return hit;
}
function staticScene(geo,context,camera,yaw,elevation) {
  const key=`${yaw}:${elevation}`;
  let cache=groundCache.get(geo);if(!cache){cache=new Map();groundCache.set(geo,cache);}
  const cached=cache.get(key);if(cached&&cached.context===context)return cached;
  const features=context?.features??[];
  const colors={'forest':'#244f43','water':'#36788a','airport-boundary':'#627c60','cargo':'#768a7d','apron':'#a3afa3'};
  let ground='';
  for(const kind of ['forest','water','airport-boundary','cargo','apron','motorway','taxiway']){
    for(const f of features.filter(f=>f.properties.kind===kind)){
      const d=geoPath(f.geometry,camera);
      if(kind==='motorway') ground+=`<path d="${d}" fill="none" stroke="#c4b38b" stroke-opacity=".75" stroke-width="${f.properties.highway==='motorway'?2.5:1.2}"/>`;
      else if(kind==='taxiway') ground+=`<path d="${d}" fill="none" stroke="#d0d7bd" stroke-opacity=".72" stroke-width="1.6" stroke-linejoin="round"/>`;
      else ground+=`<path d="${d}" fill="${colors[kind]}" fill-rule="evenodd" stroke="${colors[kind]}" stroke-width=".5"/>`;
    }
  }
  // Raised volumes follow real source polygons. Districts remain flat.
  const buildings=[...features.filter(f=>f.properties.kind==='airport-building'),...geo.features.filter(f=>f.properties.kind==='terminal'&&f.geometry.type==='Polygon')];
  const volumes=[];let shadows='';
  for(const f of buildings){
    const terminal=f.properties.kind==='terminal',height=terminal?18:f.properties.building==='hangar'?15:10;
    for(const poly of worldRing(f.geometry)){
      const ring=poly[0];const centre=ring.reduce((a,p)=>[a[0]+p[0]/ring.length,a[1]+p[1]/ring.length],[0,0]);
      if(centre[0]<30||centre[0]>670||centre[1]<20||centre[1]>550)continue;
      shadows+=`<path d="${pathOf(ring.map(([x,y])=>[x+height*.55,y+height*.65]),camera,0,true)}" fill="#102b29" opacity=".24"/>`;
      let shape='';
      for(const r of poly){for(let i=0;i<r.length-1;i++){
        const a=r[i],b=r[i+1],corners=[camera.point(a),camera.point(b),camera.point(b,height),camera.point(a,height)];
        const lit=(b[0]-a[0])*.5+(b[1]-a[1])*.8>0;
        shape+=`<path d="M${corners.map(p=>p.map(fixed).join(' ')).join('L')}Z" fill="${lit?'#819a91':'#496c69'}" stroke="#385955" stroke-width=".25"/>`;
      }}
      shape+=`<path d="${poly.map(r=>pathOf(r,camera,height,true)).join(' ')}" fill="${terminal?'#e4eadb':'#bccbbd'}" stroke="${terminal?'#f5f6dc':'#d4ddce'}" stroke-width=".6" fill-rule="evenodd"><title>${safe(f.properties.name||'Mapped airport building')}; illustrative height</title></path>`;
      volumes.push({depth:camera.depth(centre),shape});
    }
  }
  // Small woodland canopies are sampled only inside mapped forest polygons.
  const forests=features.filter(f=>f.properties.kind==='forest').flatMap(f=>worldRing(f.geometry));
  const airport=features.filter(f=>f.properties.kind==='airport-boundary').flatMap(f=>worldRing(f.geometry));
  for(let x=45;x<660;x+=24)for(let y=36;y<540;y+=24){
    const pt=[x+Math.sin(x+y)*7,y+Math.cos(x-y)*7];
    if(!forests.some(p=>inside(pt,p[0])&&!p.slice(1).some(r=>inside(pt,r)))||airport.some(p=>inside(pt,p[0])))continue;
    const [u,v]=camera.point(pt,5),size=3.8*camera.scale;
    volumes.push({depth:camera.depth(pt),shape:`<ellipse cx="${fixed(u)}" cy="${fixed(v+size*.65)}" rx="${fixed(size*1.05)}" ry="${fixed(size*.55)}" fill="#102e29" opacity=".35"/><path d="M${fixed(u-size)} ${fixed(v+size*.5)}L${fixed(u)} ${fixed(v-size*1.4)}L${fixed(u+size)} ${fixed(v+size*.5)}Z" fill="#387260"/><path d="M${fixed(u)} ${fixed(v-size*1.4)}L${fixed(u+size)} ${fixed(v+size*.5)}L${fixed(u)} ${fixed(v+size*.7)}Z" fill="#285b50"/>`});
  }
  const result={context,ground,shadows,volumes:volumes.sort((a,b)=>a.depth-b.depth).map(v=>v.shape).join('')};
  if(cache.size>24)cache.clear();cache.set(key,result);return result;
}

export function airfield3DSVG(geo,row,context,options={}) {
  const {yaw=-16,elevation=48,wind=true,selected='runway-18'}=options;
  const camera=camera3D(yaw,elevation),base=staticScene(geo,context,camera,yaw,elevation);
  const direction=row.p07>=.5?'07':'25',east=direction==='07';
  const valid=[row.windSpeed,row.windDirection,row.windGust??row.windSpeed].every(Number.isFinite);
  const r18=valid?windComponents(row.windSpeed,row.windDirection,180,row.windGust??row.windSpeed):null;
  const parallels=valid?windComponents(row.windSpeed,row.windDirection,70,row.windGust??row.windSpeed):null;
  const closed18=r18&&(r18.tailwind>=15||r18.crosswindGust>40),closedParallel=parallels&&parallels.crosswindGust>40;
  const tile=pathOf(groundCorners,camera,0,true),bottom=pathOf(groundCorners,camera,-20,true);
  let svg=`<svg class="airfield-scene" viewBox="0 0 940 650" role="img" aria-labelledby="scene-title scene-description"><title id="scene-title">Frankfurt Airport 3D outlook. Forecast direction ${direction}.</title><desc id="scene-description">Mapped airport footprints with illustrative building heights. Cyan arrows show wind moving away from its source direction. Lime arrows show forecast runway direction, not actual aircraft. ${closed18?'Runway 18 exceeds challenge wind limits.':'Runway 18 wind limits are shown in the inspector.'} Use the runway buttons for surface wind components.</desc><defs><linearGradient id="scene-sky" x2=".9" y2="1"><stop stop-color="#102932"/><stop offset="1" stop-color="#1d4541"/></linearGradient><radialGradient id="scene-halo"><stop stop-color="#6cae8b" stop-opacity=".28"/><stop offset="1" stop-color="#183c36" stop-opacity="0"/></radialGradient><filter id="scene-shadow" x="-30%" y="-50%" width="160%" height="210%"><feGaussianBlur stdDeviation="13"/></filter><clipPath id="scene-ground-clip"><path d="${tile}"/></clipPath><clipPath id="scene-wind-clip"><path d="${pathOf(groundCorners,camera,32,true)}"/></clipPath><marker id="scene-flight" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0 1L7 4L0 7L2 4Z" fill="#d3f58d"/></marker><marker id="scene-wind" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto"><path d="M1 1L8 4.5L1 8" fill="none" stroke="#86dfef" stroke-width="1.2"/></marker></defs><rect width="940" height="650" rx="16" fill="url(#scene-sky)"/><ellipse cx="475" cy="400" rx="450" ry="260" fill="url(#scene-halo)"/><path d="${bottom}" transform="translate(0 20)" fill="#061e20" opacity=".6" filter="url(#scene-shadow)"/>`;
  for(let i=0;i<4;i++){
    const a=groundCorners[i],b=groundCorners[(i+1)%4];
    svg+=`<path d="M${[camera.point(a),camera.point(b),camera.point(b,-20),camera.point(a,-20)].map(p=>p.map(fixed).join(' ')).join('L')}Z" fill="${i%2?'#244a44':'#345e4e'}" stroke="#3f6f58" stroke-width=".7"/>`;
  }
  svg+=`<path d="${tile}" fill="#2d5949" stroke="#7a9e79" stroke-width="1"/><g clip-path="url(#scene-ground-clip)">${base.ground}${base.shadows}`;
  for(const f of geo.features.filter(f=>f.properties.kind==='runway')){
    const points=f.geometry.coordinates.map(project),is18=f.id==='runway-18',restricted=is18?closed18:closedParallel;
    const d=pathOf(points,camera,.8),width=Math.max(5,f.properties.widthM*.075*camera.scale);
    if(f.id===selected)svg+=`<path d="${d}" stroke="#ecedaf" stroke-width="${width+11}" opacity=".16"/>`;
    svg+=`<path d="${d}" stroke="#c5cdb1" stroke-width="${width+2}"/><path d="${d}" stroke="${restricted?'#a26843':'#213f43'}" stroke-width="${width}"/><path d="${d}" stroke="#dae4cf" stroke-width=".8" stroke-dasharray="5 4"/>`;
  }
  svg+=`${base.volumes}</g>`;
  if(wind&&valid&&row.windSpeed>=.5){
    const flow=windFlowVector(row.windDirection),perp=[-flow[1],flow[0]],duration=Math.max(1.3,6-row.windSpeed/8);
    svg+='<g clip-path="url(#scene-wind-clip)" class="wind-streams">';
    for(let i=-3;i<=3;i++){
      const centre=[350+perp[0]*i*85,285+perp[1]*i*85],a=centre.map((n,j)=>n-flow[j]*470),b=centre.map((n,j)=>n+flow[j]*470);
      svg+=`<path d="${pathOf([a,b],camera,32)}" fill="none" stroke="#8fe8f1" stroke-opacity=".1" stroke-width="1.6"/><path class="wind-particle" style="animation-duration:${duration}s;animation-delay:${i*.28}s" d="${pathOf([a,b],camera,32)}" fill="none" stroke="#8ce7ed" stroke-opacity=".6" stroke-width="2" stroke-linecap="round" stroke-dasharray="22 130"/>`;
      const tip=mix(a,b,.55);svg+=`<path d="${pathOf([mix(a,b,.49),tip],camera,32)}" fill="none" stroke="#86dfef" stroke-opacity=".72" stroke-width="1.4" marker-end="url(#scene-wind)"/>`;
    }svg+='</g>';
  }
  for(const f of geo.features.filter(f=>f.properties.kind==='runway')){
    const [a,b]=f.geometry.coordinates.map(project),is18=f.id==='runway-18',restricted=is18?closed18:closedParallel;
    const start=mix(a,b,(is18||east) ? .28 : .72),end=mix(a,b,(is18||east) ? .72 : .28);
    if(!restricted&&valid)svg+=`<path d="${pathOf([start,end],camera,3)}" stroke="#d3f58d" stroke-width="3.4" fill="none" marker-end="url(#scene-flight)"/>`;
    else if(restricted){const [x,y]=camera.point(mix(a,b,.5),5);svg+=`<g transform="translate(${x} ${y})"><circle r="10" fill="#efb17c"/><path d="M-4-4L4 4M-4 4L4-4" stroke="#4a3027" stroke-width="2"/></g>`;}
    const mid=mix(a,b,.5),[mx,my]=camera.point(mid,15);
    const name=is18?'18 · SOUTH ONLY':f.properties.name;
    svg+=`<g class="scene-runway-tag ${f.id===selected?'active':''}" data-scene-runway="${safe(f.id)}"><title>${safe(f.properties.usage)}</title><rect x="${mx-53}" y="${my-17}" width="106" height="24" rx="6"/><text x="${mx}" y="${my-1}" text-anchor="middle">${safe(name)}</text></g>`;
  }
  for(const [coord,name,z] of [[[8.566,50.053],'TERMINAL 1',32],[[8.587,50.0545],'T2 · CLOSED*',19],[[8.578,50.0275],'TERMINAL 3',31],[[8.56,50.019],'CARGO CITY SOUTH',2]])svg+=label(camera,project(coord),name,name.startsWith('CARGO')?'scene-context':'scene-terminal',z);
  const anchor=[100,475],n=camera.point([100,425]),a=camera.point(anchor),e=camera.point([150,475]);
  svg+=`<g class="scene-compass"><path d="M${n.join(' ')}L${a.join(' ')}L${e.join(' ')}" fill="none" stroke="#abc9bb" stroke-width="1.5"/>${label(camera,[100,413],'N','scene-north')}${label(camera,[163,475],'E','scene-context')}</g>`;
  svg+=`<text x="34" y="38" class="scene-kicker">FRA / SPATIAL WIND OUTLOOK</text><text x="34" y="60" class="scene-subtitle">Mapped airfield · illustrative heights</text><g transform="translate(712 23)"><rect width="195" height="65" rx="11" fill="#0c262b" fill-opacity=".86" stroke="#47736c"/><text x="15" y="23" class="scene-kicker">WIND FROM ${valid?Math.round(row.windDirection)+'°':'—'}</text><text x="15" y="47" class="scene-wind-value">${valid?row.windSpeed.toFixed(1):'—'} kt <tspan class="scene-gust"> / gust ${valid?(row.windGust??row.windSpeed).toFixed(1):'—'}</tspan></text></g><text x="34" y="624" class="scene-subtitle">Arrows show forecast wind and runway flow. No live aircraft positions.</text></svg>`;
  return svg;
}
