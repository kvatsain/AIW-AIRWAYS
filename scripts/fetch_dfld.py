"""Refresh a bounded DFLD factual snapshot. Standard library only; no training changes.

python scripts/fetch_dfld.py --end-date 2026-10-29 --days 3
Raw pages stay in ignored model/raw/dfld/. Published files contain only aggregate
movements and selected half-hour direction values, never aircraft identifiers.
"""
import argparse
import csv
import hashlib
import html
import io
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://www.dfld.de/Mess/'
RUNWAYS = ['07L', '07C', '07R', '25L', '25C', '25R', '18', 'unknown']


def text(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', value))).strip()


def fetch(url, name):
    req = Request(url, headers={'User-Agent': 'FRA-WindLab/1.0 (noncommercial research snapshot)'})
    with urlopen(req, timeout=45) as response:
        body = response.read(8_000_001)
        if len(body) > 8_000_000:
            raise ValueError('Unexpectedly large DFLD response')
        charset = response.headers.get_content_charset() or 'iso-8859-1'
    retrieved = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    meta = {'url': url, 'retrievedAt': retrieved, 'sha256': hashlib.sha256(body).hexdigest()}
    raw = ROOT / 'model/raw/dfld'
    raw.mkdir(parents=True, exist_ok=True)
    (raw / f'{name}.html').write_bytes(body)
    (raw / f'{name}.provenance.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    # DFLD declares UTF-8 but some aircraft names contain legacy bytes. We only
    # parse numeric fields and HTML entities; replacement never changes raw proof.
    return body.decode(charset, errors='replace'), meta


def parse_weather(page, day):
    label = day.strftime('%d.%m.%Y')
    matching = [row for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', page, re.S | re.I)
                if re.search(r'<td[^>]*>\s*' + re.escape(label) + r':\s*</td>', row)]
    if len(matching) != 1:
        raise ValueError(f'Missing or duplicate DFLD date row: {label}')
    values = {}
    for raw in re.findall(r'title="([^"]*)"', matching[0]):
        match = re.fullmatch(r'(\d\d:\d\d) - (\d\d:\d\d): (BR(?:07|25)|\d{1,3}°)', html.unescape(raw))
        if not match:
            continue
        start, end, value = match.groups()
        item = values.setdefault(start, {'sourceTime': start, 'sourceEndTime': end,
                                        'operatingDirection': None, 'windDirectionDeg': None})
        if item['sourceEndTime'] != end:
            raise ValueError('Conflicting source interval')
        key = 'operatingDirection' if value.startswith('BR') else 'windDirectionDeg'
        if item[key] is not None:
            raise ValueError(f'Duplicate {key} at {start}')
        item[key] = value[2:] if value.startswith('BR') else int(value[:-1])
        if key == 'windDirectionDeg' and not 0 <= item[key] <= 360:
            raise ValueError('Invalid wind direction')
    result = []
    for minute in range(0, 1440, 30):
        start = f'{minute // 60:02}:{minute % 60:02}'
        end = f'{(minute + 30) // 60:02}:{(minute + 30) % 60:02}'
        item = values.pop(start, {'sourceTime': start, 'sourceEndTime': end,
                                 'operatingDirection': None, 'windDirectionDeg': None})
        if item['sourceEndTime'] != end:
            raise ValueError('Unexpected source interval; no timezone normalization attempted')
        result.append(item)
    if values or not any(x['operatingDirection'] for x in result):
        raise ValueError('Unrecognized or empty direction history')
    return result


def parse_airport(page):
    if '<h2>Einzelauflistung</h2>' not in page:
        raise ValueError('DFLD movement table not found')
    detail = page.split('<h2>Einzelauflistung</h2>', 1)[1].split('</table>', 1)[0]
    hourly = [{'sourceTime': f'{h:02}:00', 'departures': 0, 'arrivals': 0,
               'rwy18Departures': 0, 'arrivals07': 0, 'arrivals25': 0,
               'otherArrivals': 0, 'rwy18Closed': None} for h in range(24)]
    runway = {r: {'runway': r, 'departures': 0, 'arrivals': 0} for r in RUNWAYS}
    count = 0
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', detail, re.S | re.I):
        cells = [text(c) for c in re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.S | re.I)]
        if len(cells) != 8:
            continue
        if not re.fullmatch(r'\d\d:\d\d:\d\d', cells[0]):
            raise ValueError('Unrecognized movement time')
        hh, mm, ss = map(int, cells[0].split(':'))
        if hh > 23 or mm > 59 or ss > 59:
            raise ValueError('Invalid movement time')
        kind = {'\ue916': 'departures', '\ue917': 'arrivals'}.get(cells[1])
        if kind is None:
            raise ValueError('Unrecognized arrival/departure marker')
        rwy = cells[7] if cells[7] in RUNWAYS else 'unknown'
        hourly[hh][kind] += 1
        runway[rwy][kind] += 1
        if rwy == '18' and kind == 'departures':
            hourly[hh]['rwy18Departures'] += 1
        if kind == 'arrivals':
            key = 'arrivals07' if rwy.startswith('07') else 'arrivals25' if rwy.startswith('25') else 'otherArrivals'
            hourly[hh][key] += 1
        count += 1
    published = re.search(r'Summe:\s*(\d+)', detail)
    if not published or count != int(published.group(1)) or not count:
        raise ValueError('Movement rows do not reconcile with DFLD published total')
    # Reconcile each runway with the independently published runway summary.
    summary = page.split('<h2>Pisten Belegung</h2>', 1)[1].split('</table>', 1)[0]
    columns = [text(x) for x in re.findall(r'<th\b[^>]*colspan="2"[^>]*>(.*?)</th>', summary, re.S | re.I)]
    columns = ['unknown' if r == '\ue918' else r for r in columns]
    if not columns or len(set(columns)) != len(columns) or any(r not in RUNWAYS for r in columns):
        raise ValueError('Unrecognized runway summary columns')
    if any(runway[r]['departures'] + runway[r]['arrivals'] for r in RUNWAYS if r not in columns):
        raise ValueError('Runway missing from published summary')
    totals = []
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', summary, re.S | re.I):
        cells = [text(c) for c in re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.S | re.I)]
        if len(cells) == 2 * len(columns) + 2 and cells[0] == 'Σ':
            totals = list(map(int, cells[1:]))
    expected = [runway[r][k] for r in columns for k in ('departures', 'arrivals')] + [count]
    if totals != expected:
        raise ValueError('Runway aggregates do not reconcile with DFLD summary')
    return hourly, list(runway.values()), count


