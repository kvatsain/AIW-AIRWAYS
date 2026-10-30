"""Empirical clock audit: public DFLD wind display vs UTC EDDF METAR.

python audit_dfld_timezone.py --metar /path/to/model/raw/eddf_2026.csv

This establishes an empirical alignment, not a provider timezone declaration or
publication-time guarantee. It must never convert missing/VRB training winds to N.
"""
import argparse
import csv
import hashlib
import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

SAMPLES = [
    ('2026-05-15', 2), ('2026-07-15', 2), ('2026-10-24', 2),
    ('2026-10-26', 1), ('2026-10-29', 1),
]
OFFSETS = [0, 1, 2]


def fetch(url, target, refresh=False):
    provenance = target.with_suffix('.provenance.json')
    if target.exists() and provenance.exists() and not refresh:
        body = target.read_bytes()
        meta = json.loads(provenance.read_text(encoding='utf-8'))
        if meta['url'] != url or meta['sha256'] != hashlib.sha256(body).hexdigest():
            raise ValueError('Cache provenance mismatch')
    else:
        with urlopen(Request(url, headers={'User-Agent':'FRA-WindLab/1.0 (noncommercial research clock audit)'}), timeout=45) as response:
            body = response.read(8_000_001)
            if len(body) > 8_000_000:
                raise ValueError('Unexpected response size')
        meta = {'url':url, 'retrievedAt':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
                'sha256':hashlib.sha256(body).hexdigest(), 'bytes':len(body)}
        target.write_bytes(body)
        provenance.write_text(json.dumps(meta,indent=2)+'\n',encoding='utf-8')
    return body.decode('utf-8',errors='replace'), meta


