"""Marine data viewer for Bangladesh waters.

Reads only prepared files under data/ (see docs/data_contract.md). All wording comes from docs/screen_spec.md.
The map tab runs as a Streamlit fragment and the data overlay is sent to the map as a separate layer, so picking a
variable, a depth or a month updates the map and chart in place instead of reloading the whole page.
"""
import base64
import io
import json
import warnings
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
# Short names shown in the panel (the catalogue keeps the full Copernicus long names)
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
LOG_SCALE_IDS = {"CHL", "KD490", "chl_bgc", "nppv", "phyc"}  # guide Step 5: chlorophyll on a log scale

st.set_page_config(page_title="Bangladesh Marine Data Viewer", layout="wide")


# ------------------------------------------------------------------ loaders (cached so the slider is fast)
@st.cache_resource
def open_grid(var_id):
    """Open one NetCDF file once per server and keep it in memory, north-up latitude."""
    path = DATA / "netcdf" / f"{var_id}_monthly.nc"
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
    return catalogue


@st.cache_data
def load_boundary():
    return json.loads((DATA / "boundary" / "bd_maritime_boundary.geojson").read_text())


@st.cache_resource
def boundary_shape(_geojson):
    return shape(_geojson["features"][0]["geometry"])


@st.cache_data
def load_timeseries(var_id, depth=None):
    """Boundary-wide monthly stats. 2D variables: the delivered CSV. Depth variables: computed from the NetCDF
    at the chosen depth so the chart always matches the map."""
    if depth is None:
        df = pd.read_csv(DATA / "timeseries" / f"{var_id}_boundary_stats.csv")
        df["date"] = pd.to_datetime(df["date"])
        return df
    da = open_grid(var_id).sel(depth=depth)
    vals = da.values.reshape(da.shape[0], -1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        df = pd.DataFrame({
            "date": pd.to_datetime(da.time.values), "mean": np.nanmean(vals, 1), "min": np.nanmin(vals, 1),
            "max": np.nanmax(vals, 1), "std": np.nanstd(vals, 1), "n_cells": np.isfinite(vals).sum(1)})
    return df[df["n_cells"] > 0].reset_index(drop=True)


def make_norm(vmin, vmax, log_scale):
    if log_scale:
        return mcolors.LogNorm(vmin=max(vmin, 1e-4), vmax=vmax)
    return mcolors.Normalize(vmin=vmin, vmax=vmax)


def _merc_y(lat):
    return np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))


@st.cache_data(max_entries=1024)
def render_slice(var_id, month_str, depth, cmap_name, vmin, vmax, log_scale):
    """One month (and depth) as a coloured PNG, resampled to Web-Mercator rows so it lines up with the basemap."""
    da = open_grid(var_id)
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

for k, v in {"panel_open": False, "selected_var_id": None, "last_click": None}.items():
    st.session_state.setdefault(k, v)

st.markdown(
    "<style>.block-container{padding-top:2rem}"
    "@media (max-width:640px){.block-container{padding-left:.75rem;padding-right:.75rem}h3{font-size:1.25rem}}"
    "</style>",
    unsafe_allow_html=True,
)


def base_map():
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
    m.fit_bounds([[b_miny - 0.2, b_minx - 0.2], [b_maxy + 0.2, b_maxx + 0.2]])
    # Chrome draws a focus rectangle around a clicked Leaflet shape; hide it
    m.get_root().header.add_child(folium.Element("<style>.leaflet-interactive:focus{outline:none}</style>"))
    return m


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

    meta = next((v for v in catalogue if v["id"] == st.session_state.selected_var_id), None)
    depth = None
    if meta:
        if meta["depths"]:
            dkey = f"depth_{meta['id']}"
            st.session_state.setdefault(dkey, meta["depths"][0])
            depth = st.session_state[dkey]
        ts_df = load_timeseries(meta["id"], depth)
        months = ts_df["date"].dt.strftime("%Y-%m").tolist()
        mkey = f"month_{meta['id']}"
        if st.session_state.get(mkey) not in months:
            st.session_state[mkey] = months[-1]
        selected_month = st.session_state[mkey]

    # ---------------------------------------------------------- Screens 1 and 3: map, depth, slider, legend
    with map_col:
        layer = folium.FeatureGroup(name="data")
        if meta:
            uri, bounds = render_slice(meta["id"], selected_month, depth,
                                       meta["colormap"], meta["vmin"], meta["vmax"], meta["log_scale"])
            ImageOverlay(image=uri, bounds=bounds, opacity=0.85).add_to(layer)

        out = st_folium(base_map(), feature_group_to_add=layer, use_container_width=True, height=560,
                        returned_objects=["last_clicked"], key="main_map")

        click = out.get("last_clicked") if out else None
        if click and click != st.session_state.last_click:
            st.session_state.last_click = click
            if inside(click, boundary_poly) and not st.session_state.panel_open:
                st.session_state.panel_open = True
                st.rerun(scope="fragment")

        if meta:
            if meta["depths"]:
                st.select_slider("Depth", options=meta["depths"], key=f"depth_{meta['id']}",
                                 format_func=depth_label,
                                 help="Depth below the sea surface. The map and the chart change together.")
            st.select_slider("Month", options=months, key=f"month_{meta['id']}",
                             help="Step through months. The map and the chart marker change together.")
            lg, note = st.columns([1, 1.3])
            with lg:
                st.image(render_legend(meta["display_label"], meta["display_unit"], meta["colormap"],
                                       meta["vmin"], meta["vmax"], meta["log_scale"]), width=420)
            with note:
                st.caption("Empty cells: no data. Satellite ocean colour has gaps in the June–September monsoon "
                           "because of cloud cover." if meta["satellite"] else "Empty cells: outside the boundary.")

    # ---------------------------------------------------------- chart, CSV and citation
    if not meta:
        return
    st.divider()
    sel_ts = pd.Timestamp(selected_month + "-01")
    label, unit = meta["display_label"], meta["display_unit"]
    export = ts_df.assign(date=ts_df["date"].dt.strftime("%Y-%m-%d"))
    if depth is not None:
        export.insert(1, "depth_m", depth)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ts_df["date"], y=ts_df["max"], mode="lines", line=dict(width=0),
                             showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=ts_df["date"], y=ts_df["min"], mode="lines", line=dict(width=0), fill="tonexty",
                             fillcolor="rgba(3,105,161,0.13)", name="Min–max range"))
    fig.add_trace(go.Scatter(x=ts_df["date"], y=ts_df["mean"], mode="lines+markers", name="Monthly mean",
                             line=dict(color="#0369a1", width=2), marker=dict(size=3)))
    sel_y = ts_df.loc[ts_df["date"] == sel_ts, "mean"]
    if not sel_y.empty:
        fig.add_trace(go.Scatter(x=[sel_ts], y=[sel_y.iloc[0]], mode="markers", name="Selected month",
                                 marker=dict(color="#dc2626", size=11, symbol="diamond")))
    fig.add_vline(x=sel_ts, line_dash="dash", line_color="#dc2626")
    title = f"{label}: boundary-wide monthly mean" + (f" at {depth_label(depth)}" if depth is not None else "")
    fig.update_layout(
        title=title, xaxis_title="Month", yaxis_title=f"{label} ({unit})",
        yaxis_type="log" if meta["log_scale"] else "linear", yaxis_dtick=1 if meta["log_scale"] else None,
        height=400, margin=dict(l=20, r=20, t=50, b=20), legend=dict(orientation="h", y=-0.22),
    )
    st.plotly_chart(fig, width="stretch")

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
