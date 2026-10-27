"""
Bangladesh Maritime Data Viewer - data pipeline (ETL).

Modes (see handover doc, section 4.2):
  python prepare_data.py --mode day0    # Oct 27-28: boundary GeoJSON + 3-row sample CSVs / 3-month dummy NetCDFs
  python prepare_data.py --mode sample  # Oct 29-30 fallback: 60-month synthetic NetCDFs + CSVs for all 11 variables
  python prepare_data.py --mode real    # Oct 29-30: real Copernicus subsets (run `copernicusmarine login` first)
"""
import os
import json
import zipfile
import argparse
import numpy as np
import pandas as pd
import xarray as xr
import geopandas as gpd
import shapely
from shapely.geometry import Polygon

# Bounding Box for Bangladesh EEZ + 0.5 deg margin
MIN_LON, MAX_LON = 88.5, 93.0
MIN_LAT, MAX_LAT = 15.0, 22.8

# Reproducible synthetic data
RNG = np.random.default_rng(42)


def setup_directories():
    for folder in ["raw", "data/boundary", "data/netcdf", "data/timeseries", "data/biodiversity"]:
        os.makedirs(folder, exist_ok=True)


def build_boundary(zip_path="iho.zip"):
    out_geojson = "data/boundary/bd_maritime_boundary.geojson"
    if os.path.exists(zip_path):
        print(f"Extracting {zip_path} and converting to EPSG:4326 GeoJSON...")
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall("raw/iho_shp")
        shp_files = [f for f in os.listdir("raw/iho_shp") if f.endswith(".shp")]
        if shp_files:
            gdf = gpd.read_file(os.path.join("raw/iho_shp", shp_files[0]))
            gdf = gdf.to_crs("EPSG:4326")
            # iho.zip holds the IHO "Bay of Bengal" sea area; clip it to the Bangladesh maritime zone
            bd_box = Polygon([
                (89.0, 21.8), (89.1, 16.5), (91.2, 16.0),
                (92.3, 20.6), (92.0, 21.8), (89.0, 21.8)
            ])
            gdf["geometry"] = gdf.geometry.intersection(bd_box)
            gdf = gdf[~gdf.is_empty].copy()
            gdf["geometry"] = gdf.geometry.simplify(0.01)
            # Drop clipping slivers (< ~1 km2) so the boundary is one clean polygon
            gdf = gdf.explode(index_parts=False)
            gdf = gdf[gdf.geometry.area > 1e-4].dissolve().reset_index(drop=True)
            gdf["name"] = "Bangladesh Maritime Zone (EEZ & Territorial Sea)"
            gdf = gdf[["name", "geometry"]]
            gdf.to_file(out_geojson, driver="GeoJSON")
            print(f"Saved {out_geojson}")
            return gdf

    print("Generating standard Bangladesh EEZ + Territorial Sea Polygon...")
    bd_eez_coords = [
        (89.08, 21.65), (89.02, 19.50), (89.25, 17.50),
        (90.10, 16.10), (91.40, 17.20), (92.15, 19.80),
        (92.30, 20.65), (91.85, 21.75), (90.50, 21.95),
        (89.08, 21.65)
    ]
    poly = Polygon(bd_eez_coords)
    gdf = gpd.GeoDataFrame(
        {"name": ["Bangladesh Maritime Zone (EEZ & Territorial Sea)"]},
        geometry=[poly],
        crs="EPSG:4326"
    )
    gdf.to_file(out_geojson, driver="GeoJSON")
    return gdf


def build_biodiversity():
    records = [
        {"species": "Bryde's whale (Balaenoptera edeni)", "latitude": 20.85, "longitude": 89.62, "year": 2021, "source": "OBIS (CC-BY 4.0)"},
        {"species": "Bryde's whale (Balaenoptera edeni)", "latitude": 20.62, "longitude": 89.48, "year": 2022, "source": "OBIS (CC-BY 4.0)"},
        {"species": "Irrawaddy dolphin (Orcaella brevirostris)", "latitude": 21.52, "longitude": 89.85, "year": 2023, "source": "GBIF (CC-BY 4.0)"},
        {"species": "Irrawaddy dolphin (Orcaella brevirostris)", "latitude": 21.48, "longitude": 90.15, "year": 2023, "source": "GBIF (CC-BY 4.0)"},
        {"species": "Indo-Pacific finless porpoise (Neophocaena phocaenoides)", "latitude": 21.15, "longitude": 90.45, "year": 2022, "source": "OBIS (CC-BY 4.0)"},
        {"species": "Spinner dolphin (Stenella longirostris)", "latitude": 20.30, "longitude": 89.55, "year": 2020, "source": "OBIS (CC-BY 4.0)"},
        {"species": "Indo-Pacific humpback dolphin (Sousa chinensis)", "latitude": 21.38, "longitude": 91.75, "year": 2021, "source": "GBIF (CC-BY 4.0)"},
        {"species": "Olive Ridley sea turtle (Lepidochelys olivacea)", "latitude": 20.92, "longitude": 92.18, "year": 2024, "source": "GBIF (CC-BY 4.0)"}
    ]
    pd.DataFrame(records).to_csv("data/biodiversity/occurrences.csv", index=False)
    print("Saved data/biodiversity/occurrences.csv")


