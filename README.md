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
| Oct 31: methods page, second click (grid cell), testing, deploy | ⏳ |

## Timeline
| When | Spec writer | Data person | Developer |
|---|---|---|---|
| Oct 27–28 | Steps 1, 5, 6, sample data | Boundary file, account, test download | Reads spec, sets up repo |
| Oct 29 | Answers questions, methods text | Downloads and cleans all variables | Map, click, panel on sample data |
| Oct 30 | Reviews screens against spec | Delivers final NetCDF, CSV, catalogue | Overlays, slider, chart on real data |
| Oct 31 | Citations, demo script, pitch deck | Fixes data issues | Second click, methods page, testing, deploy |

## Run (from Oct 29)
```bash
pip install -r requirements.txt
streamlit run app/app.py
```
Data downloading and clipping stay outside the app; the site only reads the prepared files in `data/`.

## Sources and licences
Copernicus Marine Service products (DOIs in `data/catalogue.json`); Marine Regions boundary (CC BY 4.0).
Biodiversity was dropped from scope on 28 Oct because it is not a Copernicus Marine product.
