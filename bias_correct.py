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
    """Daily bias correction using pooled day-of-year quantile mapping.

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
        """Perform bias correction.

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
        if obs_var not in obs:
            raise KeyError(f"Observation variable not found: {obs_var}")
        if modeled_var not in modeled:
            raise KeyError(f"Modeled variable not found: {modeled_var}")
        for dim in ("time", "lat", "lon"):
            if dim not in obs[obs_var].dims:
                raise ValueError(f"obs[{obs_var!r}] must have dimension {dim!r}")
            if dim not in modeled[modeled_var].dims:
                raise ValueError(
                    f"modeled[{modeled_var!r}] must have dimension {dim!r}"
                )

        obs = _ensure_daily_datetime_sorted(obs)
        modeled = _ensure_daily_datetime_sorted(modeled)

        # Intersect time periods, preserving only shared timestamps.
        intersection = np.intersect1d(obs["time"].values, modeled["time"].values)
        if intersection.size == 0:
            raise ValueError(
                "No overlapping timestamps were found between obs and modeled."
            )

        obs = obs.sel(time=intersection)
        modeled = modeled.sel(time=intersection)

        obs_da = obs[obs_var]
        modeled_da = modeled[modeled_var]

        dayofyear = obs["time"].dt.dayofyear
        lat_vals = modeled["lat"].values
        lon_vals = modeled["lon"].values

        mapped_data = np.full(
            (intersection.shape[0], lat_vals.shape[0], lon_vals.shape[0]),
            np.nan,
            dtype=np.float32,
        )

        unique_days = np.unique(dayofyear.values)

        for day in unique_days:
            print(f"Processing day-of-year {int(day)}")
            dayrange = _day_range(int(day), self.pool)

            day_mask = xr.DataArray(
                np.isin(dayofyear.values, dayrange),
                coords={"time": obs["time"].values},
                dims=("time",),
            )

            subobs = obs_da.sel(time=day_mask)
            submodeled = modeled_da.sel(time=day_mask)

            sub_doy = subobs["time"].dt.dayofyear.values
            sub_curr_day_rows = np.where(sub_doy == day)[0]
            curr_day_rows = np.where(dayofyear.values == day)[0]

            train_idx = np.where(subobs["time"].dt.year.values <= self.max_train_year)[
                0
            ]
            if train_idx.size == 0:
                raise ValueError(
                    f"No training samples found for day {day}"
                    f"with max_train_year={self.max_train_year}."
                )

            # Original code used the last eligible index, then sliced with [:train_num].
            # That excludes the last eligible item by mistake. Here we use a true count.
            train_count = int(train_idx[-1]) + 1

            jobs = []
            for lat in lat_vals:
                x_lat = subobs.sel(lat=lat, lon=lon_vals, method="nearest").values
                y_lat = submodeled.sel(lat=lat, lon=lon_vals).values
                jobs.append(delayed(_mapper)(x_lat, y_lat, train_count, self.step))

            print(f"Running {len(jobs)} latitude jobs")
            day_mapped = np.asarray(Parallel(n_jobs=njobs)(jobs), dtype=np.float32)
            day_mapped = day_mapped[:, sub_curr_day_rows, :]
            day_mapped = np.swapaxes(day_mapped, 0, 1)  # (time, lat, lon)
            mapped_data[curr_day_rows, :, :] = day_mapped

        bias_corrected = xr.DataArray(
            mapped_data,
            coords={
                "time": obs["time"].values,
                "lat": lat_vals,
                "lon": lon_vals,
            },
            dims=("time", "lat", "lon"),
            name="bias_corrected",
            attrs={"gridtype": "latlon"},
        )

        ds_bc = xr.Dataset({"bias_corrected": bias_corrected})

        # Preserve the modeled dataset structure as much as possible.
        out = modeled.copy()
        out = out.drop_vars([modeled_var], errors="ignore")
        out["bias_corrected"] = ds_bc["bias_corrected"].reindex_like(
            modeled[modeled_var]
        )
        return out