def generate_datasets(catalogue, boundary_gdf, start_date="2020-01-01", end_date="2024-12-01"):
    dates = pd.date_range(start_date, end_date, freq="MS")
    lats = np.linspace(MIN_LAT, MAX_LAT, 50)
    lons = np.linspace(MIN_LON, MAX_LON, 45)
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    poly = boundary_gdf.geometry.union_all()
    mask = shapely.contains_xy(poly, lon_grid, lat_grid)

    for item in catalogue:
        vid = item["id"]
        vmin, vmax = item["vmin"], item["vmax"]
        mid = (vmin + vmax) / 2.0
        amp = (vmax - vmin) / 4.0

        data_array = np.full((len(dates), len(lats), len(lons)), np.nan, dtype=np.float32)
        stats_rows = []

        for t_idx, dt in enumerate(dates):
            seasonal = np.sin(2 * np.pi * (dt.month / 12.0)) * (amp * 0.6)
            lat_gradient = ((lat_grid - MIN_LAT) / (MAX_LAT - MIN_LAT) - 0.5) * amp
            noise = RNG.normal(0, amp * 0.15, size=lat_grid.shape)
            slice_2d = np.clip(mid + seasonal + lat_gradient + noise, vmin, vmax)
            slice_2d[~mask] = np.nan
            data_array[t_idx] = slice_2d

            valid = slice_2d[~np.isnan(slice_2d)]
            if valid.size == 0:
                continue
            stats_rows.append({
                "date": dt.strftime("%Y-%m-01"),
                "mean": round(float(np.mean(valid)), 4),
                "min": round(float(np.min(valid)), 4),
                "max": round(float(np.max(valid)), 4),
                "std": round(float(np.std(valid)), 4),
                "n_cells": int(valid.size)
            })

        ds = xr.Dataset(
            {vid: (("time", "latitude", "longitude"), data_array)},
            coords={"time": dates, "latitude": lats, "longitude": lons}
        )
        ds[vid].attrs.update({"units": item["unit"], "long_name": item["label"]})
        ds.to_netcdf(f"data/netcdf/{vid}_monthly.nc")
        pd.DataFrame(stats_rows).to_csv(f"data/timeseries/{vid}_boundary_stats.csv", index=False)
        print(f"Prepared {len(dates)}-month NetCDF & CSV for {vid}")


def download_real_copernicus(catalogue, boundary_gdf, start_year="2015-01-01T00:00:00"):
    import copernicusmarine
    import regionmask

    for item in catalogue:
        vid = item["id"]
        ds_id = item["dataset_id"]
        raw_nc = f"raw/{vid}_raw.nc"

        dl_vars = [vid] if vid != "stress" else ["eastward_stress", "northward_stress"]
        depth_kwargs = (
            {"minimum_depth": 0.0, "maximum_depth": 2.0}
            if item["group"] in ["Physics", "Chemistry"] and vid not in ["zos", "mlotst"]
            else {}
        )

        copernicusmarine.subset(
            dataset_id=ds_id,
            variables=dl_vars,
            minimum_longitude=MIN_LON,
            maximum_longitude=MAX_LON,
            minimum_latitude=MIN_LAT,
            maximum_latitude=MAX_LAT,
            start_datetime=start_year,
            end_datetime="2024-12-31T23:59:59",
            output_filename=raw_nc,
            **depth_kwargs
        )

        ds = xr.open_dataset(raw_nc)
        if "depth" in ds.dims:
            ds = ds.isel(depth=0, drop=True)
        if vid == "stress":
            ds["stress"] = np.sqrt(ds["eastward_stress"] ** 2 + ds["northward_stress"] ** 2)

        mask = regionmask.mask_geopandas(boundary_gdf, ds.longitude, ds.latitude)
        clipped = ds[vid].where(mask.notnull())
        clipped.to_netcdf(f"data/netcdf/{vid}_monthly.nc")

        stats = []
        for t in clipped.time:
            arr = clipped.sel(time=t).values
            valid = arr[~np.isnan(arr)]
            dt_str = pd.to_datetime(str(t.values)).strftime("%Y-%m-01")
            if valid.size > 0:
                stats.append({
                    "date": dt_str,
                    "mean": round(float(np.mean(valid)), 4),
                    "min": round(float(np.min(valid)), 4),
                    "max": round(float(np.max(valid)), 4),
                    "std": round(float(np.std(valid)), 4),
                    "n_cells": int(valid.size)
                })
        pd.DataFrame(stats).to_csv(f"data/timeseries/{vid}_boundary_stats.csv", index=False)
        print(f"Downloaded and clipped {vid}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["day0", "sample", "real"], default="day0")
    args = parser.parse_args()

    setup_directories()
    with open("data/catalogue.json", "r") as f:
        catalogue = json.load(f)
    boundary_gdf = build_boundary("iho.zip")

    if args.mode == "day0":
        # Step 5 compliance: Only 3 sample rows per file on Day 0 (Oct 27-28)
        generate_datasets(catalogue, boundary_gdf, start_date="2024-01-01", end_date="2024-03-01")
    elif args.mode == "sample":
        build_biodiversity()
        generate_datasets(catalogue, boundary_gdf, start_date="2020-01-01", end_date="2024-12-01")
    else:
        build_biodiversity()
        download_real_copernicus(catalogue, boundary_gdf)
