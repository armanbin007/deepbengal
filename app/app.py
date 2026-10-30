"""Marine data viewer for Bangladesh waters.

Reads only prepared files under data/ (see docs/data_contract.md) and the U-Net forecasts under data/forecast/
(see model/train_unet.py). All wording comes from docs/screen_spec.md.

The map tab runs as a Streamlit fragment and the data overlay is sent to the map as a separate layer, so picking a
variable, a depth or a month updates the map and chart in place instead of reloading the whole page.
"""
import base64
import io
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import streamlit as st
import folium
from folium.raster_layers import ImageOverlay
from streamlit_folium import st_folium
from shapely.geometry import shape, Point
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FORECAST = DATA / "forecast"
GROUPS = ["Optics and plankton", "Physics", "Chemistry", "Wind"]
ZONE_NAME = "Bangladesh maritime zone (territorial sea + EEZ)"
BASEMAP_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
BASEMAP_ATTR = "Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ"

# Display details per Copernicus product: title for the citation, short source for panel rows, satellite (cloud gaps)
PRODUCT_INFO = {
    "OCEANCOLOUR_GLO_BGC_L4_MY_009_104": (
        "Global Ocean Colour (Copernicus-GlobColour), Bio-Geo-Chemical, L4 (monthly and interpolated) "
        "from Satellite Observations", "Copernicus Marine · satellite ocean colour", True),
    "GLOBAL_MULTIYEAR_PHY_001_030": (
        "Global Ocean Physics Reanalysis", "Copernicus Marine · ocean physics reanalysis", False),
    "GLOBAL_MULTIYEAR_BGC_001_029": (
        "Global Ocean Biogeochemistry Hindcast", "Copernicus Marine · biogeochemistry hindcast", False),
    "WIND_GLO_PHY_CLIMATE_L4_MY_012_003": (
        "Global Ocean Monthly Mean Sea Surface Wind and Stress from Scatterometer and Model",
        "Copernicus Marine · scatterometer wind climatology", False),
}
# Short names shown in the panel (the data person's catalogue keeps the full Copernicus long names)
DISPLAY_LABEL = {
    "CHL": "Chlorophyll-a (satellite)", "KD490": "Turbidity (KD490)", "ZSD": "Water clarity (Secchi depth)",
    "thetao": "Temperature", "so": "Salinity", "uo": "Eastward current", "vo": "Northward current",
    "zos": "Sea surface height", "mlotst": "Mixed layer depth", "bottomT": "Sea floor temperature",
    "chl_bgc": "Chlorophyll (model)", "phyc": "Phytoplankton", "nppv": "Net primary production",
    "o2": "Dissolved oxygen", "ph": "pH", "spco2": "Surface pCO2", "no3": "Nitrate", "po4": "Phosphate",
    "si": "Dissolved silicate", "fe": "Dissolved iron",
    "wind_speed": "Wind speed", "eastward_wind": "Eastward wind", "northward_wind": "Northward wind",
    "eastward_stress": "Eastward wind stress", "northward_stress": "Northward wind stress",
    "wind_stress_magnitude": "Wind stress magnitude",
}
DISPLAY_UNIT = {"degrees_C": "°C", "1e-3": "PSU", "1": "no unit", "milligram m-3": "mg m-3"}
# Marine protected areas: outline colour per area (files in data/mpa/bd_mpas.geojson)
MPA_COLORS = {"Swatch of No Ground MPA": "#e11d48", "Nijhum Dwip MPA": "#16a34a",
              "St. Martin's Island MPA": "#d97706", "Naf MPA": "#7c3aed"}
LOG_SCALE_IDS = {"CHL", "KD490", "chl_bgc", "nppv", "phyc"}

st.set_page_config(page_title="Bangladesh Marine Data Viewer", layout="wide")


# ------------------------------------------------------------------ loaders
@st.cache_resource
def open_grid(var_id, kind="netcdf"):
    """Open one NetCDF file once per server (observed or forecast) and keep it in memory, north-up latitude."""
    path = DATA / "netcdf" / f"{var_id}_monthly.nc" if kind == "netcdf" else FORECAST / f"{var_id}_forecast.nc"
    if not path.exists():
        return None
    with xr.open_dataset(path) as ds:
        da = ds[var_id].load()
    if da.latitude[0] > da.latitude[-1]:
        da = da.isel(latitude=slice(None, None, -1))
    return da


