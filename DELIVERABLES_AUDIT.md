# Deliverables audit

Overall: **partially achieved**. No claim of accuracy against actual airport operations.

Frozen coefficients rescored from raw METAR and archived ICON; all saved confusion counts, accuracy and Brier scores reproduced within 1e-12. No retraining or retuning.

## 1. Hourly ML forecast through 48 hours — PARTIAL

48 hourly probabilities for RWY18 wind usability, OD07/25 and direction scores; first predicted change hour; baseline alongside ML.

**Remaining:** Actual runway status and switch timing are unvalidated. OD accuracy beats rules at 1h/6h but loses at 24h/48h. Direction Brier improves at all four leads; closure recall at 50% is zero. Intermediate leads reuse nearest 1/6/24/48h model.

## 2. Self-sourced public data and citations — MET

49,600 EDDF METAR reports combined with archived DWD ICON forecasts. Public sources and raw request URLs preserved; current direction is separately sourced to Umwelthaus/DFS.

**Remaining:** Bulk historical operating-direction and RWY18 availability records were not obtained; this limits the target, not the public-data collection deliverable.

## 3. Held-out quality at 1h, 6h and 24h — PARTIAL

Chronological train/validation/test splits; 72h gaps; train-only scaling; validation-only regularization; verified held-out metrics at required horizons.

**Remaining:** Evaluation measures weather proxies. Archive offsets predate origin by at least 18h, but exact run delivery and METAR arrival timestamps are unavailable. Backtest uses older forecasts than live inference. No operational or switch-event timing score.

## 4. Repository, model card and jury forecasts — PARTIAL

Public code repository, one-page model card, 48-hour CSV export and historical replay command.

**Remaining:** Jury dates have not been supplied. No jury forecast submission or comparison with actually flown directions can be claimed. Historical replay is retrospective, not evidence of an as-issued forecast.

## Verified direction-proxy comparison

| Lead | Hours | ML accuracy | Rules accuracy | Gain (pp) | ML Brier | Rules Brier |
|---|---:|---:|---:|---:|---:|---:|
| 1h | 3432 | 98.40% | 94.61% | +3.79 | 0.0111 | 0.0539 |
| 6h | 3273 | 93.46% | 91.78% | +1.68 | 0.0473 | 0.0822 |
| 24h | 3250 | 88.92% | 90.68% | -1.75 | 0.0818 | 0.0932 |
| 48h | 3243 | 86.52% | 87.73% | -1.20 | 0.1028 | 0.1227 |

Brier is probability error (lower is better), accuracy uses a 50% class threshold. Scores are on identical comparable rows. Higher probability skill does not establish better closure detection. At 50%, all four closure classifiers detect 0 of 5 positive test hours. Three scheduled-hour positives support the alert comparison; these may be correlated.

## Forecast-time evidence

Origins use past observations without future interpolation; scaling is fitted on training rows and regularization on validation rows. Fixed archive offsets have at least 18h nominal lead before each origin. Provider documentation establishes the offset convention, not exact delivery timestamps. METAR observation timestamps do not prove report arrival times. Retrospective model generation in October does not prove forecasts were issued in April. A prospective frozen submission or exact run/availability archive is still required.

## Improvements in this revision

- Replaced schematic runway placement with geographically referenced runway and terminal geometry.
- Added explicit four-deliverable audit and comparable baseline accuracy gains.
- Next-change detection includes a transition in the first forecast hour; exports include direction score and next change.
- Added a downloadable one-page PDF model card and reproducible frozen-model audit.

No model coefficients or alert thresholds were changed by this audit. Existing improvements include both alert priorities and the independent Europe/Berlin 05:00–23:00 scheduling layer.

## Complete the jury submission

1. Obtain the jury issue dates, issue times, timezone and required file schema.
2. Freeze the model before each untouched jury origin and preserve weather retrieval/run timestamps.
3. Export the 48 hourly predictions, direction score and predicted change time.
4. Join verified operating-direction/RWY18 status labels and report actual-operations accuracy, probability error, closure detection and switch timing separately.

Sources: [IEM](https://mesonet.agron.iastate.edu/request/download.phtml), [Open-Meteo Previous Runs](https://open-meteo.com/en/docs/previous-runs-api), [DWD ICON via Open-Meteo](https://open-meteo.com/en/docs/dwd-api), [NOAA AWC](https://aviationweather.gov/data/api/), [Umwelthaus / DFS](https://www.umwelthaus.org/fluglaerm/anwendungen-service/aktuelle-betriebsrichtung-und-prognose/). Challenge thresholds: supplied FraAlliance PDF, section 3.
