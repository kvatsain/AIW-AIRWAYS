"""Export an auditable historical 48h prediction from saved archives.
python model/predict.py --issue-time 2026-05-10T06:00:00Z --output model/prediction.csv
Only uses origin-or-earlier METAR and archived forecasts predating the origin.
Exports probability estimates and physics baseline, never actual operational labels.
"""
import argparse, json, math
from pathlib import Path
import numpy as np
import pandas as pd
from train import ROOT, OUT, observations, forecasts, feature_matrix, predict

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--issue-time',required=True);parser.add_argument('--hours',type=int,default=48);parser.add_argument('--output',default=str(ROOT/'model'/'historical_prediction.csv'));parser.add_argument('--initial-direction',choices=['07','25'])
    args=parser.parse_args();issue=pd.Timestamp(args.issue_time)
    if issue.tzinfo is None:raise ValueError('issue-time must have an explicit UTC offset, e.g. Z')
    issue=issue.tz_convert('UTC').floor('h')
    if args.hours<1 or args.hours>48:raise ValueError('hours must be 1..48')
    model=json.loads((OUT/'model.json').read_text());policies=json.loads((OUT/'alert-policies.json').read_text())['policyDefinitions'];obs,_=observations();nwp=forecasts()
    if issue<=pd.Timestamp(model['validationPeriod'][1],tz='UTC')+pd.Timedelta(days=1):raise ValueError('Issue time must follow model selection (2026-03-31); earlier replay would leak fitted coefficients.')
    if issue not in obs.index:raise ValueError('Issue time is outside downloaded observations. Run download_data.py for available coverage.')
    origin=obs.loc[[issue]].copy()
    if not np.isfinite(origin[['east','north','gust','eastTrend3h','northTrend3h','od07']].to_numpy(float)).all():raise ValueError('Origin METAR is missing/VRB. Choose an adjacent hour; no invented direction is used.')
    if args.initial_direction:origin.loc[:,'od07']=int(args.initial_direction=='07')
    rows=[]
    for h in range(1,args.hours+1):
        nearest=min([1,6,24,48],key=lambda x:abs(x-h));spec=model['models'][str(nearest)];lead=spec['archiveLeadHours']//24;t=issue+pd.Timedelta(hours=h)
        # With nearest-horizon mapping, the archive always predates origin.
        if lead*24<h:raise ValueError('Requested archive would postdate origin')
        wx=nwp.reindex([t])[[f'{v}_previous_day{lead}' for v in ['wind_speed_10m','wind_direction_10m','wind_gusts_10m']]].to_numpy(float)
        if not np.isfinite(wx).all():raise ValueError(f'Missing archived forecast at {t}; extend data before export')
        x=feature_matrix(wx,origin,pd.DatetimeIndex([t]));z=(x-np.array(spec['mean']))/np.array(spec['scale']);p={}
        for name,c in spec['classifiers'].items():p[name]=float(predict(z,np.array([c['intercept']]+c['weights']))[0])
        s,d,g=wx[0];tail=max(0,s*math.cos(math.radians(d)));cross=abs(g*math.sin(math.radians(d-180)))
        local=t.tz_convert('Europe/Berlin');scheduled=5<=local.hour<23;wind_exceeded=tail>=15 or cross>40
        catch=p['closed18']>=policies['catchMore']['threshold'] or wind_exceeded
        reduce=p['closed18']>=policies['reduceFalseAlarms']['threshold'] or wind_exceeded
        rows.append({'issue_time':issue.isoformat(),'valid_time':t.isoformat(),'valid_time_frankfurt':local.isoformat(),'schedule_timezone':'Europe/Berlin','lead_hours':h,'model_horizon_hours':nearest,'archive_lead_hours':lead*24,'wind_speed_kt':s,'wind_direction_true':d,'gust_kt':g,'p_rwy18_wind_usable':1-p['closed18'],'p_od07_proxy':p['od07'],'p_od25_proxy':1-p['od07'],'baseline_rwy18_wind_usable':not wind_exceeded,'scheduled_departures_window':scheduled,'scheduled_arrivals_window':scheduled,'night_restriction':not scheduled,'conditional_delay_window':local.hour==23,'catch_threshold':policies['catchMore']['threshold'],'reduce_threshold':policies['reduceFalseAlarms']['threshold'],'catch_weather_alert':catch,'reduce_weather_alert':reduce,'catch_scheduled_alert':scheduled and catch,'reduce_scheduled_alert':scheduled and reduce,'label_basis':'weather-derived proxy; flight window does not establish permission'})
    dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True);pd.DataFrame(rows).to_csv(dest,index=False);print(f'Exported {len(rows)} hours to {dest}')

if __name__=='__main__':main()
