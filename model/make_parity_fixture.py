import json
import numpy as np
import pandas as pd
from train import ROOT,OUT,observations,forecasts,feature_matrix,predict
model=json.loads((OUT/'model.json').read_text());obs,_=observations();nwp=forecasts();origin=pd.Timestamp('2026-05-10T06:00:00Z');o=obs.loc[[origin]];fixtures=[]
for h in [1,6,24,48]:
    spec=model['models'][str(h)];day=spec['archiveLeadHours']//24;t=origin+pd.Timedelta(hours=h);weather=nwp.reindex([t])[[f'{v}_previous_day{day}' for v in ['wind_speed_10m','wind_direction_10m','wind_gusts_10m']]].to_numpy(float)
    x=feature_matrix(weather,o,pd.DatetimeIndex([t]));z=(x-spec['mean'])/spec['scale'];r=o.iloc[0];s,d,g=weather[0]
    p={k:float(predict(z,np.array([c['intercept']]+c['weights']))[0]) for k,c in spec['classifiers'].items()}
    fixtures.append({'horizon':h,'row':{'time':t.isoformat(),'windSpeed':s,'windDirection':d,'windGust':g},'observation':{'windSpeed':r.sknt,'windDirection':r.drct,'windGust':r.gust,'eastTrend3h':r.eastTrend3h,'northTrend3h':r.northTrend3h},'initialOD':'07' if r.od07 else '25','features':x[0].tolist(),'p07':p['od07'],'pClosed18':p['closed18']})
(ROOT/'model'/'parity_fixture.json').write_text(json.dumps(fixtures,indent=2))
