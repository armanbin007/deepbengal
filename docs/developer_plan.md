# Developer plan (build guide Step 7 and Step 8)

The developer builds `app/app.py` during the event. This file says what to prepare beforehand, what to build each
day, and how to know each part is done. It contains no app code.

## Tonight, Oct 28 (preparation only, no app code)
1. **Read the spec:** `docs/screen_spec.md` (every label), `docs/data_contract.md` (the only files the app reads),
   `docs/scope.md`.
2. **Set up your computer:** Python 3.11+, a virtual environment, then `pip install -r requirements.txt`.
   Check that `streamlit hello` opens in the browser.
3. **Check git:** clone `armanbin007/deepbengal` and confirm you can push.
4. **Accounts:** sign in to Streamlit Community Cloud (share.streamlit.io) with GitHub, for the Oct 31 deploy.
5. **Get the full data from the data person** and keep it on your computer. It goes into the repo on Oct 30.
6. **Skim the docs for the pieces you will use:** folium `Map` (`max_bounds`, `fit_bounds`), streamlit-folium
   `st_folium` (`last_clicked`), folium `ImageOverlay`, `st.cache_data`, `st.select_slider`, Plotly
   `add_vline`, `st.download_button`, `st.popover`.
7. **Check the hackathon rules** on what counts as pre-work.

## Oct 29: map, click, panel (guide 7.1–7.4)
| Build | Done when |
|---|---|
| `app/app.py` with the page title and heading from the spec | Page opens |
| Map zoomed to the boundary, boundary outlined, plain basemap, panning limited to a small margin | Opens on the boundary and shows no other layer |
| Capture the click; open the panel only if the click is inside the polygon | Clicking the boundary opens the panel; clicks outside do nothing |
| Panel built from `catalogue.json`: zone name, search box, groups from `category`, one row per variable showing label, unit, years and source | All 19 variables listed; search filters them |

Commit at the end of the day.

## Oct 30: overlay, slider, chart on real data (guide 7.5–7.7)
| Build | Done when |
|---|---|
| Data person commits the full `data/netcdf` and `data/timeseries` | Files match the data contract |
| Selected variable: take the month's slice from its NetCDF, colour it with the catalogue `colormap`/`vmin`/`vmax` (log scale for CHL and nppv), add as an image overlay | Variable appears on the map |
| Legend from the same values, with the unit and the empty-cells note | Legend shows the unit |
| Month slider below the map; cache the loaded data | Map changes in under 2 seconds |
| Plotly chart of the boundary monthly mean with min–max band and a marker on the selected month | Chart shows the same variable and marks the month |
| "Download chart data (CSV)" and "Source citation" buttons | CSV matches the chart; citation shows product and DOI |

Commit at the end of the day.

## Oct 31: methods, second click, test, deploy (guide 7.9–7.10, Step 8)
| Build | Done when |
|---|---|
| About and methods tab: boundary citation (Marine Regions v12, doi:10.14284/632), every Copernicus product with its DOI, basemap licence, limitations (monsoon cloud gaps, no `dissic`) | Methods page lists every product and outside source |
| Optional second click: nearest grid cell's own series added to the chart and the CSV | Clicking the sea adds a dotted series |
| Run the acceptance checklist on the real data | All items pass |
| Test on a phone and on the demo projector | Works on both |
| Deploy on Streamlit Community Cloud (main file `app/app.py`) | Deployed link opens on a phone |
| Record a 2-minute backup video following the demo script | Video saved |

## Things to watch for
- **Basemap:** CartoDB tiles in folium now need an API key. Use a free plain basemap such as Esri World Light Gray.
- **Overlay position:** NetCDF latitudes are ascending, so flip the image so north is up. Leaflet draws in Web
  Mercator, so resample rows to Mercator spacing or the overlay looks slightly shifted. Make NaN cells transparent.
- **Catalogue fields:** the panel group is `category`. The wind stress variable id is `wind_stress_magnitude`.
  Each NetCDF also has a `spatial_ref` variable; read the variable named after the catalogue `id`.
- **Clicks:** the EEZ polygon follows river channels north of 23°N where there is no ocean data. Ignore clicks
  outside the polygon, and snap a second click to the nearest grid cell that has data.
- **Size:** the full NetCDF files are about 55 MB (largest about 14 MB), inside GitHub's 100 MB per-file limit.
