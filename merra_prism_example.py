"""
Example of using the BCSD daily bias correction workflow.
"""

from __future__ import annotations

import argparse
import time

import xarray as xr

from bias_correct import BiasCorrectDaily, convert_to_float32


def _daily_resample(ds: xr.Dataset) -> xr.Dataset:
    """Resample to daily frequency using the default mean aggregation.

    The original repo used an old xarray signature equivalent to a daily
    resample followed by an aggregation. Here we make that explicit.
    """
    return ds.resample(time="1D").mean()


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Example daily BCSD bias correction workflow."
    )
    parser.add_argument(
        "fobserved",
        help="NetCDF file containing an upscaled version of the observed dataset.",
        type=str,
    )
    parser.add_argument(
        "fmodeled",
        help="NetCDF file containing a GCM or reanalysis dataset.",
        type=str,
    )
    parser.add_argument("var1", help="Variable name of the observed dataset", type=str)
    parser.add_argument("var2", help="Variable name of the modeled dataset", type=str)
    parser.add_argument(
        "ofile", help="Output file for the bias-corrected dataset", type=str
    )
    parser.add_argument("--njobs", default=1, type=int, help="Number of parallel jobs")
    parser.add_argument(
        "--max-train-year",
        default=2001,
        type=int,
        help="Maximum year to include in quantile-mapping training.",
    )
    parser.add_argument(
        "--pool",
        default=2,
        type=int,
        help="Half-window size for pooled day-of-year samples.",
    )
    parser.add_argument(
        "--drop-time-bnds",
        action="store_true",
        help="Drop the 'time_bnds' variable from the modeled dataset if present.",
    )
    args = parser.parse_args()

    print("Loading observations")
    obs_data = xr.open_dataset(args.fobserved)
    obs_data = obs_data.load()
    obs_data = obs_data.dropna(dim="time", how="all")
    obs_data = _daily_resample(obs_data)
    obs_data = convert_to_float32(obs_data)

    print("Loading modeled data")
    modeled_data = xr.open_dataset(args.fmodeled)
    if args.drop_time_bnds:
        modeled_data = modeled_data.drop_vars("time_bnds", errors="ignore")
    modeled_data = modeled_data.load()
    modeled_data = _daily_resample(modeled_data)
    modeled_data = convert_to_float32(modeled_data)

    print("Starting BCSD daily bias correction")
    t0 = time.time()
    bc = BiasCorrectDaily(max_train_year=args.max_train_year, pool=args.pool)
    corrected = bc.bias_correction(
        obs_data,
        modeled_data,
        args.var1,
        args.var2,
        njobs=args.njobs,
    )
    elapsed = time.time() - t0
    print(f"Finished in {elapsed:.2f} seconds")

    corrected.to_netcdf(args.ofile)
    print(f"Saved: {args.ofile}")


if __name__ == "__main__":
    main()
