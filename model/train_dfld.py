"""Fit independent DFLD direction models under the predeclared chronological plan.
Never changes model.json, metrics.json or RWY18 coefficients/normalizers.
"""
from pathlib import Path
import json, hashlib
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from train import ROOT, OUT, observations, forecasts, feature_matrix, fit_logistic, predict, scores

BASE_INDICES=[0,1,2,3,4,5,6,7,8,9,10,11,13,14]
BASE_NAMES=['nwpEastFrom','nwpNorthFrom','nwpSpeed','nwpGust','nwpTailwind18','nwpCrosswindGust18','nwpHeadwind07','obsEastFrom','obsNorthFrom','obsGust','obsEastTrend3h','obsNorthTrend3h','hourSin','hourCos']
EXTRA_NAMES=['boundedHeadwind07','forecastOriginHeadwindInteraction','absForecastEast','absForecastNorth','forecastEastGustInteraction']


def direction_features(x,kind):
    base=x[:,BASE_INDICES]
    if kind=='weather-linear':return base
    origin_head=x[:,7]*np.sin(np.radians(70))+x[:,8]*np.cos(np.radians(70))
    return np.column_stack([base,np.tanh(x[:,6]/5),np.clip(x[:,6]*origin_head/25,-25,25),np.abs(x[:,0]),np.abs(x[:,1]),np.clip(x[:,0]*x[:,3]/20,-100,100)])


def rule_predictions(nwp,times,origin_state,horizon,lead):
    state=origin_state.astype(int).copy();since=np.full(len(times),-1);missing=np.zeros(len(times),bool)
    for step in range(1,horizon+1):
        t=times-pd.Timedelta(hours=horizon-step)
        w=nwp.reindex(t)[[f'wind_speed_10m_previous_day{lead}',f'wind_direction_10m_previous_day{lead}']].to_numpy(float)
        valid=np.isfinite(w).all(axis=1);missing|=~valid
        tail=-w[:,0]*np.cos(np.radians(w[:,1]-np.where(state==1,70,250)))
        adverse=(tail>1e-9)&valid
        since=np.where(adverse&(since<0),step,since)
        switch=adverse&((tail>=10)|((step-since)*60>30))
        state=np.where(switch,1-state,state);since=np.where(~adverse|switch,-1,since)
    return state,missing


def interval(times,bounds):
    return (times>=pd.Timestamp(bounds[0]))&(times<pd.Timestamp(bounds[1]))


def block_interval(y,new,old,times):
    frame=pd.DataFrame({'date':times.tz_convert('Europe/Berlin').date,'brier':(old-y)**2-(new-y)**2,
                        'accuracy':((new>=.5)==y).astype(float)-((old>=.5)==y).astype(float)})
    daily=frame.groupby('date').agg({'brier':['sum','count'],'accuracy':'sum'})
    a=daily.to_numpy();rng=np.random.default_rng(20261030); draws=rng.integers(0,len(a),size=(1000,len(a)))
    sums=a[draws].sum(axis=1);b=sums[:,0]/sums[:,1];acc=sums[:,2]/sums[:,1]
    return {'days':len(a),'draws':1000,'brierImprovement95':np.quantile(b,[.025,.975]).tolist(),
            'accuracyGainPercentagePoints95':(np.quantile(acc,[.025,.975])*100).tolist()}