@st.cache_data
def load_catalogue():
    """catalogue.json as delivered by the data person, plus display-only fields for the panel."""
    catalogue = json.loads((DATA / "catalogue.json").read_text())
    skill = load_skill()
    for v in catalogue:
        title, source, satellite = PRODUCT_INFO.get(v["product_id"], (v["product_id"], "Copernicus Marine", False))
        v.setdefault("group", v.get("category"))
        v["display_label"] = DISPLAY_LABEL.get(v["id"], v["label"])
        v["display_unit"] = DISPLAY_UNIT.get(v["unit"], v["unit"])
        v.setdefault("product_title", title)
        v.setdefault("source", source)
        v.setdefault("satellite", satellite)
        v.setdefault("log_scale", v["id"] in LOG_SCALE_IDS and v["vmin"] > 0)
        da = open_grid(v["id"])
        v["depths"] = [float(d) for d in da.depth.values] if da is not None and "depth" in da.dims else []
        v["has_forecast"] = (FORECAST / f"{v['id']}_forecast.nc").exists()
        v["skill"] = skill.get(v["id"])
    return catalogue


@st.cache_data
def load_skill():
    path = FORECAST / "skill.json"
    return json.loads(path.read_text()) if path.exists() else {}


@st.cache_data
def load_boundary():
    return json.loads((DATA / "boundary" / "bd_maritime_boundary.geojson").read_text())


@st.cache_data
def load_mpas():
    path = DATA / "mpa" / "bd_mpas.geojson"
    return json.loads(path.read_text()) if path.exists() else None


@st.cache_resource
def mpa_shapes(_geojson):
    return [(f["properties"]["name"], shape(f["geometry"])) for f in _geojson["features"]] if _geojson else []


@st.cache_resource
def boundary_shape(_geojson):
    return shape(_geojson["features"][0]["geometry"])


def _stats_from_grid(da):
    vals = da.values.reshape(da.shape[0], -1)
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            df = pd.DataFrame({
                "date": pd.to_datetime(da.time.values), "mean": np.nanmean(vals, 1), "min": np.nanmin(vals, 1),
                "max": np.nanmax(vals, 1), "std": np.nanstd(vals, 1), "n_cells": np.isfinite(vals).sum(1)})
    return df[df["n_cells"] > 0].reset_index(drop=True)


@st.cache_data
def load_timeseries(var_id, depth=None):
    """Boundary-wide monthly stats. 2D variables: the delivered CSV. Depth variables: computed from the NetCDF
    at the chosen depth so the chart always matches the map."""
    if depth is None:
        df = pd.read_csv(DATA / "timeseries" / f"{var_id}_boundary_stats.csv")
        df["date"] = pd.to_datetime(df["date"])
        return df
    return _stats_from_grid(open_grid(var_id).sel(depth=depth))


@st.cache_data
def load_forecast_stats(var_id, depth=None):
    path = FORECAST / f"{var_id}_forecast_stats.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    if depth is not None:
        df = df[np.isclose(pd.to_numeric(df["depth"], errors="coerce"), depth)]
    return df.reset_index(drop=True)


def make_norm(vmin, vmax, log_scale):
    if log_scale:
        return mcolors.LogNorm(vmin=max(vmin, 1e-4), vmax=vmax)
    return mcolors.Normalize(vmin=vmin, vmax=vmax)


def _merc_y(lat):
    return np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))


