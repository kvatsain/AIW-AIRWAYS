# Frankfurt wind model

## Six-month DFLD direction model

Direction v2 uses **183 days (30 April–29 October 2026), 8,784 half-hour DFLD-reported direction bins**. This replaces weather-rule direction labels with reported operations. The new artifact has its own scaling and coefficients; original RWY18 closure coefficients and both alert policies are unchanged. Runway movement counts remain available for 27–29 October only. Zero departures never imply closure.

| Lead | Held-out hours | New accuracy | Original accuracy | Rules accuracy | New Brier | Original Brier | Rules Brier |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1h | 517 | 79.69% | 76.98% | 76.21% | 0.1900 | 0.2186 | 0.2379 |
| 6h | 517 | 80.08% | 75.63% | 76.21% | 0.1965 | 0.2088 | 0.2379 |
| 24h | 521 | 71.79% | 71.79% | 71.02% | 0.2371 | 0.2317 | 0.2898 |
| 48h | 521 | 70.06% | 69.48% | 68.52% | 0.2415 | 0.2308 | 0.3148 |

All three methods use identical actual-direction test rows. Lower Brier is better. The gain is strongest at 1h/6h; 24h accuracy is unchanged and probability scores regress at 24h/48h. Do not compare these scores with v1 weather-proxy scores. No hyperparameters were changed after inspecting test results. The validation-selected models are deployed at all four horizons, including regressions.

UTC target splits: train 30 Apr–31 Aug; validate 4–26 Sep; test 30 Sep–29 Oct 2026, with 72-hour gaps. Feature sets and L2 are selected by validation Brier; train-only scaling. The plan is in `model/dfld-experiment-plan.json`. Weather features use origin-or-earlier METAR and archived ICON, with no DFLD origin feature. Nominal archive offsets predate origin by at least 18h; exact delivery timestamps are unavailable. Test coverage is about 75% after missing/variable inputs are excluded. Correlated-hour uncertainty uses a paired daily-block bootstrap (1,000 draws); full intervals, class counts and reliability bins are in `dist/data/direction-metrics.json`. Six months provide limited seasonal coverage, and live weather is fresher than backtest inputs.

The Europe/Berlin source clock is supported empirically by **240/240 exact METAR matches** across five summer/winter dates. It is not an explicit provider timezone declaration. DFLD does not distinguish the repeated local hour on 25 October; the whole date is retained for display but excluded from UTC model joins. Publication times are unknown, so DFLD is used only as a target. Half-hour reports do not establish exact switch instants. Variable wind can be displayed as 0° in DFLD; the model uses original METAR and excludes variable direction.

```powershell
python scripts/fetch_dfld_history.py --start-date 2026-04-30 --end-date 2026-10-29
python scripts/audit_dfld_timezone.py --metar model/raw/eddf_2026.csv
python model/train_dfld.py
node model/update_direction_snapshot.mjs
python model/update_dfld_delivery.py
python scripts/make_model_card.py
python scripts/make_model_card_pdf.py
node tests/direction-model.mjs
node tests/dfld.mjs
python -m unittest discover -s tests -p "test_dfld*.py"
python model/predict.py --issue-time 2026-10-10T06:00:00Z --hours 48 --output model/prediction.csv
```

Run the weather downloader first if raw archives are absent. The six-month importer uses seven monthly statistics pages and cached raw pages, preserving URLs, retrieval times and hashes. It replaces the old three-day import; do not run `fetch_dfld.py` against the main output, since it produces the older schema. `train_dfld.py` never rewrites the legacy closure artifact. Browser refresh, saved snapshots and CLI replay use direction v2. CLI replay before 27 September is rejected unless `--legacy-direction` is explicitly requested. Historical replay is retrospective, not evidence of an issued forecast.

