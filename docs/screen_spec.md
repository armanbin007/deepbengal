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
| Month slider tooltip | Step through months. The map and the chart marker change together. |
| Chart title | {label}: boundary-wide monthly mean (+ " at {depth} m" for depth variables) |
| Chart x axis | Month |
| Chart y axis | {label} ({unit}) |
| Chart series | Monthly mean · Min–max range · Selected month |
| Download button | Download chart data (CSV) |
| Citation button | Source citation |
| Citation text | E.U. Copernicus Marine Service Information (CMEMS). {product_title} ({product_id}), dataset {dataset_id}. DOI: {doi}. Accessed {today}. |
| Second-click hint | Click a point inside the boundary to add that grid cell's series to the chart. |
| Grid-cell series name | Grid cell {lat}°N {lon}°E |
| Remove grid cell button | Remove grid cell |
| Grid cell without data | No data in that grid cell for {label}. |

## About and methods page
Lists every Copernicus product with its DOI and every outside source with its licence (see the app).