@st.cache_data(max_entries=1024)
def render_slice(var_id, kind, month_str, depth, cmap_name, vmin, vmax, log_scale):
    """One month (and depth) as a coloured PNG, resampled to Web-Mercator rows so it lines up with the basemap."""
    da = open_grid(var_id, kind)
    if depth is not None:
        da = da.sel(depth=depth)
    sl = da.sel(time=pd.Timestamp(month_str), method="nearest")
    lats, lons, arr = sl.latitude.values, sl.longitude.values, sl.values
    dlat = float(np.abs(np.diff(lats)).mean()) / 2 if lats.size > 1 else 0
    dlon = float(np.abs(np.diff(lons)).mean()) / 2 if lons.size > 1 else 0
    south, north = float(lats.min()) - dlat, float(lats.max()) + dlat
    west, east = float(lons.min()) - dlon, float(lons.max()) + dlon

    y = np.linspace(_merc_y(north), _merc_y(south), max(arr.shape[0] * 4, 200))
    target = np.degrees(2 * np.arctan(np.exp(y)) - np.pi / 2)
    idx = np.clip(np.searchsorted(lats, target), 0, len(lats) - 1)
    prev = np.clip(idx - 1, 0, len(lats) - 1)
    idx = np.where(np.abs(lats[prev] - target) < np.abs(lats[idx] - target), prev, idx)
    arr_m = np.repeat(arr[idx], 4, axis=1)

    cmap = plt.get_cmap(cmap_name).copy()
    cmap.set_bad(color=(0, 0, 0, 0))
    rgba = (cmap(make_norm(vmin, vmax, log_scale)(np.ma.masked_invalid(arr_m))) * 255).astype(np.uint8)
    buf = io.BytesIO()
    plt.imsave(buf, rgba, format="png")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii"), [[south, west], [north, east]]


@st.cache_data
def render_legend(label, unit, cmap_name, vmin, vmax, log_scale):
    fig, ax = plt.subplots(figsize=(4.4, 0.6), dpi=150)
    fig.subplots_adjust(left=0.04, right=0.96, top=0.62, bottom=0.42)
    cb = fig.colorbar(plt.cm.ScalarMappable(norm=make_norm(vmin, vmax, log_scale), cmap=cmap_name),
                      cax=ax, orientation="horizontal")
    cb.ax.tick_params(labelsize=6)
    cb.set_label(f"{label} ({unit})" + (" · Log scale" if log_scale else ""), fontsize=7)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True)
    plt.close(fig)
    return buf.getvalue()


@st.cache_data
def valid_cells(var_id):
    """Latitude/longitude of every grid cell that has data at any depth and month."""
    da = open_grid(var_id)
    vals = da.values
    has = np.isfinite(vals).any(axis=tuple(range(vals.ndim - 2)))
    lat2d, lon2d = np.meshgrid(da.latitude.values, da.longitude.values, indexing="ij")
    return lat2d[has], lon2d[has]


def nearest_cell(var_id, lat, lon, max_deg=0.25):
    """Grid cell nearest to a click that has data (a click on the coast snaps to the closest sea cell)."""
    lats, lons = valid_cells(var_id)
    if lats.size == 0:
        return None
    d2 = (lats - lat) ** 2 + ((lons - lon) * np.cos(np.radians(lat))) ** 2
    i = int(np.argmin(d2))
    return (float(lats[i]), float(lons[i])) if d2[i] <= max_deg ** 2 else None


@st.cache_data(max_entries=256)
def pixel_series(var_id, lat, lon):
    """Observed and forecast values at one grid cell: DataFrames indexed by month, one column per depth."""
    def frame(da):
        if da is None:
            return None
        cell = da.sel(latitude=lat, longitude=lon, method="nearest")
        if "depth" in cell.dims:
            df = pd.DataFrame(cell.transpose("time", "depth").values, columns=[float(d) for d in cell.depth.values])
        else:
            df = pd.DataFrame({None: cell.values})
        df.index = pd.to_datetime(cell.time.values)
        return df
    return frame(open_grid(var_id)), frame(open_grid(var_id, "forecast"))


def plotly_scale(cmap_name, n=11):
    cmap = plt.get_cmap(cmap_name)
    return [[i / (n - 1), mcolors.to_hex(cmap(i / (n - 1)))] for i in range(n)]


def stats_line(values, unit):
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if not v.size:
        return "No data"
    return f"x̄ {v.mean():.4g}  ↓ {v.min():.4g}  ↑ {v.max():.4g} {unit}"


def years(first, last):
    return f"{str(first)[:4]}–{str(last)[:4]}"


def inside(click, poly):
    return bool(click) and poly.contains(Point(click["lng"], click["lat"]))


def depth_label(d):
    return f"{d:.1f} m"


