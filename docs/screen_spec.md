# Step 6: Screen spec

Every label and tooltip the app shows. The developer copies wording from here and does not invent any.
`{braces}` are filled from `data/catalogue.json` or the data.

## General
| Element | Text |
|---|---|
| Browser tab title | Bangladesh Marine Data Viewer |
| Tab 1 | Map |
| Tab 2 | About and methods |
| Page heading | Marine data viewer for Bangladesh waters |

## Screen 1: Map
- Map zoomed to the boundary, boundary outlined, plain grey basemap, nothing else drawn.
- Panning limited to a small margin around the boundary.

| Element | Text |
|---|---|
| Instruction line | Click the Bangladesh maritime boundary to see the data we hold for these waters. |
| MPA outlines | Dashed outline per marine protected area, one colour each; tooltip: {name} · Area (km²) {area} |
| MPA toggle | Show marine protected areas |
| MPA legend (under the map) | Dashed line in each colour + {name} |
| Boundary tooltip | Bangladesh maritime zone: click to open the data panel |
| Click outside the boundary | (nothing happens; instruction line stays) |

## Screen 2: Data panel (opened by the click)
| Element | Text |
|---|---|
| Zone name | Bangladesh maritime zone (territorial sea + EEZ) |
| Search box label | Search datasets |
| Search box placeholder | e.g. chlorophyll, salinity, wind |
| Group headings | Optics and plankton · Physics · Chemistry · Wind (each followed by the count in brackets) |
| Variable row | {label} ({unit}) · {first year}–{last year} · {source} · {n} depths (only for variables with depth) |
| Variable row tooltip | Show {label} on the map |
| No search match | No dataset matches "{query}". |

## Screen 3: Viewer state (after picking a variable)
| Element | Text |
|---|---|
| Legend title | {label} ({unit}) |
| Legend scale note (log variables) | Log scale |
| Legend note, satellite variables | Empty cells: no data. Satellite ocean colour has gaps in the June–September monsoon because of cloud cover. |
| Legend note, other variables | Empty cells: outside the boundary. |
| Depth slider label (only for variables with depth) | Depth |
| Depth values | {depth} m |
| Depth slider tooltip | Depth below the sea surface. The map and the chart change together. |
| Month slider label (below the map) | Month |
| Forecast months on the slider | {YYYY-MM} (forecast) |
| Month slider tooltip | Step through months. The map and the chart marker change together. Months after the last observation are U-Net forecasts. |
| Legend note, forecast month | Forecast map (U-Net), not an observation. Trained on data up to {last month}. |
| Chart title | {label}: boundary-wide monthly mean (+ " at {depth} m" for depth variables) |
| Chart x axis | Month |
| Chart y axis | {label} ({unit}) |
| Chart series | Monthly mean · Min–max range · U-Net forecast · Forecast 95% range · Selected month |
| Forecast note under the chart | U-Net 12-month forecast ({period}). In a test on {test period}, hidden from training, it beat the average-year baseline by {n}% / did not beat the average-year baseline, so treat this forecast as indicative only. The shaded band is the 95% range of its test errors. |
| Download button | Download chart data (CSV) |
| Citation button | Source citation |
| Citation text | E.U. Copernicus Marine Service Information (CMEMS). {product_title} ({product_id}), dataset {dataset_id}. DOI: {doi}. Accessed {today}. |
| Second-click hint (panel) | Click any point in the sea to inspect that pixel: its value, time series and, for variables with depth, its vertical profile. |
| Map label on the clicked pixel | {lon}°E, {lat}°N · {label}: {value} {unit} · {month} (forecast) · {depth} m |
| Pixel panel heading | Pixel {lon}°E, {lat}°N |
| Pixel panel subtitle | {label} · grid cell nearest to your click · {grid resolution} · inside {MPA name} (when the pixel is inside an MPA) |
| Pixel value | {month} (forecast) · {depth} m → {value} {unit} |
| Pixel charts | Time series at this pixel · {depth} m / Vertical profile · {month} / Depth–time section at this pixel · last 3 years + forecast |
| Stats under each chart | x̄ {mean} ↓ {min} ↑ {max} {unit} |
| Pixel buttons | Close pixel · Download pixel data (CSV) |

## About and methods page
Lists every Copernicus product with its DOI and every outside source with its licence (see the app).
