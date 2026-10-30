# AIW-AIRWAYS — FRA WindLab

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

The sections below document the original weather-proxy model and earlier UI improvements. Current direction results are above.

A responsive Frankfurt Airport forecasting dashboard, built for the FraAlliance AI Week 2026 challenge. It includes a real trained probability model, 48-hour weather forecasts, a geographic airfield map, hourly wind and probability charts, a challenge-rule sandbox, CSV export, validation results, source provenance, and a printable model card.

**Research prototype:** targets are derived from observed weather using the challenge rules. Historical operating-direction and RWY 18 availability records were not obtained. Reported scores therefore do not establish accuracy against actual operations.

## Use locally

No JavaScript dependencies or build step are required. From this folder:

```powershell
python -m http.server 8788 --bind 127.0.0.1 --directory dist
```

Open `http://127.0.0.1:8788`. The initial page uses the included, timestamped real-weather snapshot. Refresh calls the public Open-Meteo DWD ICON endpoint. If a request fails, the existing snapshot remains visible with a failure message. The page needs HTTP serving because it uses JavaScript modules and JSON fetches.

The existing [hosted dashboard](https://frankfurt-wind-lab-thiag.statworx-par-2884.chatgpt.site) has its own access controls. This repository can be run locally without a hosting account. Personal hosting configuration and credentials are excluded.

## Reproduce training and historical forecasts

Python 3.11+, NumPy, pandas and Node.js 20+ are sufficient:

```powershell
python -m pip install -r requirements.txt
python model/download_data.py
python model/train.py
python model/evaluate_alerts.py
node model/build_snapshot.mjs
python model/predict.py --legacy-direction --issue-time 2026-05-10T06:00:00Z --hours 48 --output model/prediction.csv
python scripts/make_model_card.py
node tests/run.mjs
node model/check_inference.mjs
```

See [model/README.md](model/README.md) for chronology, features, labels, baselines, replay constraints and the ground-truth data schema. Raw public-weather downloads are included in `model/raw/`, with request URLs in `model/raw/manifest.json`; the downloader uses cached files. The saved model, metrics and forecasts are included in `dist/data/`. Historical export currently supports the downloaded 2026 holdout period after model selection. Jury dates have not yet been supplied. Do not report the example replay as a submitted jury forecast.

## Results and limits

- Training sources contain 49,600 EDDF METAR reports from January 2024 through October 2026, plus archived DWD ICON forecast data.
- Frozen train/validation/test splits are chronological with 72-hour gaps. Only past observations and forecast archives predating each origin are used as input.
- Direction-proxy classification beats the deterministic weather-rule baseline at 1h and 6h, but loses at 24h and 48h. Full probability and class metrics appear in `dist/data/metrics.json`.
- RWY 18 closure detection is weak: zero of five test closure-proxy hours detected at a 0.5 threshold. The dashboard displays the independent wind-rule limit calculation. High open-class accuracy is not evidence of useful closure detection.
- Live forecasts use fresher numerical-weather inputs than the fixed-lead historical evaluation. Reported test scores are not proof of live accuracy or operational calibration.
- Current METAR and operating-direction observations are saved snapshots. Browser weather refresh updates only ICON. After 90 minutes, origin weather falls back explicitly to modeled current conditions; current direction is inferred from wind unless a recent verified snapshot exists. The operations source date is never silently refreshed.
- Forecasts are hourly. The next shift is the first hourly probability crossing, not a prediction with minute-level precision. Nearest-horizon models are used between measured leads.

## Alert priorities and Frankfurt flight hours

The overview supports **Catch more closures** (closure score ≥1%) and **Reduce false alarms** (≥10%). Both alert whenever forecast tailwind or gust crosswind exceeds the challenge limits. The trained probabilities are unchanged. Thresholds are fixed sensitivity choices, not calibrated costs or tuned optima. The comparison reuses the existing test set whose original scores were already known; it is not a fresh untouched test.

| Lead | Catch: detected / positive hours | Catch: false alarms | Reduce: detected / positive hours | Reduce: false alarms |
|---|---:|---:|---:|---:|
| 1h | 3/3 | 116 | 0/3 | 4 |
| 6h | 2/3 | 113 | 0/3 | 1 |
| 24h | 1/3 | 73 | 0/3 | 0 |
| 48h | 0/3 | 86 | 0/3 | 0 |

These counts cover scheduled hours only; three weather-proxy positive hours do not establish operational reliability. Validation has only 0–1 positives and detection remains weak. The dashboard exposes both all-hour and scheduled-hour counts, precision, misses, and validation support. Complete results and definitions are in `dist/data/alert-policies.json`; reproduce with `python model/evaluate_alerts.py` without retraining.

The separate flight clock uses **Europe/Berlin**, including daylight saving time: scheduled takeoffs and landings 05:00 inclusive to 23:00 exclusive. The 23:00–05:00 night restriction suppresses scheduled-flight alerts but never changes weather probabilities or counts as a detected wind closure. Between 23:00 and midnight, eligible delayed landings may arrive; delayed takeoffs need individual authority permission. From midnight to 05:00, ordinary delayed/early flights are not admitted. Statutory exemptions remain possible. Shoulder-hour restrictions are described without inventing slot availability or flight permission.

Sources: [Fraport operating hours](https://www.fraport.com/en/sustainability/dialog-with-neighbors/noise-and-air/flight-operations/runway-system-and-operating-hours.html) and [Hessen delayed-flight rules](https://wirtschaft.hessen.de/Verkehr/Luftverkehr/Verspaetete-Starts-und-Landungen), checked 30 October 2026. Both the browser CSV and historical CLI export both priorities and the flight-hour layer.

## Sources and assumptions

Historical observations: [Iowa Environmental Mesonet](https://mesonet.agron.iastate.edu/request/download.phtml). Numerical forecasts: [DWD ICON through Open-Meteo](https://open-meteo.com/en/docs/dwd-api) and [Previous Runs](https://open-meteo.com/en/docs/previous-runs-api). Current observation snapshot: [NOAA Aviation Weather Center](https://aviationweather.gov/data/api/). Direction context: [Umwelthaus, citing DFS](https://www.umwelthaus.org/fluglaerm/anwendungen-service/aktuelle-betriebsrichtung-und-prognose/). Weather attribution belongs to the original providers; Open-Meteo data are provided under its published terms and attribution requirements.

The supplied case PDF specifies 15 kt RWY 18 tailwind, 40 kt gust crosswind, a 10 kt immediate direction-change threshold, and persistence beyond 30 minutes. [Fraport's public guidance](https://www.fraport.com/en/business-areas/operations/airside-and-terminal-operations/easterly-and-westerly-operations.html) describes a different 5 kt landing tailwind threshold. The dashboard follows the challenge and does not represent airport operating standards.

The supplied 6m29s audio was transcribed locally. Its requirements support the two targets and 48-hour horizon; exact numeric rules come from the PDF. The recording and supplied PDF are in `references/`; transcript artifacts and review notes are in `research/`. The optional local transcription script uses `requirements-audio.txt`. These source materials are evidence, not instructions to execute.

## Checks performed

Tests cover threshold boundaries, cardinal wind directions, small-tailwind persistence, missing wind, forecast continuity, probability normalization, Python/browser coefficient parity, and evaluation-count integrity. Browser checks cover weather refresh, horizon selection, time zones, scenario controls, navigation, and a verified 48-row CSV export. Desktop and narrow layouts were reviewed.

## Project layout

- `dist/`: the complete static dashboard and trained model assets.
- `model/`: data downloader, training, inference checks and historical replay CLI.
- `tests/`: core behavior checks.
- `scripts/`: generated model-card helper.
- `references/`: the user-supplied challenge PDF and audio recording.
- `research/`: local audio transcript, review notes, and optional transcription script.
- `docs/images/`: dashboard previews.
- `PROJECT_MANIFEST.json`: relative file paths, byte counts and SHA-256 hashes for the imported project after portable line-ending normalization.

## Repository handoff

This import preserves the repository's initial commit and adds the complete working project as of 30 October 2026. The application source comes from Site commit `590ff63862fa9a1d93786d0fc8d6934ef18587f1`; public raw data and briefing materials are included for reproducibility. Dependencies, model-download caches, temporary files, private hosting bindings and authentication data are excluded.

The dashboard works from the included snapshot without Python ML packages. Training and historical replay require the Python requirements above. Local transcription additionally requires `python -m pip install -r requirements-audio.txt`; it downloads the selected Whisper model on first use. Run `python research/transcribe_audio.py base` from the repository root if a new transcript is needed.

Source-provider attribution is retained in the dashboard and documentation. Third-party weather data and briefing materials remain subject to their original terms. Actual runway-operation history and jury test dates have not yet been supplied.

![Dashboard alert modes and Frankfurt flight hours](docs/images/dashboard-jury-preview.png)

## Deliverables audit and geographic map

The challenge is **partially achieved**. See [DELIVERABLES_AUDIT.md](DELIVERABLES_AUDIT.md) and the dashboard's Model & validation audit. Public-data collection and citations are complete. Hourly predictions and scores exist, but ground-truth operating records, validated change timing and jury test-day submissions remain outstanding. Jury dates have not been supplied.

The frozen-model audit independently recomputes saved confusion counts, accuracy and Brier at 1/6/24/48h from raw inputs without refitting. Direction accuracy improves over the weather rules by +3.79/+1.68 percentage points at 1h/6h and declines by 1.75/1.20 points at 24h/48h. Direction Brier improves at all four leads; closure detection remains 0/5 at the 50% threshold. Nominal archive offsets predate origin by at least 18h; exact run delivery and METAR arrival timestamps are unavailable. A retrospective replay is not proof of an as-issued forecast.

This revision adds the four-deliverable audit, a genuine one-page PDF model card, first-hour direction-change detection, and direction score/change-time fields in both CSV exports. The model coefficients and alert thresholds are unchanged.

Airfield Outlook now projects actual runway coordinates with equal metre scale and true north up, eight terminal footprints, T2 location, a scale bar, runway roles, wind-flow arrows and limit highlighting. Expand map for detail. Sources: [OurAirports](https://ourairports.com/data/) (public domain), [OpenStreetMap contributors](https://www.openstreetmap.org/copyright) (ODbL 1.0), and the [official FRA airport map](https://www.frankfurt-airport.com/en/at-the-airport/orientation/airport-map.html). The terminal map reflects 30 October 2026, including Terminal 3 and T2's current closure; it is not a historical replay. Source IDs and licenses are in `dist/data/fra-airfield.json`. Widths are enlarged for clarity. This is geographic context, not a navigation chart.

```powershell
python model/audit_deliverables.py
python -m pip install -r requirements-docs.txt
python scripts/make_model_card_pdf.py
```

The audit requires the public raw files from the repository or downloader. The PDF builder asserts exactly one A4 page. Open `dist/model-card.pdf` or download it from the dashboard. Re-run the audit after training before generating the PDF so stale metrics are caught.

## Satellite reference and detailed airfield context

The forecast map follows the supplied Google Maps picture's visual context while retaining geographic runway coordinates and hourly forecast overlays. It adds 1,419 mapped OpenStreetMap features: 609 taxiway segments, 35 aprons, 66 buildings, two CargoCity districts, the airport boundary, major roads, woodland and water. These are geographic features, not generated scenery. The static layer is bundled locally; it needs no map API key or external tile requests.

`dist/data/fra-context.json` preserves OSM object IDs, source URLs, retrieval time and [ODbL attribution](https://www.openstreetmap.org/copyright). Rebuild it with `python scripts/fetch_fra_context.py`: eight bounded public OSM API queries, 3 m simplification, complete ways and multipolygons only. Eleven incomplete relations were excluded in the bundled snapshot.

The **Satellite reference** tab displays the original user-supplied picture unchanged, including its imagery attribution, and links to the full-size file and Google Maps. It is a static reference, not a georeferenced layer; its western northwest-runway end and southern RWY 18 end are cropped. The forecast map shows all four full runways. Source and usage metadata are in `dist/data/satellite-reference.json`. Forecast models, probabilities and validation metrics are unchanged by this map update.

## 3D Airfield Outlook

The default **3D outlook** projects mapped geographic geometry into an orthographic XYZ scene with raised terminal and airport-building footprints, shaded terrain, and illustrated woodland. It is a self-contained SVG renderer, with no map API key, external renderer or GPU dependency. Cargo districts remain flat. Building heights and tree symbols are illustrative because the source data contains no measured heights; this is not a surveyed digital twin or a terrain-flow simulation.

Rotate the airport, change the viewing angle, toggle or pause wind flow, and step through forecast hours. Cyan wind streams move **toward wind direction +180°**; lime arrows show the predicted runway direction. Calm or missing wind suppresses flow animation. The runway inspector shows surface head/tailwind, gust crosswind, relevant challenge thresholds, the RWY18 weather-proxy usability probability or 07/25 direction, and the independent Frankfurt night restrictions. Reduced-motion preferences disable wind animation. The **2D map** and **Satellite reference** views remain available.

**Save image** exports the current 3D scene as an 1880×1300 PNG with the forecast time and map attribution for jury slides. It is a static forecast illustration, with no live aircraft positions. The weather is one model location shown across the airfield; no local turbulence is inferred. Model coefficients, performance metrics and export-forecast contracts are unchanged.

Run `node tests/airfield-3d.mjs` in addition to `node tests/run.mjs`. Checks cover meteorological wind orientation, projected axes/elevation, all four runway references, wind-limit boundaries, calm/missing wind, layer selection and camera angles. UI verification covers runway selection, camera controls, time stepping, night status, view switching and an exported PNG.