# ------------------------------------------------------------------ static parts
catalogue = load_catalogue()
boundary_geojson = load_boundary()
boundary_poly = boundary_shape(boundary_geojson)
b_minx, b_miny, b_maxx, b_maxy = boundary_poly.bounds
mpa_geojson = load_mpas()
mpas = mpa_shapes(mpa_geojson)

for k, v in {"panel_open": False, "selected_var_id": None, "last_click": None, "pixel_click": None,
             "show_mpa": True}.items():
    st.session_state.setdefault(k, v)

st.markdown(
    "<style>.block-container{padding-top:2rem}"
    "@media (max-width:640px){.block-container{padding-left:.75rem;padding-right:.75rem}h3{font-size:1.25rem}}"
    "</style>",
    unsafe_allow_html=True,
)


def base_map(show_mpa=True):
    """Built the same way on every run, so streamlit-folium keeps the browser's map and only swaps the data layer."""
    m = folium.Map(
        location=[(b_miny + b_maxy) / 2, (b_minx + b_maxx) / 2], zoom_start=7, min_zoom=6, max_zoom=10,
        max_bounds=True, min_lat=b_miny - 1.0, max_lat=b_maxy + 1.0, min_lon=b_minx - 1.0, max_lon=b_maxx + 1.0,
        tiles=BASEMAP_URL, attr=BASEMAP_ATTR, zoom_snap=0.25, zoom_delta=0.5,
    )
    folium.GeoJson(
        boundary_geojson, name=ZONE_NAME,
        style_function=lambda x: {"fillColor": "#0ea5e9", "color": "#0369a1", "weight": 2.5, "fillOpacity": 0.05},
        highlight_function=lambda x: {"weight": 4},
        tooltip="Bangladesh maritime zone: click to open the data panel",
    ).add_to(m)
    if show_mpa and mpa_geojson:
        folium.GeoJson(
            mpa_geojson, name="Marine protected areas",
            style_function=lambda f: {"color": MPA_COLORS.get(f["properties"]["name"], "#e11d48"), "weight": 2.5,
                                      "dashArray": "6 4", "fillColor": MPA_COLORS.get(f["properties"]["name"], "#e11d48"),
                                      "fillOpacity": 0.08},
            highlight_function=lambda f: {"weight": 4, "fillOpacity": 0.18},
            tooltip=folium.GeoJsonTooltip(fields=["name", "area_km2"], aliases=["", "Area (km²)"]),
        ).add_to(m)
    m.fit_bounds([[b_miny - 0.2, b_minx - 0.2], [b_maxy + 0.2, b_maxx + 0.2]])
    # Chrome draws a focus rectangle around a clicked Leaflet shape; hide it
    m.get_root().header.add_child(folium.Element("<style>.leaflet-interactive:focus{outline:none}</style>"))
    return m


