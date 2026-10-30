"""Attach the DFLD evaluation to the delivery audit without replacing archived v1 scores."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'dist/data/deliverables.json';a=json.loads(p.read_text())
m=json.loads((ROOT/'dist/data/direction-metrics.json').read_text())
a['targetBasis']='Direction v2: DFLD-reported operations; RWY18 v1: weather-derived challenge proxy'
a['directionEvidence']={'modelVersion':m['modelVersion'],'generatedAt':m['generatedAt'],'metrics':'direction-metrics.json','history':'dfld.json','clockAudit':'dfld-time-audit.json','days':m['days'],'knownHalfHourBins':m['knownHalfHourBins']}
a['archivedBenchmark']='Top-level horizons and method describe archived v1 weather-proxy evaluation only.'
a['deliverables'][0]['reached']='48 hourly probabilities, direction scores and first predicted change hour. Direction v2 is trained on six months of DFLD reports and beats weather rules on identical held-out rows at 1/6/24/48h.'
a['deliverables'][0]['remaining']='Confirmed RWY18 status and switch-event timing are unvalidated. Versus v1, 24h accuracy is unchanged and 24h/48h Brier regress. Intermediate leads reuse the nearest measured model.'
a['deliverables'][1]['reached']='49,600 METAR reports, archived ICON forecasts and 183 DFLD direction days (8,784 half-hour bins), with citations, retrieval times and raw source hashes.'
a['deliverables'][1]['remaining']='Actual RWY18 closure labels and exact source delivery times remain unavailable. Movement detail covers only 27–29 October.'
a['deliverables'][2]['reached']='Reported-direction evaluation at 1/6/24/48h with chronological splits, 72h gaps, train-only scaling, validation-only selection and paired daily-block uncertainty. Empirical source-clock audit; ambiguous DST date excluded.'
a['deliverables'][2]['remaining']='Retrospective weather delivery is not verified as-issued. Closure evaluation remains proxy-based. Limited seasonal coverage, missing-input exclusions and unvalidated switch timing restrict the claim.'
a['improvements']=list(dict.fromkeys(a['improvements']+['Added six months of DFLD direction targets, an independent direction model and actual-label paired evaluation.','Preserved closure coefficients and alerts; exposed longer-horizon probability regressions.']))
p.write_text(json.dumps(a,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
parts=['# Deliverables audit\n\nOverall: **partially achieved**. Direction now has DFLD-reported operational labels; RWY18 still uses weather proxies.\n']
for d in a['deliverables']:parts.append(f"## {d['id']}. {d['title']} — {d['status'].upper()}\n\n{d['reached']}\n\n**Remaining:** {d['remaining']}\n")
parts+=['## Direction v2 evidence\n\n'+(ROOT/'README.md').read_text(encoding='utf-8').split('## Six-month DFLD direction model\n',1)[1].split('## Archived v1 implementation',1)[0]]
parts+=['## Archived closure and weather-proxy evidence\n\n`dist/data/deliverables.json` retains v1 weather-proxy scores under `horizons`; current direction scores are in `direction-metrics.json`. `python model/audit_deliverables.py` rebuilds the legacy audit. Run this script afterward to restore the combined delivery assessment. No model tuning occurs in either audit.\n']
(ROOT/'DELIVERABLES_AUDIT.md').write_text('\n'.join(parts),encoding='utf-8')
print('Updated combined delivery audit; archived v1 scores preserved')