def main():
    plan=json.loads((ROOT/'model/dfld-experiment-plan.json').read_text())
    history=json.loads((OUT/'dfld.json').read_text(encoding='utf-8'))
    clock=json.loads((OUT/'dfld-time-audit.json').read_text(encoding='utf-8'))
    if history['schemaVersion']!=2 or history['requestedPeriod']!=plan['dataWindowLocal']:
        raise ValueError('History does not match the declared experiment window')
    if clock['inferredTimezone']!='Europe/Berlin' or clock['summary']['matchingBins']!=240:
        raise ValueError('Required empirical clock audit is missing')
    legacy_bytes=(OUT/'model.json').read_bytes();legacy=json.loads(legacy_bytes)
    label_rows=[{'time':b['timeUtc'],'y':int(b['operatingDirection']=='07')}
                for d in history['days'] for b in d['directionBins']
                if b['eligibleForModel'] and b['sourceTime'].endswith(':00')]
    labels=pd.DataFrame(label_rows);labels['time']=pd.to_datetime(labels.time,utc=True)
    labels=labels.set_index('time').sort_index()
    if not labels.index.is_unique:raise ValueError('Duplicate UTC targets')
    obs,obs_counts=observations();nwp=forecasts();models={};reports=[];fixtures=[];test_rows=[]
    times=labels.index.intersection(obs.index).intersection(nwp.index)
    for horizon,lead in {1:1,6:1,24:2,48:3}.items():
        origin_times=times-pd.Timedelta(hours=horizon);origins=obs.reindex(origin_times)
        weather=nwp.reindex(times)[[f'{v}_previous_day{lead}' for v in ['wind_speed_10m','wind_direction_10m','wind_gusts_10m']]].to_numpy(float)
        full_x=feature_matrix(weather,origins,times);y=labels.reindex(times).y.to_numpy(float)
        rules,missing=rule_predictions(nwp,times,origins.od07.fillna(0).to_numpy(),horizon,lead)
        valid=np.isfinite(full_x).all(axis=1)&~missing
        t=times[valid];x=full_x[valid];y=y[valid];rules=rules[valid];origin=origins.iloc[np.flatnonzero(valid)];wx=weather[valid]
        masks={k:interval(t,plan[k+'Utc']) for k in ['train','validation','test']}
        train,val,test=masks['train'],masks['validation'],masks['test']
        if min(train.sum(),val.sum(),test.sum())<100:raise ValueError('Insufficient eligible rows')
        candidates=[]
        for kind in plan['candidates']['featureSets']:
            features=direction_features(x,kind);mean=features[train].mean(axis=0);scale=features[train].std(axis=0);scale=np.where(scale<1e-6,1,scale)
            z=(features-mean)/scale
            for l2 in plan['candidates']['l2']:
                coef=fit_logistic(z[train],y[train],l2);p=predict(z,coef)
                candidates.append({'kind':kind,'l2':l2,'loss':float(np.mean((p[val]-y[val])**2)),
                                   'coef':coef,'p':p,'mean':mean,'scale':scale})
        chosen=min(candidates,key=lambda c:c['loss'])
        # Selection is finalized on validation before the following test scores.
        p=chosen['p'];oldspec=legacy['models'][str(horizon)];c=oldspec['classifiers']['od07']
        old=predict((x-oldspec['mean'])/oldspec['scale'],np.array([c['intercept']]+c['weights']))
        climate=np.repeat(y[train].mean(),len(y))
        metrics={name:scores(y[test],values[test]) for name,values in [('dfldModel',p),('legacyModel',old),('weatherRules',rules),('climatology',climate)]}
        local=t.tz_convert('Europe/Berlin');scheduled=test&(local.hour>=5)&(local.hour<23)
        scheduled_metrics={name:scores(y[scheduled],values[scheduled]) for name,values in [('dfldModel',p),('legacyModel',old),('weatherRules',rules)]}
        report={'horizonHours':horizon,'trainRows':int(train.sum()),'validationRows':int(val.sum()),'testRows':int(test.sum()),
                'testCandidateHours':int(interval(times,plan['testUtc']).sum()),'testCoverage':float(test.sum()/interval(times,plan['testUtc']).sum()),
                'trainingEastHours':int(y[train].sum()),'validationEastHours':int(y[val].sum()),
                'selectedFeatureSet':chosen['kind'],'selectedL2':chosen['l2'],'validationBrier':chosen['loss'],
                'validationCandidates':[{'featureSet':c['kind'],'l2':c['l2'],'brier':c['loss']} for c in candidates],
                'targets':metrics,'scheduledHours':scheduled_metrics,
                'uncertaintyVsLegacy':block_interval(y[test],p[test],old[test],t[test]),
                'uncertaintyVsRules':block_interval(y[test],p[test],rules[test],t[test]),
                'brierImprovementVsLegacy':metrics['legacyModel']['brier']-metrics['dfldModel']['brier'],
                'accuracyGainVsLegacyPp':100*(metrics['dfldModel']['accuracy']-metrics['legacyModel']['accuracy']),
                'nominalMinimumForecastAgeAtOriginHours':lead*24-horizon}
        reports.append(report)
        models[str(horizon)]={'horizonHours':horizon,'featureSet':chosen['kind'],'featureNames':BASE_NAMES+(EXTRA_NAMES if chosen['kind']=='weather-nonlinear' else []),
                            'mean':chosen['mean'].tolist(),'scale':chosen['scale'].tolist(),'intercept':float(chosen['coef'][0]),
                            'weights':chosen['coef'][1:].tolist(),'l2':chosen['l2'],'validationBrier':chosen['loss']}
        for i in np.flatnonzero(test):
            test_rows.append({'validTimeUtc':t[i].isoformat(),'originUtc':(t[i]-pd.Timedelta(hours=horizon)).isoformat(),'horizonHours':horizon,
                              'actualDirection':'07' if y[i] else '25','p07':float(p[i]),'legacyP07':float(old[i]),'weatherRuleDirection':'07' if rules[i] else '25'})
        for i in np.flatnonzero(test)[::max(1,int(test.sum())//5)][:5]:
            o=origin.iloc[i];s,d,g=wx[i]
            fixtures.append({'horizon':horizon,'row':{'time':t[i].isoformat(),'windSpeed':s,'windDirection':d,'windGust':g},
                'observation':{'windSpeed':o.sknt,'windDirection':o.drct,'windGust':o.gust,'eastTrend3h':o.eastTrend3h,'northTrend3h':o.northTrend3h},
                'initialOD':'07' if o.od07 else '25','p07':float(p[i]),'features':direction_features(x[[i]],chosen['kind'])[0].tolist()})
        print(json.dumps({'horizon':horizon,'n':int(test.sum()),'chosen':chosen['kind'],'l2':chosen['l2'],
                          'accuracy':{k:round(v['accuracy'],4) for k,v in metrics.items()},'brier':{k:round(v['brier'],4) for k,v in metrics.items()}}),flush=True)
    generated=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    artifact={'version':'2.0.0','name':'FRA DFLD Direction v2','generatedAt':generated,'targetBasis':'DFLD-reported operating direction',
              'algorithm':'Horizon-specific L2 logistic regression; validation-selected wind feature set',
              'models':models,'split':plan,'legacyClosureModelSha256':hashlib.sha256(legacy_bytes).hexdigest(),
              'limitations':['Direction labels are DFLD-reported Fraport-based half-hour bins; exact switch timing is not known.',
                'Europe/Berlin time basis is empirically checked; DST transition day is excluded.',
                'DFLD records are targets only. Exact weather delivery timestamps are unavailable; evaluation is retrospective.',
                'Six months cover a limited seasonal range; correlated hourly rows and few switch events limit generalization.',
                'Closure model and alert policies are unchanged. No actual RWY18 closure labels were obtained.',
                'Probabilities are fitted scores, not operational certainty. Intermediate leads use the nearest tested horizon.']}
    metrics={'generatedAt':generated,'modelVersion':artifact['version'],'dataPeriod':history['requestedPeriod'],'days':len(history['days']),
             'knownHalfHourBins':sum(d['directionCoverageBins'] for d in history['days']), 'excludedDates':plan['excludedLocalDates'],
             'targetDefinition':plan['target'],'split':plan,'horizons':reports,'limitations':artifact['limitations'],
             'legacyModelSha256':artifact['legacyClosureModelSha256'],'observationCounts':obs_counts,
             'historySha256':hashlib.sha256((OUT/'dfld.json').read_bytes()).hexdigest()}
    for name,value in [('direction-model.json',artifact),('direction-metrics.json',metrics),('direction-test-predictions.json',test_rows)]:
        (OUT/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    (ROOT/'model/dfld-parity-fixture.json').write_text(json.dumps(fixtures,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    assert (OUT/'model.json').read_bytes()==legacy_bytes,'Legacy closure artifact changed'


if __name__=='__main__':main()