# ------------------------------------------------------------------ pixel inspector
def pixel_inspector(meta, pixel, depth, sel_ts, selected_month, is_forecast, obs_px, fc_px):
    """Like the Copernicus viewer: value, time series, vertical profile and depth-time section at one pixel."""
    label, unit, lat, lon = meta["display_label"], meta["display_unit"], pixel[0], pixel[1]
    col = depth if depth is not None else None
    log = meta["log_scale"]
    with st.container(border=True):
        h1, h2, h3 = st.columns([2.2, 1.3, 0.8])
        with h1:
            st.markdown(f"#### Pixel {lon:.3f}°E, {lat:.3f}°N")
            in_mpa = [n for n, g in mpas if g.contains(Point(lon, lat))]
            st.caption(f"{label} · grid cell nearest to your click · {meta['grid_resolution']}"
                       + (f" · inside **{', '.join(in_mpa)}**" if in_mpa else ""))
        with h2:
            src = fc_px if is_forecast and fc_px is not None else obs_px
            v = src[col].get(sel_ts, np.nan) if col in src.columns else np.nan
            st.metric(f"{selected_month}{' (forecast)' if is_forecast else ''}"
                      f"{' · ' + depth_label(depth) if depth is not None else ''}",
                      "no data" if not np.isfinite(v) else f"{v:.4g} {unit}")
        with h3:
            if st.button("Close pixel", width="stretch"):
                st.session_state.pixel_click = None
                st.rerun(scope="fragment")

        # 1. time series at this pixel (and depth)
        ts = go.Figure()
        ts.add_trace(go.Scatter(x=obs_px.index, y=obs_px[col], mode="lines", name="Observed",
                                line=dict(color="#0369a1", width=1.6)))
        if fc_px is not None and col in fc_px.columns:
            ts.add_trace(go.Scatter(x=[obs_px.index[-1]] + list(fc_px.index),
                                    y=[obs_px[col].iloc[-1]] + list(fc_px[col]), mode="lines",
                                    name="U-Net forecast", line=dict(color="#7c3aed", width=2, dash="dash")))
        ts.add_vline(x=sel_ts, line_dash="dash", line_color="#dc2626")
        ts.update_layout(title=f"Time series at this pixel{' · ' + depth_label(depth) if depth is not None else ''}",
                         height=280, margin=dict(l=10, r=10, t=40, b=10), yaxis_title=f"{label} ({unit})",
                         yaxis_type="log" if log else "linear", legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(ts, width="stretch", key="px_ts")
        st.caption(stats_line(obs_px[col], unit))

        if meta["depths"]:
            c1, c2 = st.columns(2)
            depths = meta["depths"]
            # 2. vertical profile at the selected month
            with c1:
                src = fc_px if is_forecast and fc_px is not None else obs_px
                prof = src.loc[sel_ts] if sel_ts in src.index else pd.Series(np.nan, index=depths)
                pf = go.Figure()
                pf.add_trace(go.Scatter(x=prof.values, y=depths, mode="lines+markers", name="Profile",
                                        line=dict(color="#0369a1", width=2), marker=dict(size=6)))
                if depth is not None and np.isfinite(prof.get(depth, np.nan)):
                    pf.add_trace(go.Scatter(x=[prof[depth]], y=[depth], mode="markers", name="Selected depth",
                                            marker=dict(color="#dc2626", size=12, symbol="diamond")))
                pf.update_layout(title=f"Vertical profile · {selected_month}", height=340,
                                 margin=dict(l=10, r=10, t=40, b=10), showlegend=False,
                                 xaxis_title=f"{label} ({unit})", yaxis_title="Depth (m)",
                                 xaxis_type="log" if log else "linear")
                pf.update_yaxes(autorange="reversed")
                st.plotly_chart(pf, width="stretch", key="px_profile")
                st.caption(stats_line(prof.values, unit))
            # 3. depth-time section (Hovmöller) at this pixel
            with c2:
                recent = obs_px.iloc[-36:]                       # last 3 years, like the Copernicus viewer
                full = recent if fc_px is None else pd.concat([recent, fc_px])
                z = full[depths].T.values.astype(float)
                if log:
                    with np.errstate(all="ignore"):
                        z = np.log10(np.where(z > 0, z, np.nan))
                zmin, zmax = (np.log10(max(meta["vmin"], 1e-4)), np.log10(meta["vmax"])) if log else (
                    meta["vmin"], meta["vmax"])
                hm = go.Figure(go.Heatmap(
                    x=full.index, y=depths, z=z, colorscale=plotly_scale(meta["colormap"]), zmin=zmin, zmax=zmax,
                    colorbar=dict(title=dict(text=("log10 " if log else "") + unit, side="right"), thickness=10),
                    hovertemplate="%{x|%Y-%m}<br>%{y:.1f} m<br>%{z:.4g}<extra></extra>"))
                if fc_px is not None:
                    hm.add_vline(x=obs_px.index[-1], line_color="#7c3aed", line_dash="dot")
                hm.add_vline(x=sel_ts, line_color="#dc2626", line_dash="dash")
                hm.update_layout(title="Depth–time section at this pixel · last 3 years"
                                       + (" + forecast" if fc_px is not None else ""), height=340,
                                 margin=dict(l=10, r=10, t=40, b=10), yaxis_title="Depth (m)")
                hm.update_yaxes(autorange="reversed")
                st.plotly_chart(hm, width="stretch", key="px_hovmoller")
                st.caption(stats_line(full[depths].values, unit)
                           + ("  · dotted line: forecast starts" if fc_px is not None else ""))

        out = obs_px.copy()
        out.columns = [f"{meta['id']}_{c:.1f}m" if c is not None else meta["id"] for c in out.columns]
        out.insert(0, "type", "observed")
        if fc_px is not None:
            f = fc_px.copy()
            f.columns = out.columns[1:]
            f.insert(0, "type", "forecast")
            out = pd.concat([out, f])
        out.index = out.index.strftime("%Y-%m-%d")
        out.index.name = "date"
        st.download_button("Download pixel data (CSV)", data=out.to_csv().encode("utf-8"),
                           file_name=f"{meta['id']}_pixel_{lat:.3f}N_{lon:.3f}E.csv", mime="text/csv",
                           key="px_csv")


# ------------------------------------------------------------------ map tab (fragment: updates in place)
@st.fragment
def map_tab():
    st.markdown("### Marine data viewer for Bangladesh waters")
    if not st.session_state.panel_open:
        st.info("Click the Bangladesh maritime boundary to see the data we hold for these waters.")

    map_col, panel_col = st.columns([2.2, 1] if st.session_state.panel_open else [1, 0.001])

    # ---------------------------------------------------------- Screen 2: data panel
    if st.session_state.panel_open:
        with panel_col:
            st.markdown(f"#### {ZONE_NAME}")
            query = st.text_input("Search datasets", placeholder="e.g. chlorophyll, salinity, wind")
            q = query.lower().strip()
            matches = [v for v in catalogue if not q or any(
                q in str(v[f]).lower() for f in ("display_label", "label", "id", "group", "source", "display_unit"))]
            sel_group = next((v["group"] for v in catalogue if v["id"] == st.session_state.selected_var_id), None)
            for grp in GROUPS:
                items = [v for v in matches if v["group"] == grp]
                if not items:
                    continue
                with st.expander(f"{grp} ({len(items)})", expanded=bool(q) or sel_group in (None, grp)):
                    for item in items:
                        row = (f"{item['display_label']} ({item['display_unit']}) · "
                               f"{years(item['first_date'], item['last_date'])} · {item['source']}")
                        if item["depths"]:
                            row += f" · {len(item['depths'])} depths"
                        if st.button(row, key=f"btn_{item['id']}", help=f"Show {item['display_label']} on the map",
                                     width="stretch",
                                     type="primary" if st.session_state.selected_var_id == item["id"] else "secondary"):
                            st.session_state.selected_var_id = item["id"]
                            st.rerun(scope="fragment")
            if not matches:
                st.write(f'No dataset matches "{query}".')
            if st.session_state.selected_var_id:
                st.caption("Click any point in the sea to inspect that pixel: its value, time series and, for "
                           "variables with depth, its vertical profile.")
    meta = next((v for v in catalogue if v["id"] == st.session_state.selected_var_id), None)
    depth = None
    obs_months, fc_months = [], []
    if meta:
        if meta["depths"]:
            dkey = f"depth_{meta['id']}"
            st.session_state.setdefault(dkey, meta["depths"][0])
            depth = st.session_state[dkey]
        ts_df = load_timeseries(meta["id"], depth)
        obs_months = ts_df["date"].dt.strftime("%Y-%m").tolist()
        fc_df = load_forecast_stats(meta["id"], depth) if meta["has_forecast"] else None
        fc_months = fc_df["date"].dt.strftime("%Y-%m").tolist() if fc_df is not None and len(fc_df) else []
        months = obs_months + fc_months
        mkey = f"month_{meta['id']}"
        if st.session_state.get(mkey) not in months:
            st.session_state[mkey] = obs_months[-1]
        selected_month = st.session_state[mkey]
        is_forecast = selected_month in fc_months

    # ---------------------------------------------------------- Screens 1 and 3: map, depth, slider, legend
    with map_col:
        layer = folium.FeatureGroup(name="data")
        pixel = None
        if meta:
            uri, bounds = render_slice(meta["id"], "forecast" if is_forecast else "netcdf", selected_month, depth,
                                       meta["colormap"], meta["vmin"], meta["vmax"], meta["log_scale"])
            ImageOverlay(image=uri, bounds=bounds, opacity=0.85 if not is_forecast else 0.75).add_to(layer)
            pc = st.session_state.pixel_click
            if pc:
                pixel = nearest_cell(meta["id"], pc["lat"], pc["lng"])
            if pixel:
                obs_px, fc_px = pixel_series(meta["id"], *pixel)
                src = fc_px if is_forecast and fc_px is not None else obs_px
                col = depth if depth is not None else None
                px_val = src[col].get(pd.Timestamp(selected_month + "-01"), np.nan) if col in src.columns else np.nan
                val_txt = "no data" if not np.isfinite(px_val) else f"{px_val:.4g} {meta['display_unit']}"
                html = (f"<div style='font:13px sans-serif;min-width:170px'><b>{pixel[1]:.3f}°E, {pixel[0]:.3f}°N</b>"
                        f"<br>{meta['display_label']}: <b>{val_txt}</b><br>{selected_month}"
                        f"{' (forecast)' if is_forecast else ''}"
                        f"{' · ' + depth_label(depth) if depth is not None else ''}</div>")
                folium.CircleMarker([pixel[0], pixel[1]], radius=7, color="#ffffff", weight=2, fill=True,
                                    fill_color="#111827", fill_opacity=1,
                                    tooltip=folium.Tooltip(html, permanent=True, direction="right",
                                                           offset=(10, 0))).add_to(layer)

        out = st_folium(base_map(st.session_state.show_mpa), feature_group_to_add=layer, use_container_width=True, height=560,
                        returned_objects=["last_clicked"], key="main_map")

        click = out.get("last_clicked") if out else None
        if click and click != st.session_state.last_click:
            st.session_state.last_click = click
            if inside(click, boundary_poly):
                if not st.session_state.panel_open:
                    st.session_state.panel_open = True
                    st.rerun(scope="fragment")
                elif meta:
                    st.session_state.pixel_click = click
                    st.rerun(scope="fragment")

        if mpas:
            t, chips = st.columns([1.5, 3])
            with t:
                st.toggle("Show marine protected areas", key="show_mpa")
            with chips:
                if st.session_state.show_mpa:
                    st.markdown(" ".join(
                        f"<span style='white-space:nowrap;margin-right:14px;font-size:.85rem'>"
                        f"<span style='display:inline-block;width:18px;border-top:3px dashed {MPA_COLORS.get(n, '#e11d48')};"
                        f"vertical-align:middle;margin-right:5px'></span>{n}</span>" for n, _ in mpas),
                        unsafe_allow_html=True)
                    st.caption("MPA outlines digitised by Mohammad Azharul Islam from the boundaries in Bangladesh "
                               "Maritime Journal 7(1), [doi:10.70279/bmj-v7-i1-1046]"
                               "(https://doi.org/10.70279/bmj-v7-i1-1046).")

        if meta:
            if meta["depths"]:
                st.select_slider("Depth", options=meta["depths"], key=f"depth_{meta['id']}",
                                 format_func=depth_label,
                                 help="Depth below the sea surface. The map and the chart change together.")
            st.select_slider("Month", options=months, key=f"month_{meta['id']}",
                             format_func=lambda m: f"{m} (forecast)" if m in fc_months else m,
                             help="Step through months. The map and the chart marker change together. "
                                  "Months after the last observation are U-Net forecasts.")
            lg, note = st.columns([1, 1.3])
            with lg:
                st.image(render_legend(meta["display_label"], meta["display_unit"], meta["colormap"],
                                       meta["vmin"], meta["vmax"], meta["log_scale"]), width=420)
            with note:
                if is_forecast:
                    sk = meta.get("skill") or {}
                    st.caption(f"Forecast map (U-Net), not an observation. Trained on data up to "
                               f"{sk.get('trained_through', '–')}.")
                else:
                    st.caption("Empty cells: no data. Satellite ocean colour has gaps in the June–September monsoon "
                               "because of cloud cover." if meta["satellite"] else "Empty cells: outside the boundary.")

    # ---------------------------------------------------------- pixel inspector
    if not meta:
        return
    sel_ts = pd.Timestamp(selected_month + "-01")
    label, unit = meta["display_label"], meta["display_unit"]
    if pixel:
        pixel_inspector(meta, pixel, depth, sel_ts, selected_month, is_forecast, obs_px, fc_px)

    # ---------------------------------------------------------- chart, CSV and citation
    st.divider()
    export = ts_df.assign(date=ts_df["date"].dt.strftime("%Y-%m-%d"), type="observed")
    if depth is not None:
        export.insert(1, "depth_m", depth)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ts_df["date"], y=ts_df["max"], mode="lines", line=dict(width=0),
                             showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=ts_df["date"], y=ts_df["min"], mode="lines", line=dict(width=0), fill="tonexty",
                             fillcolor="rgba(3,105,161,0.13)", name="Min–max range"))
    fig.add_trace(go.Scatter(x=ts_df["date"], y=ts_df["mean"], mode="lines+markers", name="Monthly mean",
                             line=dict(color="#0369a1", width=2), marker=dict(size=3)))
    if fc_months:
        fig.add_trace(go.Scatter(x=fc_df["date"], y=fc_df["upper"], mode="lines", line=dict(width=0),
                                 showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=fc_df["date"], y=fc_df["lower"], mode="lines", line=dict(width=0), fill="tonexty",
                                 fillcolor="rgba(124,58,237,0.15)", name="Forecast 95% range"))
        fig.add_trace(go.Scatter(x=pd.concat([ts_df["date"].tail(1), fc_df["date"]]),
                                 y=pd.concat([ts_df["mean"].tail(1), fc_df["mean"]]),
                                 mode="lines+markers", name="U-Net forecast",
                                 line=dict(color="#7c3aed", width=2, dash="dash"), marker=dict(size=4)))
        export = pd.concat([export, pd.DataFrame({
            "date": fc_df["date"].dt.strftime("%Y-%m-%d"), "mean": fc_df["mean"], "forecast_lower": fc_df["lower"],
            "forecast_upper": fc_df["upper"], "type": "forecast"}).assign(
            **({"depth_m": depth} if depth is not None else {}))], ignore_index=True)

    sel_y = None
    if selected_month in obs_months:
        sel_y = ts_df.loc[ts_df["date"] == sel_ts, "mean"].iloc[0]
    elif fc_months:
        sel_y = fc_df.loc[fc_df["date"] == sel_ts, "mean"].iloc[0]
    if sel_y is not None:
        fig.add_trace(go.Scatter(x=[sel_ts], y=[sel_y], mode="markers", name="Selected month",
                                 marker=dict(color="#dc2626", size=11, symbol="diamond")))
    fig.add_vline(x=sel_ts, line_dash="dash", line_color="#dc2626")
    title = f"{label}: boundary-wide monthly mean" + (f" at {depth_label(depth)}" if depth is not None else "")
    fig.update_layout(
        title=title, xaxis_title="Month", yaxis_title=f"{label} ({unit})",
        yaxis_type="log" if meta["log_scale"] else "linear", yaxis_dtick=1 if meta["log_scale"] else None,
        height=400, margin=dict(l=20, r=20, t=50, b=20), legend=dict(orientation="h", y=-0.22),
    )
    st.plotly_chart(fig, width="stretch")

    sk = meta.get("skill")
    if fc_months and sk:
        s = sk.get("skill_vs_climatology")
        verdict = (f"beat the average-year baseline by {s * 100:.0f}%" if s is not None and s > 0
                   else "did not beat the average-year baseline, so treat this forecast as indicative only")
        st.caption(f"U-Net 12-month forecast ({sk['forecast_period']}). In a test on {sk['test_period']}, hidden from "
                   f"training, it {verdict}. The shaded band is the 95% range of its test errors.")

    b1, b2, _ = st.columns([1, 1, 2])
    with b1:
        st.download_button("Download chart data (CSV)", data=export.to_csv(index=False).encode("utf-8"),
                           file_name=f"{meta['id']}{'_' + str(depth) + 'm' if depth is not None else ''}_series.csv",
                           mime="text/csv", width="stretch")
    with b2:
        with st.popover("Source citation", width="stretch"):
            st.write(f"E.U. Copernicus Marine Service Information (CMEMS). {meta['product_title']} "
                     f"({meta['product_id']}), dataset {meta['dataset_id']}. DOI: {meta['doi']}. "
                     f"Accessed {date.today():%d %B %Y}.")
            st.markdown(f"[Product page]({meta['source_url']})")


map_tab()
