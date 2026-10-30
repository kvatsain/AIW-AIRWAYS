"""User-requested six-month direction archive; one request per calendar month.
Raw pages are private cache; no aircraft identifiers or provider graphics exported.
python scripts/fetch_dfld_history.py --start-date 2026-04-30 --end-date 2026-10-29
"""
import argparse
import csv
import io
import json
import hashlib
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from fetch_dfld import ROOT, BASE, fetch, parse_weather, changes


def build_history(start, end):
    if start < date(2004, 3, 1) or end < start or (end-start).days > 190:
        raise ValueError('Select up to six months of post-March-2004 history')
    if end >= datetime.now(timezone.utc).date():
        raise ValueError('Use completed dates only')
    days, months, missing = [], {}, []
    recent = json.loads((ROOT/'dist/data/dfld.json').read_text(encoding='utf-8'))
    movement_days = {d['date']:d for d in recent['days'] if d.get('hourlyMovements')}
    day = start
    while day <= end:
        month = day.strftime('%Y-%m')
        if month not in months:
            raw = ROOT/f'model/raw/dfld/weather-{month}.html'
            meta = raw.with_suffix('.provenance.json')
            if raw.exists() and meta.exists():
                provenance=json.loads(meta.read_text())
                if hashlib.sha256(raw.read_bytes()).hexdigest()!=provenance['sha256']:
                    raise ValueError('Cached DFLD source hash mismatch: '+month)
                months[month] = raw.read_text(encoding='utf-8',errors='replace'), provenance
            else:
                months[month] = fetch(BASE+f'StatWetter.php?RegNr=1&D={day:%d.%m.%Y}',f'weather-{month}')
            print('Loaded direction month '+month,flush=True)
        page, source = months[month]
        try:
            bins = parse_weather(page,day)
        except ValueError as exc:
            missing.append({'date':str(day),'reason':str(exc)})
            day += timedelta(days=1)
            continue
        zone = ZoneInfo('Europe/Berlin')
        midnight = datetime.combine(day,datetime.min.time(),zone)
        next_midnight = midnight + timedelta(days=1)
        dst_transition = midnight.utcoffset() != next_midnight.utcoffset()
        for b in bins:
            local = datetime.fromisoformat(f'{day}T{b["sourceTime"]}:00').replace(tzinfo=zone)
            b['timeUtc'] = None if dst_transition else local.astimezone(timezone.utc).isoformat().replace('+00:00','Z')
            b['eligibleForModel'] = not dst_transition and b['operatingDirection'] is not None
        d = {'date':str(day),'sources':{'directionAndWind':source},'directionBins':bins,
             'directionChanges':changes(bins),'directionCoverageBins':sum(b['operatingDirection'] is not None for b in bins),
             'dstTransitionExcluded':dst_transition,'movementCoverage':False,
             'hourlyMovements':None,'runways':None,'totalMovements':None,'departures':None,'arrivals':None,'rwy18Departures':None}
        if str(day) in movement_days:
            old=movement_days[str(day)]
            for key in ['hourlyMovements','runways','totalMovements','departures','arrivals','rwy18Departures']:
                d[key]=old[key]
            d['sources']['movements']=old['sources']['movements'];d['movementCoverage']=True
        days.append(d);day+=timedelta(days=1)
    if len(days)<(end-start).days*.9:raise ValueError('Insufficient history; keep previous published snapshot')
    return {**recent,'schemaVersion':2,'generatedAt':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
            'timeBasis':'Europe/Berlin (empirically verified against METAR)', 'sourceTimezone':'Europe/Berlin',
            'timezoneVerification':'dfld-time-audit.json', 'requestedPeriod':[str(start),str(end)],
            'days':days,'missingDates':missing,
            'directionUse':'Targets for chronological direction-model training, validation and testing; never an origin feature.',
            'limitations':['Clock alignment is empirical; exact source publication timestamps remain unavailable.',
                'DST transition dates are excluded from model joins; displayed repeated hours cannot be reconstructed.',
                'Direction is a 30-minute reported bin, not an exact switch timestamp.',
                'Source wind bearings are coarse context only; VRB/calm can display as zero. Model weather uses original METAR/ICON.',
                'Runway movement context is available only for the separately downloaded dates. Missing movement coverage is never zero.',
                'Zero RWY18 departures is not evidence of closure. Closure labels remain unknown.'],
            'reuse':{'notice':'User-requested noncommercial research extraction of factual direction values. Raw pages, graphics and flight identifiers are excluded; DFLD supplies no open-data license. Review source terms for broader reuse.','url':'https://www.dfld.de/DFLDimprint.php?L=G'}}


def write_history(snapshot):
    stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n')
    writer.writerow(['source_date','source_time','source_end_time','source_timezone','time_utc','eligible_for_model','operating_direction','wind_direction_display_bin','rwy18_closed','retrieved_at_utc','source_url'])
    for d in snapshot['days']:
        source=d['sources']['directionAndWind']
        for b in d['directionBins']:
            writer.writerow([d['date'],b['sourceTime'],b['sourceEndTime'],'Europe/Berlin (empirical)',b['timeUtc'],b['eligibleForModel'],b['operatingDirection'],b['windDirectionDeg'],'',source['retrievedAt'],source['url']])
    (ROOT/'dist/data/dfld.json').write_text(json.dumps(snapshot,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    (ROOT/'dist/data/dfld-direction.csv').write_text(stream.getvalue(),encoding='utf-8')
    print(json.dumps({'days':len(snapshot['days']),'bins':sum(d['directionCoverageBins'] for d in snapshot['days']),'missingDates':snapshot['missingDates']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--start-date',required=True,type=date.fromisoformat);p.add_argument('--end-date',required=True,type=date.fromisoformat)
    args=p.parse_args();write_history(build_history(args.start_date,args.end_date))
