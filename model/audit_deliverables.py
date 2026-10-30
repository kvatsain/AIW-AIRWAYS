"""Recompute frozen-model holdout scores and publish the challenge delivery audit.

No fitting, threshold search, or model selection. Run from any working directory.
"""
import hashlib
import json
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from train import OUT, ROOT, observations, forecasts, feature_matrix, predict, rule_baseline, scores


def main():
    model = json.loads((OUT / 'model.json').read_text())
    saved = json.loads((OUT / 'metrics.json').read_text())
    obs, counts = observations()
    nwp = forecasts()
    results = []
    for record in saved['horizons']:
        horizon = record['horizonHours']
        spec = model['models'][str(horizon)]
        lead = spec['archiveLeadHours'] // 24
        times = obs.index.intersection(nwp.index)
        origin_times = times - pd.Timedelta(hours=horizon)
        origins = obs.reindex(origin_times)
        wx = nwp.reindex(times)[[f'{v}_previous_day{lead}' for v in ['wind_speed_10m', 'wind_direction_10m', 'wind_gusts_10m']]].to_numpy(float)
        x = feature_matrix(wx, origins, times)
        targets = obs.reindex(times)[['closed18', 'od07']].to_numpy(float)
        keep = np.isfinite(x).all(axis=1) & np.isfinite(targets).all(axis=1)
        times, x, targets, wx = times[keep], x[keep], targets[keep], wx[keep]
        origins = origins.iloc[np.flatnonzero(keep)]
        test = (times >= pd.Timestamp('2026-04-04', tz='UTC')) & (times < pd.Timestamp('2026-10-30', tz='UTC'))
        z = (x - np.array(spec['mean'])) / np.array(spec['scale'])
        rule_od, missing = rule_baseline(nwp, times, origins, horizon, lead)
        rule_closed = ((wx[:, 0] * np.cos(np.radians(wx[:, 1])) >= 15) | (np.abs(wx[:, 2] * np.sin(np.radians(wx[:, 1] - 180))) > 40)).astype(float)
        assert lead * 24 > horizon
        assert (times[test] - pd.Timedelta(hours=horizon)).min() > pd.Timestamp('2026-04-01', tz='UTC')
        row = {'horizonHours': horizon, 'testRows': int(test.sum()), 'minimumArchiveAgeBeforeOriginHours': lead * 24 - horizon, 'targets': {}}
        for col, target in enumerate(['closed18', 'od07']):
            coef = spec['classifiers'][target]
            probability = predict(z, np.array([coef['intercept']] + coef['weights']))
            comparable = test & (~missing if target == 'od07' else True)
            measured = scores(targets[test, col], probability[test])
            rule = scores(targets[comparable, col], (rule_od if target == 'od07' else rule_closed)[comparable])
            model_same = scores(targets[comparable, col], probability[comparable])
            for name, actual in [('model', measured), ('weatherRules', rule), ('modelOnRulesComparableRows', model_same)]:
                expected = record['targets'][target][name]
                assert actual['n'] == expected['n'] and actual['confusion'] == expected['confusion'], (horizon, target, name)
                for key in ['brier', 'accuracy']:
                    assert abs(actual[key] - expected[key]) < 1e-12, (horizon, target, name, key)
            row['targets'][target] = {
                'modelAccuracy': model_same['accuracy'], 'rulesAccuracy': rule['accuracy'],
                'accuracyGainPercentagePoints': 100 * (model_same['accuracy'] - rule['accuracy']),
                'modelBrier': model_same['brier'], 'rulesBrier': rule['brier'],
                'brierSkillVsRules': 1 - model_same['brier'] / rule['brier'],
                'positiveHours': measured['positiveEvents'], 'modelConfusion': measured['confusion'],
                'rulesConfusion': rule['confusion'], 'comparisonRows': int(comparable.sum()),
            }
        results.append(row)
    report = {
        'auditedAt': datetime.now(timezone.utc).isoformat(),
        'modelSha256': hashlib.sha256((OUT / 'model.json').read_bytes()).hexdigest(),
        'overallStatus': 'partial', 'targetBasis': model['targetBasis'],
        'method': 'Frozen coefficients rescored from raw METAR and archived ICON; all saved confusion counts, accuracy and Brier scores reproduced within 1e-12. No retraining or retuning.',
        'deliverables': [
            {'id': 1, 'title': 'Hourly ML forecast through 48 hours', 'status': 'partial', 'reached': '48 hourly probabilities for RWY18 wind usability, OD07/25 and direction scores; first predicted change hour; baseline alongside ML.', 'remaining': 'Actual runway status and switch timing are unvalidated. OD accuracy beats rules at 1h/6h but loses at 24h/48h. Direction Brier improves at all four leads; closure recall at 50% is zero. Intermediate leads reuse nearest 1/6/24/48h model.'},
            {'id': 2, 'title': 'Self-sourced public data and citations', 'status': 'met', 'reached': f'{counts["rawMetarReports"]:,} EDDF METAR reports combined with archived DWD ICON forecasts. Public sources and raw request URLs preserved; current direction is separately sourced to Umwelthaus/DFS.', 'remaining': 'Bulk historical operating-direction and RWY18 availability records were not obtained; this limits the target, not the public-data collection deliverable.'},
            {'id': 3, 'title': 'Held-out quality at 1h, 6h and 24h', 'status': 'partial', 'reached': 'Chronological train/validation/test splits; 72h gaps; train-only scaling; validation-only regularization; verified held-out metrics at required horizons.', 'remaining': 'Evaluation measures weather proxies. Archive offsets predate origin by at least 18h, but exact run delivery and METAR arrival timestamps are unavailable. Backtest uses older forecasts than live inference. No operational or switch-event timing score.'},
            {'id': 4, 'title': 'Repository, model card and jury forecasts', 'status': 'partial', 'reached': 'Public code repository, one-page model card, 48-hour CSV export and historical replay command.', 'remaining': 'Jury dates have not been supplied. No jury forecast submission or comparison with actually flown directions can be claimed. Historical replay is retrospective, not evidence of an as-issued forecast.'},
        ],
        'temporalAudit': {'archiveOffsetCheckPassed': True, 'scoresReproduced': True, 'minimumArchiveAgeBeforeOriginHours': min(r['minimumArchiveAgeBeforeOriginHours'] for r in results), 'exactAvailabilityTimestampsVerified': False, 'futureUntouchedJuryHoldoutAvailable': False},
        'horizons': results,
        'improvements': ['Replaced schematic runway placement with geographically referenced runway and terminal geometry.', 'Added explicit four-deliverable audit and comparable baseline accuracy gains.', 'Next-change detection includes a transition in the first forecast hour; exports include direction score and next change.', 'Added a downloadable one-page PDF model card and reproducible frozen-model audit.'],
    }
    (OUT / 'deliverables.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    lines = ['# Deliverables audit', '', 'Overall: **partially achieved**. No claim of accuracy against actual airport operations.', '', report['method'], '']
    for d in report['deliverables']:
        lines += [f'## {d["id"]}. {d["title"]} — {d["status"].upper()}', '', d['reached'], '', '**Remaining:** ' + d['remaining'], '']
    lines += ['## Verified direction-proxy comparison', '', '| Lead | Hours | ML accuracy | Rules accuracy | Gain (pp) | ML Brier | Rules Brier |', '|---|---:|---:|---:|---:|---:|---:|']
    for r in results:
        t = r['targets']['od07']
        lines.append(f'| {r["horizonHours"]}h | {r["testRows"]} | {t["modelAccuracy"]:.2%} | {t["rulesAccuracy"]:.2%} | {t["accuracyGainPercentagePoints"]:+.2f} | {t["modelBrier"]:.4f} | {t["rulesBrier"]:.4f} |')
    lines += ['', 'Brier is probability error (lower is better), accuracy uses a 50% class threshold. Scores are on identical comparable rows. Higher probability skill does not establish better closure detection. At 50%, all four closure classifiers detect 0 of 5 positive test hours. Three scheduled-hour positives support the alert comparison; these may be correlated.', '', '## Forecast-time evidence', '', 'Origins use past observations without future interpolation; scaling is fitted on training rows and regularization on validation rows. Fixed archive offsets have at least 18h nominal lead before each origin. Provider documentation establishes the offset convention, not exact delivery timestamps. METAR observation timestamps do not prove report arrival times. Retrospective model generation in October does not prove forecasts were issued in April. A prospective frozen submission or exact run/availability archive is still required.', '', '## Improvements in this revision', '']
    lines += ['- ' + s for s in report['improvements']]
    lines += ['', 'No model coefficients or alert thresholds were changed by this audit. Existing improvements include both alert priorities and the independent Europe/Berlin 05:00–23:00 scheduling layer.', '', '## Complete the jury submission', '', '1. Obtain the jury issue dates, issue times, timezone and required file schema.', '2. Freeze the model before each untouched jury origin and preserve weather retrieval/run timestamps.', '3. Export the 48 hourly predictions, direction score and predicted change time.', '4. Join verified operating-direction/RWY18 status labels and report actual-operations accuracy, probability error, closure detection and switch timing separately.', '', 'Sources: [IEM](https://mesonet.agron.iastate.edu/request/download.phtml), [Open-Meteo Previous Runs](https://open-meteo.com/en/docs/previous-runs-api), [DWD ICON via Open-Meteo](https://open-meteo.com/en/docs/dwd-api), [NOAA AWC](https://aviationweather.gov/data/api/), [Umwelthaus / DFS](https://www.umwelthaus.org/fluglaerm/anwendungen-service/aktuelle-betriebsrichtung-und-prognose/). Challenge thresholds: supplied FraAlliance PDF, section 3.', '']
    (ROOT / 'DELIVERABLES_AUDIT.md').write_text('\n'.join(lines), encoding='utf-8')
    print('Verified frozen model and baselines at 1/6/24/48h; overall deliverables PARTIAL.')


if __name__ == '__main__':
    main()