Sources: [DFLD direction statistics](https://www.dfld.de/Mess/StatWetter.php?RegNr=1&D=29.10.2026), [methodology](https://www.dfld.de/Mess/Language/MessHelpG.html), [IEM METAR](https://mesonet.agron.iastate.edu/request/download.phtml), and [DWD ICON archives](https://open-meteo.com/en/docs/previous-runs-api). DFLD states no open-data license; only selected factual values and derived aggregates are included. Raw pages, flight identifiers and DFLD graphics are excluded; see [DFLD reuse notice](https://www.dfld.de/DFLDimprint.php?L=G).

The dashboard and one-page model card expose the new evaluation, source clock evidence and limitations. Jury dates, exact as-issued weather provenance, confirmed RWY18 closures and switch-event timing validation remain outstanding. The unchanged closure benchmark still detects 0/5 proxy positives at the 50% threshold.

## Archived v1 implementation and benchmarks

The sections below document the original weather-proxy model and earlier UI improvements. Current direction results and reproduction steps are above.


This is an executable research prototype, trained on real public weather. The two labels are **weather-derived challenge proxies**, not recorded airport operations. Only one verified current operating-direction snapshot is available. Historical Fraport/DFS direction and RWY18 status data are required to validate the actual challenge.

## Reproduce

Requires Python 3.11+, NumPy and pandas, plus Node 20+ for the browser-model snapshot.

```powershell
python model/download_data.py
python model/train.py
node model/build_snapshot.mjs
python model/predict.py --legacy-direction --issue-time 2026-05-10T06:00:00Z --hours 48 --output model/prediction.csv
```

Raw inputs and complete request URLs are preserved in `model/raw/`. The downloader uses cached files when present; rename an existing live response before requesting an updated snapshot. `dist/data/model.json` exports portable coefficients; `dist/inference.js` is the exact browser inference implementation. `metrics.json` reports held-out performance and all three baselines: rules on archived forecast, persistence and training climatology. `backtest.json` samples the 24h held-out predictions every twelve hours for charting.

Historical CLI refuses issues before 2026-04-01 because the frozen model uses validation through March 2026. It uses only origin-time observations and older archived forecasts. It does not assert that a forecast was actually issued by this prototype at that historical time. Future jury dates require refreshing input archives and a fresh training cutoff established before the issue time.

## Data and labels

49,600 EDDF METAR reports were retrieved from IEM, spanning 2024-01-01 through 2026-10-30 10:20 UTC. Times are UTC, winds knots and direction degrees **from true north**. Missing/variable direction reports are excluded; direction is never silently converted to north. Missing gusts use the sustained wind, which is a material limitation for gust restrictions. Only 1.36% of reports explicitly contained a gust. At each hour, the most recent observation is used only if at most forty minutes old; no future interpolation is used. Three-hour trends use past observations only.

RWY18 is weather-usable when its sustained tailwind component is below 15 kn and its absolute gust crosswind component is at most 40 kn. Direction starts at 25 and switches under the challenge's 10 kn immediate tailwind or a smaller adverse component persisting more than 30 minutes. Real METAR timestamps support the persistence clock, but observations cannot reveal unobserved variability between reports. A 1e-9 kn numerical epsilon avoids floating-point noise on exactly perpendicular winds. Missing wind or a gap exceeding one hour resets the clock. These challenge assumptions differ from public descriptions of airport policy.

## Training and leakage controls

Separate L2 logistic regressions predict closure and direction07 at1/6/24/48h. Inputs are forecast wind vectors, speed, gust, runway components, current observed vector/gust, past3h trends, current simulated direction, and cyclical valid-hour/year features. Means/scales use training rows only. Regularization is selected by validation Brier score. No class weighting or probability recalibration is applied.

Training:2024–2025. Validation:2026-01-04 through03-31. Test:2026-04-04 through10-29. The72h gaps exclude overlapping future targets at split boundaries. Fixed-lead archived ICON forecasts predate the origin:24h archived lead for1/6h targets,48h for24h targets,72h for48h targets. These are fixed-lead archives rather than complete individual runs; current live inference uses newer ICON forecasts, so test results do not directly establish live performance. Between measured horizons, inference selects the nearest model.

The rules baseline follows the same archived weather sequence from origin to target, retaining origin direction and applying the challenge's persistence logic. A fixed-lead archive combines outputs of different earlier model runs. It is conservative in availability but does not reproduce an exact operational model run.

## Results and honest interpretation

| Horizon | Direction proxy ML accuracy | Archived weather rules | Persistence |
|---|---:|---:|---:|
|1h|98.40%|94.61%|97.23%|
|6h|93.46%|91.78%|90.28%|
|24h|88.92%|90.68%|74.06%|
|48h|86.52%|87.73%|64.20%|

The trained direction model beats the rules baseline at1h and6h, and loses at24h and48h. No hyperparameters were adjusted after seeing this test outcome.

**Closure model fails rare-event detection at the reference0.5 threshold:0 of5 held-out closure-proxy hours detected.** Training contains only28–34 closure hours per horizon; validation has0–1. Its99.8% accuracy mostly reflects the dominant open class and should never be used as the product headline. The dashboard therefore exposes the transparent wind-limit guardrail independently of the ML probability. No operational safety or calibration claim is made.

Brier score, class support, confusion counts, recall, precision and reliability bins are in the JSON. Consecutive hourly samples are correlated, so binomial confidence intervals would be misleading without blocked resampling. This first version has no validated switch-event timing score and no ground-truth operations score.

## Alert policy comparison and flight schedule

`python model/evaluate_alerts.py` evaluates the unchanged fitted coefficients under fixed thresholds: 1% (catch more closures) and 10% (reduce false alarms). Both modes override on a forecast challenge-limit exceedance. These are sensitivity settings; no search on the rare validation/test positives or new model fit is performed. The comparison reuses the known test set. Output: `dist/data/alert-policies.json`, with model hash, support, confusion counts, recall, precision, false-positive rate, alert rates, and validation/test metrics at every horizon.

All-hour weather diagnostics remain separate from scheduled-flight metrics. Scheduled metrics include only valid times in 05:00–23:00 Europe/Berlin, respecting DST, and exclude other hours from every numerator/denominator. Night restrictions are never target closure events. `predict.py` exports raw weather alerts under both modes plus schedule-filtered alerts and local timestamps. It does not infer permission for delayed or exempt flights.

In scheduled-hour testing, catch mode detects 3/3, 2/3, 1/3, 0/3 closure-proxy hours at 1/6/24/48h, with 116/113/73/86 false alarms. Reduce mode detects 0/3 at every horizon with 4/1/0/0 false alarms. Only 0–1 validation positives and three correlated test positive hours support each horizon; these results do not establish operational reliability. See the dashboard for the explicit trade-off and the root README for sourced airport hours and exceptions.

## Importing genuine labels

Supply CSV with `time_utc,rwy18_departures_possible,operating_direction`, where timestamps include `Z` or an explicit offset, eligibility is0/1, and direction is07/25. Preserve unknown status as blank and include source/event timestamps. These data should replace the proxy target columns, be joined by the status in force at each valid time, and be evaluated with the same fixed split and leakage controls. Do not treat an absence of departures as proof that the runway was closed. A new model version and untouched future holdout are required; the present UI does not automatically ingest labels or retrain.

Sources: IEM airport observations, Open-Meteo Previous Runs/DWD ICON, NOAA Aviation Weather Center, and Umwelthaus's DFS-sourced current direction. Full links appear in `dist/data/citations.json`.

## Independent delivery audit

Run `python model/audit_deliverables.py` to re-score the frozen coefficients and baselines from raw inputs. It verifies saved metrics without fitting and generates `dist/data/deliverables.json` and the root audit report. Exact provider delivery and METAR arrival times are unavailable; the nominal archive offset check alone does not prove operational availability. `predict.py` now also exports predicted OD, its direction score, next change time (including a first-hour change), and nominal archive reference time. Change-time scores describe direction at that hour, not a calibrated probability of a switch event. Jury forecasts are still pending the dates.
