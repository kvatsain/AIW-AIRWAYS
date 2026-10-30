"""Download public weather sources, preserving raw responses and URLs for reproduction."""
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor
import json, time

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'model' / 'raw'
RAW.mkdir(parents=True, exist_ok=True)
OUT = ROOT / 'dist' / 'data'
OUT.mkdir(parents=True, exist_ok=True)
JOBS=[]
for year, end in [(2024,'2024-12-31'),(2025,'2025-12-31'),(2026,'2026-10-29')]:
    variables=[f'{v}_previous_day{d}' for d in [1,2] for v in ['wind_speed_10m','wind_direction_10m','wind_gusts_10m']]
    query=dict(latitude=50.0379,longitude=8.5622,hourly=','.join(variables),models='icon_seamless',wind_speed_unit='kn',timezone='GMT',start_date=f'{year}-01-01',end_date=end)
    JOBS.append((f'icon_previous_{year}.json','https://previous-runs-api.open-meteo.com/v1/forecast?'+urlencode(query)))
    query['hourly']=','.join(f'{v}_previous_day3' for v in ['wind_speed_10m','wind_direction_10m','wind_gusts_10m'])
    JOBS.append((f'icon_day3_{year}.json','https://previous-runs-api.open-meteo.com/v1/forecast?'+urlencode(query)))
    query=[('station','EDDF'),('data','drct'),('data','sknt'),('data','gust'),('data','tmpf'),('data','alti'),('data','metar'),('year1',str(year)),('month1','1'),('day1','1'),('year2',str(year+1 if year<2026 else 2026)),('month2','1' if year<2026 else '10'),('day2','1' if year<2026 else '31'),('tz','Etc/UTC'),('format','onlycomma'),('latlon','no'),('elev','no'),('missing','M'),('trace','T'),('direct','no'),('report_type','3'),('report_type','4')]
    JOBS.append((f'eddf_{year}.csv','https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?'+urlencode(query)))
query=dict(latitude=50.0379,longitude=8.5622,hourly='wind_speed_10m,wind_direction_10m,wind_gusts_10m,temperature_2m,relative_humidity_2m,pressure_msl,precipitation,cloud_cover,wind_speed_80m,wind_direction_80m',current='wind_speed_10m,wind_direction_10m,wind_gusts_10m,temperature_2m,relative_humidity_2m,pressure_msl',models='icon_seamless',wind_speed_unit='kn',timezone='GMT',forecast_days=4,past_days=1)
JOBS.append(('live_icon.json','https://api.open-meteo.com/v1/forecast?'+urlencode(query)))
JOBS.append(('live_metar.json','https://aviationweather.gov/api/data/metar?ids=EDDF&format=json&hours=4'))

def fetch(job):
    name,url=job
    dest=RAW/name
    if dest.exists():
        return {'file':name,'url':url,'bytes':dest.stat().st_size,'cached':True}
    for attempt in range(3):
        try:
            with urlopen(Request(url,headers={'User-Agent':'Frankfurt-Wind-Hackathon/1.0 (research)'}),timeout=120) as response:
                data=response.read()
            dest.write_bytes(data)
            result={'file':name,'url':url,'bytes':len(data),'retrievedAt':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
            print(name, len(data), flush=True)
            return result
        except Exception as exc:
            print(name,'attempt',attempt+1,str(exc),flush=True)
            if attempt==2: return {'file':name,'url':url,'error':str(exc)}
            time.sleep(2)

if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=3) as pool: manifest=list(pool.map(fetch,JOBS))
    (RAW/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2))
