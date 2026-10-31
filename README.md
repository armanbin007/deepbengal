# Bangladesh Marine Data Viewer (CanyonWatch)

A web map that works like the Copernicus Marine viewer, but only for Bangladesh's maritime boundary.
The map opens on the boundary; clicking it opens a panel of every dataset we hold for those waters; picking one
draws it on the map with a month slider and a time-series chart.

> **Hackathon compliance:** pre-work (scope, data contract, screen spec, boundary, catalogue, sample rows) was
> committed on Oct 27–28. The app (`app/app.py`) is being built during the event, Oct 29–31.

## Pre-work (Oct 27–28)
| Document | Guide step |
|---|---|
| `docs/scope.md` | Step 1: scope decisions |
| `docs/data_contract.md` | Step 5: file layout, columns, catalogue fields, variables |
| `docs/screen_spec.md` | Step 6: three screens, every label and tooltip |
| `docs/developer_plan.md` | Step 7–8: what the developer builds each day and how to check it |
| `data/boundary/bd_maritime_boundary.geojson` | Step 2: Marine Regions Bangladesh EEZ v12 (MRGID 8481) |
| `data/catalogue.json` | Step 3: 26 variables from 4 Copernicus products |
| `data/netcdf/`, `data/timeseries/` | Step 5: full data delivered Oct 30 (26 variables, to mid-2026) |

## Progress
| Day | Status |
|---|---|
| Oct 29: map, click, panel | ✅ done |
| Oct 30: full data, overlays with legend, depth selector, month slider, chart with selected month, CSV download, citation, in-place updates | ✅ done |
| Oct 30: U-Net 12-month forecasts for all 26 variables (mentor suggestion), shown on the slider and chart | ✅ done |
| Oct 30: Copernicus-style pixel inspector; marine protected area outlines (SoNG, Nijhum Dwip, St. Martin's, Naf) | ✅ done |
| Oct 31: About and methods page, acceptance checklist (17/17 pass), phone and projector test, deploy prep | ✅ done |
| Oct 31: deploy on Streamlit Community Cloud and record the backup video | ⏳ team |

## Timeline
| When | Spec writer | Data person | Developer |
|---|---|---|---|
| Oct 27–28 | Steps 1, 5, 6, sample data | Boundary file, account, test download | Reads spec, sets up repo |
| Oct 29 | Answers questions, methods text | Downloads and cleans all variables | Map, click, panel on sample data |
| Oct 30 | Reviews screens against spec | Delivers final NetCDF, CSV, catalogue | Overlays, slider, chart on real data |
| Oct 31 | Citations, demo script, pitch deck | Fixes data issues | Second click, methods page, testing, deploy |

## Forecasts (U-Net)
One small U-Net per variable predicts the next 12 monthly maps from the last 12, all depth levels together.
It was tested on the last 24 months (hidden from training) against an average-year baseline before the final
model was trained on all months. Scores are in `data/forecast/skill.json`.
```bash
pip install -r model/requirements.txt
python model/train_unet.py            # about 2 hours on a laptop CPU
```

## Run
```bash
pip install -r requirements.txt
streamlit run app/app.py
```
Data downloading and clipping stay outside the app; the site only reads the prepared files in `data/`.

## Deploy (Streamlit Community Cloud)
1. Go to share.streamlit.io and sign in with GitHub.
2. **Create app → Deploy a public app from GitHub**: repository `armanbin007/deepbengal`, branch `main`,
   main file `app/app.py`. Under **Advanced settings** choose Python 3.12.
3. Click **Deploy**. The first build takes a few minutes; `requirements.txt` and `.streamlit/config.toml` are read
   automatically. The app uses about 230 MB at start-up, well inside the free tier.
4. Open the link on a phone and on the demo projector, then record the 2-minute backup video
   (`docs/demo_script.md`).

## Acceptance checklist (Oct 31, real data)
| # | Check | Result |
|---|---|---|
| 1 | Page opens on the boundary with no other layer | ✅ |
| 2 | Clicking the boundary opens the panel (clicks outside ignored) | ✅ |
| 3 | All 26 variables listed with unit, years and source | ✅ |
| 4 | Choosing a variable draws it with a legend showing the unit | ✅ |
| 5 | Month slider changes the map in under 2 s | ✅ about 0.3 s |
| 6 | Chart shows the same variable and marks the selected month | ✅ |
| 7 | CSV download gives the chart data (with forecast rows) | ✅ |
| 8 | Source citation shown | ✅ |
| 9 | Depth selector changes map and chart | ✅ |
| 10 | Forecast months and note shown | ✅ |
| 11 | Four MPA outlines with legend | ✅ |
| 12 | Pixel inspector: value, series, profile, depth–time section, MPA name | ✅ |
| 13 | Methods page: products with DOIs, outside sources with licences, forecast scores | ✅ |
| 14 | Phone (390 px), projector 720p and 1080p: works, no sideways scroll | ✅ (deployed link still to test) |

## Sources and licences
Copernicus Marine Service products (DOIs in `data/catalogue.json`); Marine Regions boundary (CC BY 4.0).
Marine protected area outlines were digitised by Mohammad Azharul Islam (Islam et al., *Bangladesh Maritime Journal* 9(1),
227–250, https://doi.org/10.70279/bmj-v7-i1-1046). Biodiversity was dropped from scope on 28 Oct because it is not a Copernicus Marine product.
