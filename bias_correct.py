"""
Daily bias correction using pooled day-of-year quantile mapping.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import xarray as xr
from joblib import Parallel, delayed

from qmap import QMap

np.seterr(invalid="ignore")


def convert_to_float32(ds: xr.Dataset) -> xr.Dataset:
    """Cast float64 variables to float32 in a dataset."""
    out = ds.copy()
    for var_name, da in out.data_vars.items():
        if np.issubdtype(da.dtype, np.floating) and da.dtype == np.float64:
            out[var_name] = da.astype(np.float32)
    return out


def _day_range(day: int, pool: int) -> np.ndarray:
    """Return wrapped day-of-year window centered on `day`.

    Replicates the original repo's wrapping behavior over 1..366.
    """
    days = (np.arange(day - pool, day + pool + 1) + 366 - 1) % 366 + 1
    return days.astype(int)


def _ensure_daily_datetime_sorted(ds: xr.Dataset) -> xr.Dataset:
    if "time" not in ds.dims and "time" not in ds.coords:
        raise ValueError("Dataset must contain a time coordinate.")
    return ds.sortby("time")


def _mapper(x: np.ndarray, y: np.ndarray, train_count: int, step: float) -> np.ndarray:
    qmap = QMap(step=step)
    qmap.fit(x[:train_count], y[:train_count], axis=0)
    return qmap.predict(y)


@dataclass
class BiasCorrectDaily:
    """
    Daily bias correction using pooled day-of-year quantile mapping.

    The implementation follows the original repository's intent:
    - align observation and modeled data on intersecting timestamps
    - pool +/- `pool` days around each day-of-year
    - fit quantile mapping on the training period only
    - apply mapping to all matched dates for that pooled sample
    """

    pool: int = 15
    max_train_year: int | float = np.inf
    step: float = 0.1

    def bias_correction(
        self,
        obs: xr.Dataset,
        modeled: xr.Dataset,
        obs_var: str,
        modeled_var: str,
        njobs: int = 1,
    ) -> xr.Dataset:
        """
        Perform bias correction.

        Parameters
        ----------
        obs:
            Observation dataset.
        modeled:
            Modeled dataset.
        obs_var:
            Observation variable name.
        modeled_var:
            Modeled variable name.
        njobs:
            Number of parallel jobs.
        """

        # --- basic checks ---
        for name, ds in [(obs_var, obs), (modeled_var, modeled)]:
            if name not in ds:
                raise KeyError(f"{name} not found")

        for dim in ("time", "lat", "lon"):
            if dim not in obs[obs_var].dims or dim not in modeled[modeled_var].dims:
                raise ValueError(f"Missing dim: {dim}")

        obs = _ensure_daily_datetime_sorted(obs)
        modeled = _ensure_daily_datetime_sorted(modeled)

        # --- align time ---
        t = np.intersect1d(obs.time.values, modeled.time.values)
        if t.size == 0:
            raise ValueError("No overlapping timestamps")

        obs = obs.sel(time=t)
        modeled = modeled.sel(time=t)

        obs_da = obs[obs_var]
        mod_da = modeled[modeled_var]

        doy = obs.time.dt.dayofyear.values
        lat_vals = modeled.lat.values
        lon_vals = modeled.lon.values

        out_arr = np.full(
            (len(t), len(lat_vals), len(lon_vals)),
            np.nan,
            dtype=np.float32,
        )

        # --- main loop ---
        for d in np.unique(doy):
            dayrange = _day_range(int(d), self.pool)

            mask = np.isin(doy, dayrange)
            subobs = obs_da.sel(time=mask)
            submod = mod_da.sel(time=mask)

            sub_doy = subobs.time.dt.dayofyear.values
            idx_sub = np.where(sub_doy == d)[0]
            idx_out = np.where(doy == d)[0]

            train_idx = np.where(subobs.time.dt.year <= self.max_train_year)[0]
            if train_idx.size == 0:
                raise ValueError(f"No training data for DOY {d}")

            train_n = train_idx[-1] + 1

            jobs = [
                delayed(_mapper)(
                    subobs.sel(lat=lat, lon=lon_vals, method="nearest").values,
                    submod.sel(lat=lat, lon=lon_vals).values,
                    train_n,
                    self.step,
                )
                for lat in lat_vals
            ]

            mapped = np.asarray(Parallel(n_jobs=njobs)(jobs), dtype=np.float32)
            mapped = np.swapaxes(mapped[:, idx_sub, :], 0, 1)

            out_arr[idx_out] = mapped

        # --- build dataset ---
        bc = xr.DataArray(
            out_arr,
            coords={"time": t, "lat": lat_vals, "lon": lon_vals},
            dims=("time", "lat", "lon"),
            name="bias_corrected",
        )

        out = modeled.drop_vars([modeled_var], errors="ignore")
        out["bias_corrected"] = bc.reindex_like(modeled[modeled_var])

        # --- CF metadata (for CDO) ---
        if "lat" in out:
            out.lat.attrs.update(
                {
                    "standard_name": "latitude",
                    "units": "degrees_north",
                    "axis": "Y",
                }
            )
        if "lon" in out:
            out.lon.attrs.update(
                {
                    "standard_name": "longitude",
                    "units": "degrees_east",
                    "axis": "X",
                }
            )

        return out
