"""
12-month map forecasts with a small U-Net, one model per variable.

How it works
  * Each month is a map (all depth levels stacked as channels). The model sees the last 12 months of
    anomalies (value minus that calendar month's average) and predicts the next 12 months of anomalies
    in one go. Adding the monthly average back gives the forecast maps.
  * Honest test: the last 24 months are hidden from training. The model forecasts them from 13 start
    months and is scored against two simple baselines:
      - climatology: "next year looks like the average year"
      - persistence: "this month's anomaly carries on"
    Skill > 0 means the U-Net beats climatology.
  * The final model is then retrained on all months and forecasts the 12 months after the last data month.
    The uncertainty band comes from the errors seen in the hidden-period test.

Outputs (read by the app):
  data/forecast/<id>_forecast.nc          dims time(12), [depth], latitude, longitude
  data/forecast/<id>_forecast_stats.csv   date, depth, mean, lower, upper (boundary-wide)
  data/forecast/skill.json                test scores per variable

Usage:  python model/train_unet.py            # all variables
        python model/train_unet.py thetao o2  # some variables
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import xarray as xr

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "forecast"
LOOKBACK = 12          # months of input
HORIZON = 12           # months predicted
HOLDOUT = 24           # months hidden for the test
LOG_VARS = {"CHL", "KD490", "chl_bgc", "nppv", "phyc"}   # skewed variables modelled in log10 space
SEED = 7
torch.set_num_threads(max(1, torch.get_num_threads()))


# --------------------------------------------------------------------------- data
def load_variable(vid):
    with xr.open_dataset(DATA / "netcdf" / f"{vid}_monthly.nc") as ds:
        da = ds[vid].load()
    if da.latitude[0] > da.latitude[-1]:
        da = da.isel(latitude=slice(None, None, -1))
    if "depth" not in da.dims:
        da = da.expand_dims(depth=[0.0], axis=1)
    da = da.transpose("time", "depth", "latitude", "longitude")
    x = da.values.astype(np.float32)
    if vid in LOG_VARS:
        x = np.log10(np.where(x > 0, x, np.nan))
    return da, x


def climatology(x, months, upto):
    """Per-pixel, per-depth mean for each calendar month using months [0, upto)."""
    clim = np.full((12,) + x.shape[1:], np.nan)
    for m in range(1, 13):
        sel = np.where(months[:upto] == m)[0]
        if sel.size:
            with np.errstate(all="ignore"), __import__("warnings").catch_warnings():
                __import__("warnings").simplefilter("ignore", RuntimeWarning)
                clim[m - 1] = np.nanmean(x[sel], axis=0)
    return clim


def anomalies(x, months, clim):
    return x - clim[months - 1]


def make_samples(anom, origins):
    """Inputs: 12 months of anomalies + their masks. Targets: next 12 months of anomalies."""
    T, C, H, W = anom.shape
    X = np.empty((len(origins), LOOKBACK * C + LOOKBACK, H, W), dtype=np.float32)   # preallocated: low memory
    Y = np.empty((len(origins), HORIZON * C, H, W), dtype=np.float32)
    for i, o in enumerate(origins):
        inp = anom[o - LOOKBACK + 1:o + 1]                 # (L, C, H, W)
        X[i, :LOOKBACK * C] = np.nan_to_num(inp).reshape(-1, H, W)
        X[i, LOOKBACK * C:] = np.isfinite(inp).any(axis=1)
        Y[i] = anom[o + 1:o + 1 + HORIZON].reshape(-1, H, W)
    return X, Y


def pad_to(a, mult=8):
    h, w = a.shape[-2:]
    ph, pw = (-h) % mult, (-w) % mult
    return np.pad(a, [(0, 0)] * (a.ndim - 2) + [(0, ph), (0, pw)], constant_values=np.nan), (h, w)


# --------------------------------------------------------------------------- model
def block(cin, cout):
    return nn.Sequential(
        nn.Conv2d(cin, cout, 3, padding=1), nn.GroupNorm(min(8, cout), cout), nn.GELU(),
        nn.Conv2d(cout, cout, 3, padding=1), nn.GroupNorm(min(8, cout), cout), nn.GELU(),
    )


class UNet(nn.Module):
    def __init__(self, cin, cout, base=16):
        super().__init__()
        self.e1, self.e2, self.e3 = block(cin, base), block(base, base * 2), block(base * 2, base * 4)
        self.mid = block(base * 4, base * 4)
        self.pool = nn.MaxPool2d(2)
        self.u3, self.d3 = nn.ConvTranspose2d(base * 4, base * 4, 2, 2), block(base * 8, base * 2)
        self.u2, self.d2 = nn.ConvTranspose2d(base * 2, base * 2, 2, 2), block(base * 4, base)
        self.u1, self.d1 = nn.ConvTranspose2d(base, base, 2, 2), block(base * 2, base)
        self.drop = nn.Dropout2d(0.1)
        self.out = nn.Conv2d(base, cout, 1)

    def forward(self, x):
        e1 = self.e1(x)
        e2 = self.e2(self.pool(e1))
        e3 = self.e3(self.pool(e2))
        m = self.drop(self.mid(self.pool(e3)))
        d3 = self.d3(torch.cat([self.u3(m), e3], 1))
        d2 = self.d2(torch.cat([self.u2(d3), e2], 1))
        d1 = self.d1(torch.cat([self.u1(d2), e1], 1))
        return self.out(d1)


def masked_mse(pred, tgt):
    m = torch.isfinite(tgt)
    return ((pred[m] - tgt[m]) ** 2).mean()


def train(X, Y, epochs=100, patience=12, lr=1e-3, batch=16, fixed_epochs=None):
    """Early-stopped on the last 10% of samples, or trained for `fixed_epochs` on everything."""
    torch.manual_seed(SEED)
    if fixed_epochs:
        epochs, patience = fixed_epochs, fixed_epochs + 1
        Xtr, Ytr, Xva, Yva = X, Y, X[-2:], Y[-2:]
    else:
        n_val = max(2, len(X) // 10)
        Xtr, Ytr, Xva, Yva = X[:-n_val], Y[:-n_val], X[-n_val:], Y[-n_val:]
    model = UNet(X.shape[1], Y.shape[1])
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    Xtr_t, Ytr_t = torch.from_numpy(Xtr), torch.from_numpy(Ytr)
    Xva_t, Yva_t = torch.from_numpy(Xva), torch.from_numpy(Yva)
    best, best_state, wait = np.inf, None, 0
    for ep in range(epochs):
        model.train()
        perm = torch.randperm(len(Xtr_t))
        for i in range(0, len(perm), batch):
            idx = perm[i:i + batch]
            opt.zero_grad()
            loss = masked_mse(model(Xtr_t[idx]), Ytr_t[idx])
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            v = masked_mse(model(Xva_t), Yva_t).item()
        if fixed_epochs:
            best_state, best_ep = {k: t.clone() for k, t in model.state_dict().items()}, ep + 1
            continue
        if v < best - 1e-5:
            best, best_state, wait, best_ep = v, {k: t.clone() for k, t in model.state_dict().items()}, 0, ep + 1
        else:
            wait += 1
            if wait >= patience:
                break
    model.load_state_dict(best_state)
    model.eval()
    return model, best_ep


def predict(model, X):
    with torch.no_grad():
        return model(torch.from_numpy(X)).numpy()


# --------------------------------------------------------------------------- one variable
def run_variable(vid):
    t_start = time.time()
    da, x = load_variable(vid)
    times = pd.DatetimeIndex(da.time.values)
    months = times.month.values
    T, C = x.shape[:2]
    x_p, (h, w) = pad_to(x)
    valid_px = np.isfinite(x).any(axis=(0, 1))             # cells that ever have data

    # ---- honest test on the last HOLDOUT months
    cut = T - HOLDOUT
    clim_tr = climatology(x_p, months, cut)
    anom_tr = anomalies(x_p, months, clim_tr)
    scale = np.nanstd(anom_tr[:cut], axis=(0, 2, 3), keepdims=True)
    scale[~np.isfinite(scale) | (scale == 0)] = 1.0
    z = anom_tr / scale
    train_orig = list(range(LOOKBACK - 1, cut - HORIZON))
    test_orig = list(range(cut - 1, T - HORIZON))           # 13 start months, targets all in the hidden period
    Xtr, Ytr = make_samples(z, train_orig)
    Xte, Yte = make_samples(z, test_orig)
    model, n_ep = train(Xtr, Ytr)
    P = predict(model, Xte).reshape(len(test_orig), HORIZON, C, *x_p.shape[2:])
    Yt = Yte.reshape(P.shape)
    persist = np.repeat(Xte[:, (LOOKBACK - 1) * C:LOOKBACK * C][:, None], HORIZON, axis=1).reshape(P.shape)

    def to_units(zz, origin_idx):
        """standardised anomaly -> physical units, for each test sample and lead"""
        out = np.empty_like(zz, dtype=np.float64)
        for s, o in enumerate(origin_idx):
            mm = months[o + 1:o + 1 + HORIZON]
            v = zz[s] * scale[0][None] + clim_tr[mm - 1]
            out[s] = 10 ** v if vid in LOG_VARS else v
        return out

    truth = to_units(Yt, test_orig)
    pred_u = to_units(P, test_orig)
    clim_u = to_units(np.zeros_like(P), test_orig)
    pers_u = to_units(persist, test_orig)
    m = np.isfinite(truth)

    def rmse(a):
        return float(np.sqrt(np.nanmean((a[m] - truth[m]) ** 2)))

    r_unet, r_clim, r_pers = rmse(pred_u), rmse(clim_u), rmse(pers_u)

    # boundary-mean error per lead and depth -> uncertainty band
    def bmean(a):
        aa = np.where(m, a, np.nan)
        return np.nanmean(aa[..., :h, :w], axis=(-2, -1))  # (S, H, C)

    err = bmean(pred_u) - bmean(truth)
    band = 1.96 * np.sqrt(np.nanmean(err ** 2, axis=0))     # (H, C) RMSE-based 95% band

    # ---- free the test-run arrays before the final run
    del Xtr, Ytr, Xte, Yte, P, Yt, persist, truth, pred_u, clim_u, pers_u, model, anom_tr, z
    import gc
    gc.collect()

    # ---- final model on all months, forecast after the last month
    clim_all = climatology(x_p, months, T)
    anom_all = anomalies(x_p, months, clim_all)
    scale_all = np.nanstd(anom_all, axis=(0, 2, 3), keepdims=True)
    scale_all[~np.isfinite(scale_all) | (scale_all == 0)] = 1.0
    z_all = anom_all / scale_all
    Xall, Yall = make_samples(z_all, list(range(LOOKBACK - 1, T - HORIZON)))
    model_all, n_ep_all = train(Xall, Yall, fixed_epochs=max(10, n_ep))
    inp = z_all[T - LOOKBACK:T]
    X_last = np.concatenate([np.nan_to_num(inp).reshape(-1, *x_p.shape[2:]),
                             np.isfinite(inp).any(axis=1).astype(np.float64)], axis=0)[None].astype(np.float32)
    f = predict(model_all, X_last).reshape(HORIZON, C, *x_p.shape[2:])
    f_times = pd.date_range(times[-1] + pd.offsets.MonthBegin(1), periods=HORIZON, freq="MS")
    fm = f_times.month.values
    fc = f * scale_all[0][None] + clim_all[fm - 1]
    fc = 10 ** fc if vid in LOG_VARS else fc
    fc = fc[..., :h, :w]
    fc[:, :, ~valid_px] = np.nan

    # ---- save
    OUT.mkdir(parents=True, exist_ok=True)
    has_depth = "depth" in xr.open_dataset(DATA / "netcdf" / f"{vid}_monthly.nc")[vid].dims
    coords = {"time": f_times, "latitude": da.latitude.values, "longitude": da.longitude.values}
    if has_depth:
        coords["depth"] = da.depth.values
        out = xr.DataArray(fc.astype(np.float32), dims=("time", "depth", "latitude", "longitude"), coords=coords)
    else:
        out = xr.DataArray(fc[:, 0].astype(np.float32), dims=("time", "latitude", "longitude"), coords=coords)
    out.attrs.update({"units": str(da.attrs.get("units", "")), "long_name": f"U-Net 12-month forecast of {vid}"})
    out.to_dataset(name=vid).to_netcdf(OUT / f"{vid}_forecast.nc", encoding={vid: {"zlib": True, "complevel": 4}})

    rows = []
    for li, t in enumerate(f_times):
        for ci in range(C):
            mean = float(np.nanmean(fc[li, ci]))
            rows.append({"date": t.strftime("%Y-%m-01"),
                         "depth": float(da.depth.values[ci]) if has_depth else "",
                         "mean": round(mean, 6),
                         "lower": round(mean - float(band[li, ci]), 6),
                         "upper": round(mean + float(band[li, ci]), 6)})
    pd.DataFrame(rows).to_csv(OUT / f"{vid}_forecast_stats.csv", index=False)

    result = {
        "rmse_unet": round(r_unet, 6), "rmse_climatology": round(r_clim, 6), "rmse_persistence": round(r_pers, 6),
        "skill_vs_climatology": round(1 - r_unet / r_clim, 3) if r_clim > 0 else None,
        "test_period": f"{times[cut]:%Y-%m} to {times[-1]:%Y-%m}",
        "trained_through": f"{times[-1]:%Y-%m}",
        "forecast_period": f"{f_times[0]:%Y-%m} to {f_times[-1]:%Y-%m}",
        "test_starts": len(test_orig), "epochs_test_model": n_ep, "epochs_final_model": n_ep_all,
        "log_space": vid in LOG_VARS, "seconds": round(time.time() - t_start, 1),
    }
    print(f"{vid:22} skill {result['skill_vs_climatology']:+.3f}  RMSE unet {r_unet:.4g} | clim {r_clim:.4g} | "
          f"persist {r_pers:.4g}  ({result['seconds']}s)", flush=True)
    return result


if __name__ == "__main__":
    np.random.seed(SEED)
    catalogue = json.loads((DATA / "catalogue.json").read_text())
    ids = sys.argv[1:] or [v["id"] for v in catalogue]
    skill_path = OUT / "skill.json"
    skill = json.loads(skill_path.read_text()) if skill_path.exists() else {}
    for vid in ids:
        skill[vid] = run_variable(vid)
        OUT.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(json.dumps(skill, indent=2))
    print("done")
