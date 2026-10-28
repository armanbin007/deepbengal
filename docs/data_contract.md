# Step 5: Data contract

The developer reads only the files below. If the data person delivers anything different, this contract
changes first and the developer is told.

```
data/
  boundary/bd_maritime_boundary.geojson
  netcdf/<variable>_monthly.nc
  timeseries/<variable>_boundary_stats.csv
  catalogue.json
```

## File rules
- **Boundary:** Marine Regions Bangladeshi Exclusive Economic Zone v12 (MRGID 8481), EPSG:4326, lightly simplified.
  Citation: Flanders Marine Institute (2023). Maritime Boundaries Geodatabase: Maritime Boundaries and Exclusive
  Economic Zones (200NM), version 12. https://doi.org/10.14284/632. Licence CC BY 4.0.
- **NetCDF:** one file per variable, dimensions `time`, `latitude`, `longitude`, monthly, surface layer only,
  cells outside the boundary empty (NaN). The data variable is named after the catalogue `id`.
- **Time series CSV columns:** `date` (YYYY-MM-01), `mean`, `min`, `max`, `std`, `n_cells`.
- **catalogue.json:** one entry per variable with `id`, `label`, `unit`, `product_id`, `dataset_id`, `first_date`,
  `last_date`, `grid_resolution`, `colormap`, `vmin`, `vmax`, `doi`, `source_url`
  plus `category` (panel group). The app will derive display-only details (log scale for CHL and nppv, short source
  name, product title) from `id` and `product_id`.

## Variables (19)
| Group | id | Unit | Dataset ID |
|---|---|---|---|
| Optics and plankton | CHL | mg m-3 (log scale) | cmems_obs-oc_glo_bgc-plankton_my_l4-multi-4km_P1M (product OCEANCOLOUR_GLO_BGC_L4_MY_009_104) |
| Optics and plankton | KD490, ZSD | m-1, m | cmems_obs-oc_glo_bgc-transp_my_l4-multi-4km_P1M |
| Physics | thetao, so, uo, vo, zos, mlotst | degrees C, PSU, m s-1, m s-1, m, m | cmems_mod_glo_phy_my_0.083deg_P1M-m |
| Chemistry | o2, ph, spco2, nppv | mmol m-3, no unit, Pa, mg m-3 day-1 | cmems_mod_glo_bgc_my_0.25deg_P1M-m |
| Wind | wind_speed, eastward_wind, northward_wind, eastward_stress, northward_stress, wind_stress_magnitude | m s-1, N m-2 | cmems_obs-wind_glo_phy_my_l4_P1M |

`dissic` is not in the monthly BGC dataset
(confirmed by the test download), so it is left out.

## Day-0 samples (pre-work)
Three sample rows per time-series file (Jan–Mar 2024) so the developer can start before the full files are
committed. The full NetCDF and CSV files go in on Oct 30, as the timeline says.
