"""Evaluate two fixed alert policies against frozen weather-proxy labels.

Run: python model/evaluate_alerts.py
Only writes dist/data/alert-policies.json. Does not train or modify coefficients.
Thresholds are sensitivity settings fixed before this replay, not optimized on
the validation/test outcomes. Validation has only zero or one closure hour.
Scheduled-hours evaluation is 05:00 <= Europe/Berlin local time < 23:00.
The 23:00–05:00 restriction is independent of wind and is never a scored true
positive. Night restrictions do not change the underlying weather prediction.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json

import numpy as np
import pandas as pd

from train import OUT, observations, forecasts, feature_matrix, predict

# Fixed product choices. Do not search these thresholds using the test set.
POLICIES = {
    'catchMore': {
        'label': 'Catch more closures',
        'threshold': 0.01,
        'thresholdPercent': 1,
        'description': 'Alert at a closure score of at least 1%, or whenever forecast wind limits are exceeded.',
    },
    'reduceFalseAlarms': {
        'label': 'Reduce false alarms',
        'threshold': 0.10,
        'thresholdPercent': 10,
        'description': 'Alert at a closure score of at least 10%, or whenever forecast wind limits are exceeded.',
    },
}


def score(y, alert):
    y = np.asarray(y, dtype=bool)
    alert = np.asarray(alert, dtype=bool)
    tp = int(np.sum(y & alert))
    fp = int(np.sum(~y & alert))
    tn = int(np.sum(~y & ~alert))
    fn = int(np.sum(y & ~alert))
    n = len(y)
    return {
        'n': n,
        'positiveHours': int(y.sum()),
        'negativeHours': int((~y).sum()),
        'alertHours': int(alert.sum()),
        'confusion': {'tp': tp, 'fp': fp, 'tn': tn, 'fn': fn},
        'recall': tp / (tp + fn) if tp + fn else None,
        'precision': tp / (tp + fp) if tp + fp else None,
        'falsePositiveRate': fp / (fp + tn) if fp + tn else None,
        'alertsPer1000Hours': 1000 * (tp + fp) / n if n else None,
        'falseAlarmsPer1000Hours': 1000 * fp / n if n else None,
        'missedClosureHours': fn,
    }


def evaluate_group(times, y, p, baseline, mask):
    selected_times = times[mask]
    selected_y = y[mask]
    selected_p = p[mask]
    selected_baseline = baseline[mask]
    output = {
        'n': int(mask.sum()),
        'positiveHours': int(selected_y.sum()),
        'firstValidTime': selected_times.min().isoformat() if len(selected_times) else None,
        'lastValidTime': selected_times.max().isoformat() if len(selected_times) else None,
        'baseline': score(selected_y, selected_baseline),
        'policies': {},
        'closureProxyHours': [],
    }
    for policy_id, policy in POLICIES.items():
        model_alert = selected_p >= policy['threshold']
        combined = model_alert | selected_baseline
        assert np.all(combined[selected_baseline]), 'A deterministic wind restriction must never be suppressed.'
        metrics = score(selected_y, combined)
        metrics.update({
            'threshold': policy['threshold'],
            'modelOnlyMetrics': score(selected_y, model_alert),
            'overrideOnlyAlertHours': int(np.sum(selected_baseline & ~model_alert)),
            'bothTriggersAlertHours': int(np.sum(selected_baseline & model_alert)),
        })
        output['policies'][policy_id] = metrics
    sensitive = output['policies']['catchMore']
    selective = output['policies']['reduceFalseAlarms']
    assert selective['alertHours'] <= sensitive['alertHours']
    assert selective['confusion']['fp'] <= sensitive['confusion']['fp']
    for i in np.flatnonzero(selected_y):
        output['closureProxyHours'].append({
            'timeUTC': selected_times[i].isoformat(),
            'timeBerlin': selected_times[i].tz_convert('Europe/Berlin').isoformat(),
            'closureScore': float(selected_p[i]),
            'forecastWindLimitExceeded': bool(selected_baseline[i]),
            'alerts': {key: bool(selected_p[i] >= policy['threshold'] or selected_baseline[i]) for key, policy in POLICIES.items()},
        })
    return output


def verify_schedule_boundaries():
    # Winter and summer 05:00/23:00 boundaries use local clock time.
    cases = [
        ('2026-01-15T03:59:00Z', False), ('2026-01-15T04:00:00Z', True),
        ('2026-01-15T21:59:00Z', True), ('2026-01-15T22:00:00Z', False),
        ('2026-07-15T02:59:00Z', False), ('2026-07-15T03:00:00Z', True),
        ('2026-07-15T20:59:00Z', True), ('2026-07-15T21:00:00Z', False),
    ]
    for utc_time, expected in cases:
        local = pd.Timestamp(utc_time).tz_convert('Europe/Berlin')
        assert (5 <= local.hour < 23) == expected, (utc_time, local)


def main():
    verify_schedule_boundaries()
    model_bytes = (OUT / 'model.json').read_bytes()
    model = json.loads(model_bytes)
    recorded_metrics = json.loads((OUT / 'metrics.json').read_text(encoding='utf8'))
    reference = {row['horizonHours']: row for row in recorded_metrics['horizons']}
    obs, counts = observations()
    nwp = forecasts()
    horizons = []
    for key, spec in sorted(model['models'].items(), key=lambda item: int(item[0])):
        horizon = int(key)
        lead = spec['archiveLeadHours'] // 24
        times = obs.index.intersection(nwp.index)
        origin_times = times - pd.Timedelta(hours=horizon)
        # Fixed archived forecast offset predates every forecast origin.
        assert lead * 24 > horizon
        origins = obs.reindex(origin_times)
        wx = nwp.reindex(times)[[f'{v}_previous_day{lead}' for v in ['wind_speed_10m', 'wind_direction_10m', 'wind_gusts_10m']]].to_numpy(float)
        x = feature_matrix(wx, origins, times)
        targets = obs.reindex(times)[['closed18', 'od07']].to_numpy(float)
        valid = np.isfinite(x).all(axis=1) & np.isfinite(targets).all(axis=1)
        x, targets, times, wx = x[valid], targets[valid], times[valid], wx[valid]
        y = targets[:, 0].astype(bool)
        z = (x - np.asarray(spec['mean'])) / np.asarray(spec['scale'])
        classifier = spec['classifiers']['closed18']
        coef = np.array([classifier['intercept']] + classifier['weights'])
        p = predict(z, coef)
        baseline = (wx[:, 0] * np.cos(np.radians(wx[:, 1])) >= 15) | (np.abs(wx[:, 2] * np.sin(np.radians(wx[:, 1] - 180))) > 40)
        local_hours = times.tz_convert('Europe/Berlin').hour.to_numpy()
        scheduled = (local_hours >= 5) & (local_hours < 23)
        partitions = {
            'validation': (times >= pd.Timestamp('2026-01-04', tz='UTC')) & (times < pd.Timestamp('2026-04-01', tz='UTC')),
            'test': (times >= pd.Timestamp('2026-04-04', tz='UTC')) & (times < pd.Timestamp('2026-10-30', tz='UTC')),
        }
        # Replay must reproduce the original, frozen evaluation cohort and score.
        test = partitions['test']
        old = reference[horizon]['targets']['closed18']['model']
        assert int(test.sum()) == old['n']
        assert int(y[test].sum()) == old['positiveEvents']
        assert abs(float(np.mean((p[test] - y[test]) ** 2)) - old['brier']) < 1e-12
        entry = {'horizonHours': horizon, 'archiveLeadHours': lead * 24}
        for split, mask in partitions.items():
            entry[split] = {
                'allHours': evaluate_group(times, y, p, baseline, mask),
                'scheduledHours': evaluate_group(times, y, p, baseline, mask & scheduled),
                'nightHoursExcludedFromScheduledEvaluation': int(np.sum(mask & ~scheduled)),
                'nightClosureProxyHoursExcluded': int(np.sum(mask & ~scheduled & y)),
                'nightScheduleRestrictionsScoredAsTruePositives': 0,
            }
        horizons.append(entry)
        for scope in ['allHours', 'scheduledHours']:
            group = entry['test'][scope]
            print(horizon, 'h', scope, f"n={group['n']}, closure hours={group['positiveHours']}", {
                policy: {'detected': m['confusion']['tp'], 'falseAlarms': m['confusion']['fp'], 'alertsPer1000Hours': round(m['alertsPer1000Hours'], 2)}
                for policy, m in group['policies'].items()
            }, flush=True)
    output = {
        'version': '1.0.0',
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'modelVersion': model['version'],
        'modelSha256': sha256(model_bytes).hexdigest(),
        'targetBasis': 'weather-derived RWY18 closure-proxy hours; not actual airport closure events',
        'thresholdSelection': 'Fixed sensitivity settings (1% and 10%), declared before this replay. No search, tuning or policy selection on validation/test results. The original model test results were already available; this is a policy comparison on that existing holdout, not a new untouched experiment.',
        'policyDefinitions': {key: {**policy, 'deterministicWindOverride': True, 'comparison': 'closureScore >= threshold OR forecastWindLimitExceeded'} for key, policy in POLICIES.items()},
        'windLimits': {'tailwind18Kn': 15, 'tailwindComparison': '>=', 'crosswindGustKn': 40, 'crosswindComparison': '>', 'runwayHeadingTrue': 180},
        'schedule': {
            'timezone': 'Europe/Berlin', 'startHour': 5, 'endHour': 23,
            'startInclusive': True, 'endExclusive': True,
            'definition': '05:00 <= local valid time < 23:00; local DST is respected.',
            'scope': 'Requested scheduled-flight planning window; exceptional/night flights are outside this planning assumption.',
            'nightRestriction': '23:00–05:00 local is shown independently of weather. Do not emit a scheduled-flight wind alert or count a night restriction as a successful weather-closure prediction.',
            'allHoursEvaluation': 'Weather-only diagnostic over all valid hours, without adding night restrictions to targets or predictions.',
            'scheduledHoursEvaluation': 'Both predictions and weather targets restricted to the scheduled-flight window. Night samples excluded from every metric denominator.',
        },
        'split': {key: model[key] for key in ['trainPeriod', 'validationPeriod', 'testPeriod', 'purgeHours']},
        'counts': counts,
        'horizons': horizons,
        'limitations': [
            'Only five positive held-out closure-proxy hours per horizon, potentially correlated within weather episodes. Counts are hours, not independent closure events.',
            'Validation contains zero or one positive closure-proxy hour, too little to establish a stable optimal sensitivity/false-alarm trade-off.',
            'Closure scores are uncalibrated logistic outputs. A threshold of 1% or 10% is a sensitivity setting, not a verified operational closure probability or optimal cost ratio.',
            'Historical airport closure and operational-direction labels are unavailable. These metrics only evaluate the weather-derived challenge proxy.',
            'Missing METAR gusts use sustained wind, and variable/missing wind directions are excluded, which can undercount dangerous conditions.',
            'Fixed-lead archived ICON inputs are older than live forecast inputs; live results may differ. Coefficients and original train/validation/test splits are frozen.',
            'A deterministic forecast wind restriction always overrides either ML threshold. Night schedule restriction is handled separately and is never scored as a true positive.',
            'With zero positive hours recall is null; with zero alert hours precision is null. No large-sample confidence claim is made.',
        ],
        'verification': {
            'frozenModelUnchanged': sha256((OUT / 'model.json').read_bytes()).hexdigest() == sha256(model_bytes).hexdigest(),
            'originalTestCountsAndBrierReproduced': True,
            'scheduleWinterSummerBoundaryChecks': True,
            'windOverrideNeverSuppressed': True,
            'higherThresholdCannotIncreaseFalseAlarms': True,
        },
    }
    destination = OUT / 'alert-policies.json'
    destination.write_text(json.dumps(output, indent=2, allow_nan=False), encoding='utf8')
    print('Wrote', destination)


if __name__ == '__main__':
    main()
