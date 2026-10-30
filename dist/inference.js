// Portable model inference. Every wind direction is degrees true FROM; speeds knots.
let configuredModel = null;
export function setModel(model) { configuredModel = model; }
export async function loadModel(url = './data/model.json') {
  const response = await fetch(url); if (!response.ok) throw new Error('Model could not be loaded');
  configuredModel = await response.json(); return configuredModel;
}
const radians = n => n * Math.PI / 180;
const sigmoid = x => 1 / (1 + Math.exp(-Math.max(-35, Math.min(35, x))));
const utcDate = time => new Date(/[Z]|[+-]\d\d:\d\d$/.test(time) ? time : time + 'Z');
export function windComponents(speed, direction, heading = 180, gust = speed) {
  const a = radians(direction - heading);
  return { headwind: speed * Math.cos(a), tailwind: Math.max(0, -speed * Math.cos(a)), crosswind: Math.abs(speed * Math.sin(a)), crosswindGust: Math.abs(gust * Math.sin(a)) };
}
export function normalizeWeather(hourly) {
  if (hourly.hourly) hourly = hourly.hourly;
  if (Array.isArray(hourly)) return hourly.map(row => ({ ...row }));
  return hourly.time.map((time, i) => ({ time: time.endsWith('Z') ? time : time + 'Z', windSpeed: hourly.wind_speed_10m?.[i], windDirection: hourly.wind_direction_10m?.[i], windGust: hourly.wind_gusts_10m?.[i], temperature: hourly.temperature_2m?.[i], humidity: hourly.relative_humidity_2m?.[i], pressure: hourly.pressure_msl?.[i], precipitation: hourly.precipitation?.[i], cloudCover: hourly.cloud_cover?.[i], windSpeed80m: hourly.wind_speed_80m?.[i], windDirection80m: hourly.wind_direction_80m?.[i] }));
}
export function featuresFor(row, observation, initialOD = '25') {
  const s = row.windSpeed, d = radians(row.windDirection), g = row.windGust ?? s;
  const os = observation.windSpeed, od = radians(observation.windDirection), og = observation.windGust ?? os;
  const date = utcDate(row.time), hour = date.getUTCHours() + date.getUTCMinutes() / 60;
  const doy = Math.floor((Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()) - Date.UTC(date.getUTCFullYear(), 0, 0)) / 86400000);
  return [s * Math.sin(d), s * Math.cos(d), s, g, Math.max(0, s * Math.cos(d)), Math.abs(g * Math.sin(d - Math.PI)), s * Math.cos(d - radians(70)), os * Math.sin(od), os * Math.cos(od), og, observation.eastTrend3h ?? 0, observation.northTrend3h ?? 0, initialOD === '07' ? 1 : 0, Math.sin(hour / 24 * 2 * Math.PI), Math.cos(hour / 24 * 2 * Math.PI), Math.sin(doy / 365.25 * 2 * Math.PI), Math.cos(doy / 365.25 * 2 * Math.PI)];
}
export function inferRow(features, horizonHours, model = configuredModel) {
  if (!model?.models) throw new Error('Load model.json with setModel() or pass model as fourth argument.');
  const nearest = Object.keys(model.models).map(Number).reduce((best, h) => Math.abs(h - horizonHours) < Math.abs(best - horizonHours) ? h : best, 1);
  const spec = model.models[nearest];
  const normalized = features.map((x, i) => (x - spec.mean[i]) / spec.scale[i]);
  const predict = name => { const c = spec.classifiers[name]; return sigmoid(c.intercept + normalized.reduce((sum, x, i) => sum + x * c.weights[i], 0)); };
  const p07 = predict('od07'), pClosed18 = predict('closed18');
  return { pRwy18Open: 1 - pClosed18, pClosed18, p07, p25: 1 - p07, modelHorizonHours: nearest, outOfDistribution: normalized.some(x => Math.abs(x) > 6), closureModelReliable: false };
}
export function predictForecast(weatherHourly, observation = null, initialOD = '25', model = configuredModel, issuedAt = null) {
  const rows = normalizeWeather(weatherHourly); if (!rows.length) return [];
  const valid = rows.filter(r => [r.windSpeed, r.windDirection].every(v => typeof v === 'number' && Number.isFinite(v)));
  if (!valid.length) return rows.map(r => ({ ...r, available: false }));
  const obs = observation && [observation.windSpeed, observation.windDirection].every(v => typeof v === 'number' && Number.isFinite(v)) ? observation : { ...valid[0], source: 'Modeled first-hour fallback; no observation' };
  const originTime = issuedAt ? utcDate(issuedAt).getTime() : obs.time ? utcDate(obs.time).getTime() : utcDate(rows[0].time).getTime() - 3600000;
  let od = initialOD === '07' ? '07' : '25', adverseSince = null, previousTime = null;
  return rows.map((row, index) => {
    if (![row.windSpeed, row.windDirection].every(v => typeof v === 'number' && Number.isFinite(v))) { adverseSince = null; return { ...row, available: false }; }
    const time = utcDate(row.time).getTime(), gust = row.windGust ?? row.windSpeed;
    const lead = Math.max(1, (time - originTime) / 3600000);
    const prediction = inferRow(featuresFor({ ...row, windGust: gust }, obs, initialOD), lead, model);
    const r18 = windComponents(row.windSpeed, row.windDirection, 180, gust);
    if (previousTime !== null && time - previousTime > 3600000) adverseSince = null;
    const directionWind = windComponents(row.windSpeed, row.windDirection, od === '07' ? 70 : 250, gust);
    if (directionWind.tailwind > 1e-9) {
      if (adverseSince === null) adverseSince = time;
      if (directionWind.tailwind >= 10 || time - adverseSince > 30 * 60000) { od = od === '07' ? '25' : '07'; adverseSince = null; }
    } else adverseSince = null;
    previousTime = time;
    const baselineRwy18Open = r18.tailwind < 15 && r18.crosswindGust <= 40;
    return { ...row, windGust: gust, ...prediction, available: true, horizonHours: lead, leadHours: lead, headwind18: r18.headwind, tailwind18: r18.tailwind, crosswind18: r18.crosswind, crosswindGust18: r18.crosswindGust, baselineRwy18Open, baselineOD: od, predictedOD: prediction.p07 >= .5 ? '07' : '25', guardrailTriggered: !baselineRwy18Open, rwy18Status: baselineRwy18Open ? 'Wind limits satisfied' : 'Wind restriction', targetBasis: 'weather-derived proxy', observationSource: obs.source ?? 'provided observation' };
  });
}
