# Deliverables audit

Overall: **partially achieved**. Direction now has DFLD-reported operational labels; RWY18 still uses weather proxies.

## 1. Hourly ML forecast through 48 hours — PARTIAL

48 hourly probabilities, direction scores and first predicted change hour. Direction v2 is trained on six months of DFLD reports and beats weather rules on identical held-out rows at 1/6/24/48h.

**Remaining:** Confirmed RWY18 status and switch-event timing are unvalidated. Versus v1, 24h accuracy is unchanged and 24h/48h Brier regress. Intermediate leads reuse the nearest measured model.

## 2. Self-sourced public data and citations — MET

49,600 METAR reports, archived ICON forecasts and 183 DFLD direction days (8,784 half-hour bins), with citations, retrieval times and raw source hashes.

**Remaining:** Actual RWY18 closure labels and exact source delivery times remain unavailable. Movement detail covers only 27–29 October.

## 3. Held-out quality at 1h, 6h and 24h — PARTIAL

Reported-direction evaluation at 1/6/24/48h with chronological splits, 72h gaps, train-only scaling, validation-only selection and paired daily-block uncertainty. Empirical source-clock audit; ambiguous DST date excluded.

**Remaining:** Retrospective weather delivery is not verified as-issued. Closure evaluation remains proxy-based. Limited seasonal coverage, missing-input exclusions and unvalidated switch timing restrict the claim.

## 4. Repository, model card and jury forecasts — PARTIAL

Public code repository, one-page model card, 48-hour CSV export and historical replay command.

**Remaining:** Jury dates have not been supplied. No jury forecast submission or comparison with actually flown directions can be claimed. Historical replay is retrospective, not evidence of an as-issued forecast.

## Direction v2 evidence


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


## Archived closure and weather-proxy evidence

`dist/data/deliverables.json` retains v1 weather-proxy scores under `horizons`; current direction scores are in `direction-metrics.json`. `python model/audit_deliverables.py` rebuilds the legacy audit. Run this script afterward to restore the combined delivery assessment. No model tuning occurs in either audit.
