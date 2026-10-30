"""Chronological wind-proxy classification. Requirements: numpy, pandas.

Targets are simulated weather eligibility, NOT observed airport operations.
All forecasts are archived >=18 hours before origin; future METAR is labels only.
Run: python model/download_data.py ; python model/train.py
"""
from pathlib import Path
from datetime import datetime, timezone
import json, math
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'model'/'raw'
OUT=ROOT/'dist'/'data'
FEATURES=['nwpEastFrom','nwpNorthFrom','nwpSpeed','nwpGust','nwpTailwind18','nwpCrosswindGust18','nwpHeadwind07','obsEastFrom','obsNorthFrom','obsGust','obsEastTrend3h','obsNorthTrend3h','obsOD07','hourSin','hourCos','yearSin','yearCos']
HORIZONS={1:1,6:1,24:2,48:3}
def components(speed,direction):
    a=np.radians(direction)
    return speed*np.sin(a),speed*np.cos(a)

def simulate_direction(df):
    """At real observation timestamps; small adverse component persists >30min.
    Unknown initial state seeded 25. Missing wind resets persistence and emits NaN.
    """
    states=[]; direction='25'; since=None; last=None
    for t,row in df.iterrows():
        if not np.isfinite(row['drct']) or not np.isfinite(row['sknt']):
            states.append(np.nan); since=None; last=t; continue
        if last is None or (t-last).total_seconds()>3600: since=None
        tail=-row['sknt']*math.cos(math.radians(row['drct']-int(direction)*10))
        if tail>1e-9:
            if since is None: since=t
            if tail>=10 or (t-since).total_seconds()>1800:
                direction='07' if direction=='25' else '25'; since=None
        else: since=None
        states.append(int(direction=='07'));last=t
    return states

def observations():
    df=pd.concat([pd.read_csv(f,na_values=['M']) for f in sorted(RAW.glob('eddf_*.csv'))],ignore_index=True)
    raw_count=len(df)
    df['time']=pd.to_datetime(df['valid'],utc=True)
    df=df.sort_values('time').drop_duplicates('time',keep='last').set_index('time')
    # VRB wind lacks a unique direction: exclude rather than invent 0 degrees.
    for c in ['drct','sknt','gust']:df[c]=pd.to_numeric(df[c],errors='coerce')
    df.loc[(df.sknt<0)|(df.sknt>100),'sknt']=np.nan
    df.loc[(df.drct<0)|(df.drct>360),'drct']=np.nan
    df['gustReported']=df.gust.notna()
    df['gust']=df.gust.fillna(df.sknt).clip(lower=0)
    df['gust']=np.maximum(df.gust,df.sknt)
    df['od07']=simulate_direction(df)
    east,north=components(df.sknt,df.drct)
    df['east']=east;df['north']=north
    df['closed18']=((north>=15)|(np.abs(df.gust*np.sin(np.radians(df.drct-180)))>40)).astype(float)
    df.loc[df[['drct','sknt']].isna().any(axis=1),'closed18']=np.nan
    # Latest known observation <= every hour, at most 40min old. No interpolation.
    hours=pd.date_range(df.index.min().ceil('h'),df.index.max().floor('h'),freq='h',tz='UTC')
    hourly=df.reindex(hours,method='ffill',tolerance=pd.Timedelta('40min'))
    hourly['eastTrend3h']=hourly.east-hourly.east.shift(3)
    hourly['northTrend3h']=hourly.north-hourly.north.shift(3)
    return hourly,{'rawMetarReports':raw_count,'uniqueMetarReports':len(df),'hourlyObservations':len(hourly),'variableOrMissingDirectionReports':int(df.drct.isna().sum()),'gustReportedFraction':float(df.gustReported.mean()),'firstObservation':df.index.min().isoformat(),'lastObservation':df.index.max().isoformat()}

def forecasts():
    frames=[]
    for year in [2024,2025,2026]:
        one=pd.DataFrame(json.loads((RAW/f'icon_previous_{year}.json').read_text())['hourly']).set_index('time')
        three=pd.DataFrame(json.loads((RAW/f'icon_day3_{year}.json').read_text())['hourly']).set_index('time')
        frames.append(one.join(three))
    frame=pd.concat(frames)
    frame.index=pd.to_datetime(frame.index,utc=True)
    return frame

