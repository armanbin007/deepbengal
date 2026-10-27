# Bangladesh Maritime Data Viewer (CanyonWatch Project)

A lightweight Streamlit web app for exploring monthly Copernicus Marine surface data
(ocean colour, physics, chemistry, wind) and OBIS/GBIF biodiversity records inside
the Bangladesh maritime zone (Territorial Sea + EEZ).

> **Hackathon compliance:** this repository follows the 4-phase staged build plan.
> The Oct 27–28 pre-work contains only the spec, data contract, boundary and 3-row
> sample data. The application (`app/app.py`) is built during the event, Oct 29–31.

## Build schedule

| Phase | Date | Scope |
|---|---|---|
| 0 | Oct 27–28 (pre-work) | Spec, data contract, boundary GeoJSON, 3-row sample CSVs, ETL script |
| 1 | Oct 29 | Locked map + boundary click + searchable side data panel |
| 2 | Oct 30 | Real clipped NetCDF/CSV data, raster overlays, month slider, Plotly chart, CSV export |
| 3 | Oct 31 | Biodiversity layer, click-to-sample grid cell, About & Methods tab, deploy |

## Data contract

- **Boundary:** `data/boundary/bd_maritime_boundary.geojson` (EPSG:4326). Built from `iho.zip`
  (Marine Regions IHO "Bay of Bengal" sea area, CC-BY 4.0) by clipping it to an approximate
  Bangladesh maritime polygon. The coastline edge is real; the seaward edges are approximate and
  **not** the legal EEZ delimitation (ITLOS 2012 / PCA 2014). Swap in the Marine Regions EEZ
  layer if exact limits are needed.
- **Download bbox:** 88.5°E–93.0°E, 15.0°N–22.8°N (boundary + 0.5° margin).
- **No uploads:** the app reads only pre-clipped files. Total data footprint target is under 20 MB.
- **Catalogue:** `data/catalogue.json`, 11 variables across 4 Copernicus products:

| Group | Variables | Product | DOI |
|---|---|---|---|
| Optics and plankton | CHL, KD490, ZSD | OCEANCOLOUR_GLO_BGC_L4_MY_009_108 | 10.48670/moi-00283 |
| Physics | thetao, so, zos, mlotst | GLOBAL_MULTIYEAR_PHY_001_030 | 10.48670/moi-00021 |
| Chemistry | o2, ph | GLOBAL_MULTIYEAR_BGC_001_029 | 10.48670/moi-00019 |
| Wind | wind_speed, stress | WIND_GLO_PHY_CLIMATE_L4_MY_012_003 | 10.48670/moi-00181 |

- **File layout:**
  - `data/netcdf/<var>_monthly.nc`: monthly surface grid, dims `(time, latitude, longitude)`
  - `data/timeseries/<var>_boundary_stats.csv`: columns `date, mean, min, max, std, n_cells`
  - `data/biodiversity/occurrences.csv`: columns `species, latitude, longitude, year, source`

## Data pipeline

```bash
pip install -r requirements.txt
python prepare_data.py --mode day0     # Oct 27-28: boundary + 3-row samples
python prepare_data.py --mode sample   # fallback: 60-month synthetic data for all variables
copernicusmarine login                 # then:
python prepare_data.py --mode real     # real Copernicus subsets, clipped to the boundary
```

## Run the app (from Oct 29)

```bash
streamlit run app/app.py
```

Run from the repo root; the app reads `data/` with relative paths.

## Licences

Copernicus Marine Service products (see DOIs above); Marine Regions boundary (CC-BY 4.0);
OBIS and GBIF occurrence records (CC-BY 4.0).
