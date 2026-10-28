# Step 1: Scope decisions

Agreed before the build so nothing changes on day 2.

| # | Decision | Choice | Reason |
|---|---|---|---|
| 1 | Boundary | Full Bangladesh maritime zone (territorial sea + EEZ), not only the Kuakata and Swatch of No Ground corridor | The safer reading of "only the maritime boundary" |
| 2 | Version 1 variables | Chlorophyll-a, KD490, sea surface temperature, salinity, wind stress, dissolved oxygen, pH | Core set from the guide |
| 2b | Added because time allowed | ZSD, currents (uo, vo), sea surface height, mixed layer depth, surface pCO2, net primary production, wind speed, eastward/northward wind and stress | Remaining Step 3 variables |
| 2c | Left out | `dissic` (not in the monthly BGC dataset; the test download confirmed it), satellite SST product (guide: reanalysis `thetao` is enough), hourly wind product WIND_GLO_PHY_L4_MY_012_006 (optional; monthly climate product matches the time step) | |
| 3 | Time resolution | Monthly | Small files, enough for the demo |
| 4 | Depth | Surface layer only for 3D variables (thetao, so, uo, vo, o2, ph, nppv) | Depth selector can come later |
| 5 | Stack | Streamlit + folium (Leaflet) via streamlit-folium | As in the proposal; React needs more than three days |