def feature_matrix(nwp,obs,times):
    s,d,g=nwp[:,0],nwp[:,1],nwp[:,2]
    east,north=components(s,d)
    h=times.hour.to_numpy()+times.minute.to_numpy()/60
    yr=times.dayofyear.to_numpy()/365.25*2*np.pi
    return np.column_stack([east,north,s,g,np.maximum(0,north),np.abs(g*np.sin(np.radians(d-180))),s*np.cos(np.radians(d-70)),obs.east,obs.north,obs.gust,obs.eastTrend3h,obs.northTrend3h,obs.od07,np.sin(h/24*2*np.pi),np.cos(h/24*2*np.pi),np.sin(yr),np.cos(yr)])

def sigmoid(z):return 1/(1+np.exp(-np.clip(z,-35,35)))
def fit_logistic(x,y,l2):
    a=np.column_stack([np.ones(len(x)),x]);coef=np.zeros(a.shape[1]);coef[0]=math.log((y.sum()+.5)/(len(y)-y.sum()+.5))
    penalty=np.eye(a.shape[1])*l2;penalty[0,0]=0
    for _ in range(50):
        p=sigmoid(a@coef);w=np.maximum(p*(1-p),1e-7)
        grad=a.T@(p-y)+penalty@coef
        hess=(a.T*w)@a+penalty+np.eye(a.shape[1])*1e-8
        step=np.linalg.solve(hess,grad)
        # Damping makes rare-event Newton iterations robust.
        if np.max(np.abs(step))>3:step*=3/np.max(np.abs(step))
        coef-=step
        if np.max(np.abs(step))<1e-7:break
    return coef
def predict(x,coef):return sigmoid(coef[0]+x@coef[1:])
def rule_baseline(nwp,times,origins,horizon,lead):
    state=origins.od07.to_numpy().astype(int);since=np.full(len(times),-1);missing=np.zeros(len(times),dtype=bool)
    for step in range(horizon+1):
        ts=times-pd.Timedelta(hours=horizon-step)
        wx=nwp.reindex(ts)[[f'wind_speed_10m_previous_day{lead}',f'wind_direction_10m_previous_day{lead}']].to_numpy(float)
        ok=np.isfinite(wx).all(axis=1);missing|=~ok
        heading=np.where(state==1,70,250)
        tail=-wx[:,0]*np.cos(np.radians(wx[:,1]-heading))
        adverse=(tail>1e-9)&ok
        since=np.where(adverse & (since<0),step,since)
        switch=adverse&((tail>=10)|((step-since)*60>30))
        state=np.where(switch,1-state,state)
        since=np.where(~adverse|switch,-1,since)
    return state,missing
def scores(y,p):
    y=y.astype(int); pred=(p>=.5).astype(int)
    tp=int(((pred==1)&(y==1)).sum());tn=int(((pred==0)&(y==0)).sum());fp=int(((pred==1)&(y==0)).sum());fn=int(((pred==0)&(y==1)).sum())
    recall=tp/(tp+fn) if tp+fn else None;specificity=tn/(tn+fp) if tn+fp else None
    bins=[]
    for lo in np.arange(0,1,.1):
        mask=(p>=lo)&(p<lo+.100001)
        if mask.any():bins.append({'min':round(float(lo),1),'max':round(float(lo+.1),1),'n':int(mask.sum()),'predicted':float(p[mask].mean()),'observed':float(y[mask].mean())})
    return {'n':len(y),'positiveEvents':int(y.sum()),'accuracy':float((pred==y).mean()),'balancedAccuracy':(recall+specificity)/2 if recall is not None and specificity is not None else None,'brier':float(np.mean((p-y)**2)),'recall':recall,'precision':tp/(tp+fp) if tp+fp else None,'confusion':{'tp':tp,'tn':tn,'fp':fp,'fn':fn},'reliability':bins}

def jsonwrite(name,value):(OUT/name).write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf8')