def load_metar(path):
    observations = {}
    with path.open(encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            if row['sknt'] == 'M':
                continue
            t = datetime.strptime(row['valid'],'%Y-%m-%d %H:%M')
            observations[t] = {
                'direction':None if row['drct']=='M' else int(float(row['drct'])) % 360,
                'speed':float(row['sknt']), 'metar':row['metar'],
            }
    return observations


def parse_wind(page):
    wind = []
    for title in re.findall(r'title="([^"]*)"',page):
        match = re.fullmatch(r'Windrichtung .* / (\d+)°, (\d+)kn',html.unescape(title))
        if match:
            direction,speed=map(int,match.groups())
            wind.append((direction % 360,speed))
    if len(wind)!=48:
        raise ValueError(f'Expected 48 displayed wind bins, received {len(wind)}')
    return wind


def audit(metar_path,out,refresh=False):
    out.mkdir(parents=True,exist_ok=True)
    observations=load_metar(metar_path)
    results=[]
    for iso,berlin_offset in SAMPLES:
        day=datetime.fromisoformat(iso)
        url='https://www.dfld.de/Mess/Messwerte.php?R=1&S=100&D='+day.strftime('%d.%m.%Y')
        page,source=fetch(url,out/f'station-{iso}.html',refresh)
        wind=parse_wind(page)
        candidates=[]
        for offset in OFFSETS:
            exact=eligible=nonvariable_exact=nonvariable_eligible=0
            for i,value in enumerate(wind):
                # EDDF publishes regular METAR at UTC :20 and :50. Those reports
                # fall twenty minutes into the DFLD display's half-hour bins.
                t=day+timedelta(minutes=30*i+20)-timedelta(hours=offset)
                obs=observations.get(t)
                if obs is None:
                    continue
                eligible+=1
                # DFLD renders VRB/missing direction as 0 degrees. Emulate only
                # for this source-identification audit; never for model features.
                source_style=(0 if obs['direction'] is None else obs['direction'],obs['speed'])
                exact+=int(value==source_style)
                if obs['direction'] is not None:
                    nonvariable_eligible+=1
                    nonvariable_exact+=int(value==(obs['direction'],obs['speed']))
            candidates.append({'assumedUtcOffsetHours':offset,'exactMatches':exact,'eligibleBins':eligible,
                               'nonVariableExactMatches':nonvariable_exact,'nonVariableEligibleBins':nonvariable_eligible})
        selected=next(x for x in candidates if x['assumedUtcOffsetHours']==berlin_offset)
        if selected['eligibleBins']!=48 or selected['exactMatches']!=48:
            raise ValueError(f'Clock audit failed for {iso}: {selected}')
        if any(x['exactMatches']>=selected['exactMatches'] for x in candidates if x is not selected):
            raise ValueError(f'Clock audit is ambiguous for {iso}')
        results.append({'date':iso,'source':source,'expectedEuropeBerlinUtcOffsetHours':berlin_offset,
                        'displayedWindBins':len(wind),'candidates':candidates})
    dst_url='https://www.dfld.de/Mess/StatWetter.php?RegNr=1&D=25.10.2026'
    dst_page,dst_source=fetch(dst_url,out/'dst-2026-10-25.html',refresh)
    row=next(row for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>',dst_page,re.S|re.I)
             if re.search(r'<td[^>]*>\s*25\.10\.2026:',row))
    direction_titles=[html.unescape(x) for x in re.findall(r'title="([^"]*)"',row)
                      if re.fullmatch(r'\d\d:\d\d - \d\d:\d\d: BR(?:07|25)',x)]
    report={
        'schemaVersion':1,'auditedAt':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
        'inferredTimezone':'Europe/Berlin','evidenceType':'empirical METAR cross-check; not explicit provider declaration',
        'metar':{'file':metar_path.name,'sha256':hashlib.sha256(metar_path.read_bytes()).hexdigest(),
                 'station':'EDDF','archiveTimezone':'UTC','source':'Iowa Environmental Mesonet',
                 'url':'https://mesonet.agron.iastate.edu/request/download.phtml'},
        'method':'Compare ordered DFLD wind bins to EDDF METAR at display-bin start +20 minutes minus candidate UTC offset. Test offsets 0, +1 and +2 hours independently on each date.',
        'normalization':['360 degrees is equivalent to 0 degrees.',
                         'DFLD displays VRB/missing METAR direction as zero; emulate this only for the clock audit. Separate nonvariable comparisons are reported. Training must retain VRB as missing.'],
        'results':results,
        'summary':{'sampleDays':len(results),'matchingBins':sum(next(c['exactMatches'] for c in r['candidates'] if c['assumedUtcOffsetHours']==r['expectedEuropeBerlinUtcOffsetHours']) for r in results),
                   'eligibleBins':48*len(results)},
        'dstTransition':{'date':'2026-10-25','source':dst_source,'directionBins':len(direction_titles),
                         'repeated0200BinCount':sum(x.startswith('02:00 -') for x in direction_titles),
                         'recommendation':'Exclude the entire autumn-transition date from UTC-aligned training/scoring. Only 48 source-clock bins are supplied, so the repeated local hour cannot be reconstructed.'},
        'limitations':['No explicit provider timezone declaration was found.',
                       'The clock finding is based on wind displayed alongside direction. It supports, but does not independently certify, the operating-direction clock.',
                       'Half-hour direction labels do not identify the exact switch instant.',
                       'Retrieval timestamps do not establish original publication times or availability at forecast issue time.',
                       'Do not use contemporaneous DFLD labels as forecast inputs without a separately justified availability policy.'],
        'methodologyUrl':'https://www.dfld.de/Mess/Language/MessHelpG.html',
    }
    (out/'timezone-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metar',required=True,type=Path)
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'model/raw/dfld-time-audit')
    parser.add_argument('--refresh',action='store_true')
    args=parser.parse_args()
    report=audit(args.metar,args.output,args.refresh)
    print(json.dumps({'summary':report['summary'],'dstTransition':report['dstTransition'],
                      'report':str(args.output/'timezone-audit.json')},ensure_ascii=False))