def changes(bins):
    return [{'sourceTime': b['sourceTime'], 'sourceEndTime': b['sourceEndTime'],
             'from': a['operatingDirection'], 'to': b['operatingDirection']}
            for a, b in zip(bins, bins[1:])
            if a['operatingDirection'] and b['operatingDirection']
            and a['operatingDirection'] != b['operatingDirection']]


def build(end, count):
    if not 1 <= count <= 7:
        raise ValueError('Use 1–7 days per manual refresh; this is not a bulk archive downloader')
    if end >= datetime.now(timezone.utc).date():
        raise ValueError('Select completed calendar dates only')
    days = [end - timedelta(days=i) for i in reversed(range(count))]
    months, result = {}, []
    for day in days:
        key = day.strftime('%Y-%m')
        date_param = day.strftime('%d.%m.%Y')
        if key not in months:
            months[key] = fetch(BASE + f'StatWetter.php?RegNr=1&D={date_param}', f'weather-{key}')
        page, weather_source = months[key]
        bins = parse_weather(page, day)
        airport, airport_source = fetch(BASE + f'StatAirportTag.php?R=1&D={date_param}', f'airport-{day}')
        hourly, runways, total = parse_airport(airport)
        result.append({'date': day.isoformat(), 'sources': {'directionAndWind': weather_source, 'movements': airport_source},
                       'directionBins': bins, 'directionChanges': changes(bins), 'hourlyMovements': hourly,
                       'runways': runways, 'totalMovements': total,
                       'departures': sum(x['departures'] for x in hourly),
                       'arrivals': sum(x['arrivals'] for x in hourly),
                       'rwy18Departures': sum(x['rwy18Departures'] for x in hourly),
                       'directionCoverageBins': sum(x['operatingDirection'] is not None for x in bins)})
    return {'schemaVersion': 1, 'provider': 'Deutscher Fluglärmdienst e.V. (DFLD)',
            'generatedAt': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'mode': 'historical snapshot', 'timeBasis': 'DFLD displayed time', 'sourceTimezone': None,
            'directionSource': 'DFLD describes Frankfurt direction since March 2004 as Fraport-based operating direction.',
            'windResolutionDegrees': 30, 'days': result,
            'limitations': ['Source timezone and original publication times are unverified; no UTC join or forecast-time availability claim.',
                           'Direction is reported at 30-minute resolution. A changed bin is not an exact switch timestamp.',
                           'Wind bearings are the 30-degree display bins in the DFLD METAR-based weather statistics; speed and gust are not imported.',
                           'Movement counts are DFLD-recorded activity, not certified totals. Later corrections are possible.',
                           'Zero RWY18 departures is not evidence of closure. RWY18 closure labels remain unknown.',
                           'These historical records are not used to train, initialize, or score the current forecast.'],
            'reuse': {'notice': 'Concise attributed factual subset and derived aggregates only. DFLD does not publish an open-data license. Raw pages and flight identifiers are not redistributed.',
                      'url': 'https://www.dfld.de/DFLDimprint.php?L=G'},
            'documentationUrl': BASE + 'Language/MessHelpG.html', 'regionUrl': 'https://www.dfld.de/Mess/Language/MessR001.php'}


def write(snapshot):
    target = ROOT / 'dist/data'
    (target / 'dfld.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    stream = io.StringIO(newline='')
    fields = ['source_date', 'source_time', 'source_end_time', 'source_timezone', 'operating_direction',
              'wind_direction_deg_30_degree_bin', 'rwy18_closed', 'retrieved_at_utc', 'source_url']
    writer = csv.writer(stream, lineterminator='\n'); writer.writerow(fields)
    for day in snapshot['days']:
        source = day['sources']['directionAndWind']
        for b in day['directionBins']:
            writer.writerow([day['date'], b['sourceTime'], b['sourceEndTime'], 'unverified', b['operatingDirection'],
                             b['windDirectionDeg'], '', source['retrievedAt'], source['url']])
    (target / 'dfld-direction.csv').write_text(stream.getvalue(), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--end-date', required=True, type=date.fromisoformat)
    parser.add_argument('--days', type=int, default=3)
    args = parser.parse_args()
    snapshot = build(args.end_date, args.days)
    write(snapshot)
    print(json.dumps([{'date': d['date'], 'movements': d['totalMovements'], 'rwy18Departures': d['rwy18Departures'],
                       'directionBins': d['directionCoverageBins'], 'changes': d['directionChanges']} for d in snapshot['days']]))