def main():
    obs,counts=observations();nwp=forecasts();models={};evaluations=[];backtests=[]
    for horizon,lead in HORIZONS.items():
        times=obs.index.intersection(nwp.index)
        origin_times=times-pd.Timedelta(hours=horizon)
        origins=obs.reindex(origin_times)
        wx=nwp.reindex(times)[[f'{v}_previous_day{lead}' for v in ['wind_speed_10m','wind_direction_10m','wind_gusts_10m']]].to_numpy(dtype=float)
        x=feature_matrix(wx,origins,times)
        targets=obs.reindex(times)[['closed18','od07']].to_numpy(dtype=float)
        valid=np.isfinite(x).all(axis=1)&np.isfinite(targets).all(axis=1)
        x=x[valid];targets=targets[valid];times=times[valid];origins=origins.iloc[np.flatnonzero(valid)];wx=wx[valid]
        train=times<pd.Timestamp('2026-01-01',tz='UTC')
        # 72h purged gaps prevent overlapping horizon targets at boundaries.
        val=(times>=pd.Timestamp('2026-01-04',tz='UTC'))&(times<pd.Timestamp('2026-04-01',tz='UTC'))
        test=(times>=pd.Timestamp('2026-04-04',tz='UTC'))&(times<pd.Timestamp('2026-10-30',tz='UTC'))
        mean=x[train].mean(axis=0);std=x[train].std(axis=0);std=np.where(std<1e-6,1,std);z=(x-mean)/std
        entry={'horizonHours':horizon,'archiveLeadHours':lead*24,'mean':mean.tolist(),'scale':std.tolist(),'classifiers':{}}
        evaluation={'horizonHours':horizon,'archiveLeadHours':lead*24,'trainRows':int(train.sum()),'validationRows':int(val.sum()),'testRows':int(test.sum()),'testStart':times[test].min().isoformat(),'testEnd':times[test].max().isoformat(),'targets':{}}
        probs={}
        baseline_od,baseline_missing=rule_baseline(nwp,times,origins,horizon,lead)
        baseline_closed=((wx[:,0]*np.cos(np.radians(wx[:,1]))>=15)|(np.abs(wx[:,2]*np.sin(np.radians(wx[:,1]-180)))>40)).astype(float)
        for col,target in enumerate(['closed18','od07']):
            y=targets[:,col];candidates=[]
            for l2 in [.1,1,10,100]:
                coef=fit_logistic(z[train],y[train],l2)
                candidates.append((np.mean((predict(z[val],coef)-y[val])**2),l2,coef))
            loss,l2,coef=min(candidates,key=lambda a:a[0]);p=predict(z,coef);probs[target]=p
            entry['classifiers'][target]={'intercept':float(coef[0]),'weights':coef[1:].tolist(),'l2':l2,'validationBrier':float(loss)}
            persistence=origins[target].to_numpy()
            climate=np.repeat(y[train].mean(),test.sum())
            rule=baseline_closed if target=='closed18' else baseline_od
            comparable=test & (~baseline_missing if target=='od07' else np.ones(len(test),dtype=bool))
            evaluation['targets'][target]={'model':scores(y[test],p[test]),'persistence':scores(y[test],persistence[test]),'climatology':scores(y[test],climate),'weatherRules':scores(y[comparable],rule[comparable]),'modelOnRulesComparableRows':scores(y[comparable],p[comparable]),'trainingPositiveEvents':int(y[train].sum()),'validationPositiveEvents':int(y[val].sum())}
            evaluation['targets'][target]['rules']=evaluation['targets'][target]['weatherRules']
            if target=='od07':evaluation['targets'][target]['weatherRules']['excludedIntermediateForecastMissingRows']=int(baseline_missing[test].sum())
        models[str(horizon)]=entry;evaluations.append(evaluation)
        if horizon==24:
            for i in np.flatnonzero(test)[::12]:
                backtests.append({'time':times[i].isoformat(),'pRwy18Open':round(1-float(probs['closed18'][i]),5),'p07':round(float(probs['od07'][i]),5),'observedProxyRwy18Open':bool(targets[i,0]==0),'observedProxyOD':'07' if targets[i,1] else '25','windSpeed':float(wx[i,0]),'windDirection':float(wx[i,1]),'windGust':float(wx[i,2])})
        print(horizon,'h',evaluation['trainRows'],evaluation['testRows'],{k:{m:round(v,4) if v is not None else None for m,v in t['model'].items() if m in ['accuracy','brier','recall']} for k,t in evaluation['targets'].items()},flush=True)
    generated=datetime.now(timezone.utc).isoformat()
    limitations=['Targets are weather-derived challenge proxies. No historical airport direction or RWY18 closure log was available; scores do not measure actual operations accuracy.','METAR gust absence is replaced with reported sustained wind; this may miss gust-related restrictions. VRB/missing wind directions are excluded.','Direction proxy uses observation timestamps and a >30-minute adverse-wind persistence rule; gaps reset persistence. Ground wind alone omits upper winds, ATC, noise rules, traffic, aircraft-specific limits and runway works.','Archived forecast lead times are 24h (1h/6h model), 48h (24h model) and 72h (48h model), conservatively predating origins. Live inference uses freshest ICON, so live feature distribution differs; reported scores are archive tests.','Probabilities are logistic scores with held-out Brier evaluation, not independently calibrated operational probabilities. No positive closure event support means no closure-recall claim.','Between tested horizons, dashboard chooses nearest model. 48-hour UI is hourly; no 30-minute transition timing precision is claimed.']
    metadata={'version':'1.0.0','name':'FRA Wind Logistic v1','algorithm':'L2 regularized logistic regression, separate targets and horizons','featureNames':FEATURES,'generatedAt':generated,'units':{'wind':'kn','direction':'degrees true FROM','time':'UTC'},'counts':counts,'targetBasis':'weather-derived challenge proxies','trainPeriod':['2024-01-01','2025-12-31'],'validationPeriod':['2026-01-04','2026-03-31'],'testPeriod':['2026-04-04','2026-10-29'],'purgeHours':72,'models':models,'limitations':limitations,'thresholds':{'rwy18TailwindKn':15,'crosswindGustKn':40,'directionImmediateTailwindKn':10,'smallTailwindPersistenceMinutes':30,'trueHeadings':[180,70,250]}}
    jsonwrite('model.json',metadata);jsonwrite('metrics.json',{'generatedAt':generated,'counts':counts,'targetBasis':metadata['targetBasis'],'split':{k:metadata[k] for k in ['trainPeriod','validationPeriod','testPeriod','purgeHours']},'horizons':evaluations,'limitations':limitations});jsonwrite('backtest.json',backtests)
    live=json.loads((RAW/'live_icon.json').read_text());metars=json.loads((RAW/'live_metar.json').read_text());metar=metars[0] if metars else {}
    current=live['current'];direction=metar.get('wdir');speed=metar.get('wspd');gust=metar.get('wgst') or speed
    observation={'time':metar.get('reportTime'),'windSpeed':speed,'windDirection':direction,'windGust':gust,'rawMetar':metar.get('rawOb'),'source':'NOAA Aviation Weather Center METAR','eastTrend3h':0,'northTrend3h':0}
    if not isinstance(direction,(float,int)) or speed is None:
        observation={'time':current['time']+'Z','windSpeed':current['wind_speed_10m'],'windDirection':current['wind_direction_10m'],'windGust':current['wind_gusts_10m'],'source':'DWD ICON modeled current conditions (METAR unavailable)','eastTrend3h':0,'northTrend3h':0}
    jsonwrite('weather.json',live)
    operations=json.loads((RAW/'current_operations.json').read_text()) if (RAW/'current_operations.json').exists() else None
    retrieved=datetime.fromtimestamp((RAW/'live_icon.json').stat().st_mtime,timezone.utc).isoformat()
    jsonwrite('forecast.json',{'generatedAt':generated,'weatherRetrievedAt':retrieved,'source':'DWD ICON Seamless via Open-Meteo','sourceUrl':'https://open-meteo.com/en/docs/dwd-api','weatherTimestamp':current['time']+'Z','observation':observation,'currentOperations':operations,'hourly':[],'weather':live,'limitations':limitations})
    citations=[{'title':'Iowa Environmental Mesonet airport observations','url':'https://mesonet.agron.iastate.edu/request/download.phtml','role':'Historical EDDF METAR; true wind direction and knots. Archive has limited quality control.'},{'title':'Open-Meteo Previous Runs API','url':'https://open-meteo.com/en/docs/previous-runs-api','role':'Fixed lead-time archives from past forecasts, not reanalysis.'},{'title':'Open-Meteo DWD ICON API','url':'https://open-meteo.com/en/docs/dwd-api','role':'Live numerical weather forecast at 50.0379N, 8.5622E.'},{'title':'NOAA Aviation Weather Center Data API','url':'https://aviationweather.gov/data/api/','role':'Latest EDDF observation snapshot.'},{'title':'Umwelthaus current operating direction and forecast','url':'https://www.umwelthaus.org/fluglaerm/anwendungen-service/aktuelle-betriebsrichtung-und-prognose/','role':'Current operating direction sourced to DFS; no historical bulk labels obtained.'},{'title':'FraAlliance AI Week 2026 hackathon case, user supplied PDF','url':None,'role':'Challenge proxy thresholds. These are configurable challenge assumptions, not authoritative aviation limits.'}]
    citations.extend([
        {'title':'OurAirports runway coordinates','url':'https://ourairports.com/data/','role':'Public-domain EDDF runway endpoints and dimensions. True north up; displayed widths enlarged for readability.'},
        {'title':'OpenStreetMap terminal geometry','url':'https://www.openstreetmap.org/copyright','role':'Copyright OpenStreetMap contributors, ODbL 1.0. Terminal geometry and source feature IDs are in fra-airfield.json.'},
        {'title':'Frankfurt Airport official map','url':'https://www.frankfurt-airport.com/en/at-the-airport/orientation/airport-map.html','role':'Current terminal context, checked 30 October 2026: Terminal 3 in use, Terminal 2 closed. Not historical terminal status.'},
    ])
    jsonwrite('citations.json',citations)

if __name__=='__main__':main()
