# Step 5: Data contract

The developer reads only the files below. If the data person delivers anything different, this contract
changes first and the developer is told.

```
data/
  boundary/bd_maritime_boundary.geojson
  netcdf/<variable>_monthly.nc
  timeseries/<variable>_boundary_stats.csv
  catalogue.json
  forecast/<variable>_forecast.nc          (made by model/train_unet.py)
  forecast/<variable>_forecast_stats.csv
  forecast/skill.json
```

## File rules
- **Boundary:** Marine Regions Bangladeshi Exclusive Economic Zone v12 (MRGID 8481), EPSG:4326, lightly simplified.
  Citation: Flanders Marine Institute (2023). Maritime Boundaries Geodatabase: Maritime Boundaries and Exclusive
  Economic Zones (200NM), version 12. https://doi.org/10.14284/632. Licence CC BY 4.0.
- **NetCDF:** one file per variable, dimensions `time`, (`depth`), `latitude`, `longitude`, monthly, cells outside
  the boundary empty (NaN). The data variable is named after the catalogue `id`. Physics variables keep 9 levels
  (1.5–13.5 m) and biogeochemistry 10 levels (0.5–14 m).
- **Forecast stats CSV columns:** `date`, `depth` (blank for 2D), `mean`, `lower`, `upper`.
- **Time series CSV columns:** `date` (YYYY-MM-01), `mean`, `min`, `max`, `std`, `n_cells`. For depth variables the
  app computes these at the selected depth from the NetCDF, so the chart always matches the map.
- **catalogue.json:** one entry per variable with `id`, `label`, `unit`, `product_id`, `dataset_id`, `first_date`,
  `last_date`, `grid_resolution`, `colormap`, `vmin`, `vmax`, `doi`, `source_url`
  plus `category` (panel group), `has_depth`, `depth_levels`, `source_file`. The app derives display-only details (log scale for CHL and nppv, short source
  name, product title) from `id` and `product_id`.

## Variables (26, data to mid-2026)
| Group | ids | Dataset ID |
|---|---|---|
| Optics and plankton | CHL, KD490, ZSD | cmems_obs-oc_glo_bgc-plankton/transp_my_l4-multi-4km_P1M (OCEANCOLOUR_GLO_BGC_L4_MY_009_104), to 2026-09 |
| Physics | thetao, so, uo, vo (depth) · zos, mlotst, bottomT | cmems_mod_glo_phy_my_0.083deg_P1M-m, to 2026-08 |
| Chemistry | chl_bgc, phyc, nppv, o2, ph, no3, po4, si, fe (depth) · spco2 | cmems_mod_glo_bgc_my_0.25deg_P1M-m, to 2026-08 |
| Wind | wind_speed, eastward/northward wind, eastward/northward stress, wind_stress_magnitude | cmems_obs-wind_glo_phy_my_l4_P1M, to 2026-06 |

`dissic` is not in the monthly BGC dataset
(confirmed by the test download), so it is left out.

## Delivery
Full NetCDF and CSV files for all 26 variables delivered by the data person on Oct 30 (losslessly compressed).
