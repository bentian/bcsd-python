"""
Apply BCSD spatial scaling factors.
"""

from __future__ import annotations
from typing import Optional

import argparse

import xarray as xr


def apply_spatial_scaling(
    bias_corrected: xr.Dataset,
    scale: xr.Dataset,
    bc_var: str = "bias_corrected",
    scale_var: Optional[str] = None,
) -> xr.Dataset:
    """Apply climatological day-of-year scaling factors.

    Parameters
    ----------
    bias_corrected:
        Dataset containing the bias-corrected variable.
    scale:
        Dataset containing time-dependent scaling fields.
    bc_var:
        Variable name of the bias-corrected field.
    scale_var:
        Variable name of the scaling field. If omitted, the first data variable
        in `scale` is used.
    """
    if bc_var not in bias_corrected:
        raise KeyError(f"Variable not found in bias_corrected dataset: {bc_var}")

    if scale_var is None:
        if not scale.data_vars:
            raise ValueError("Scale dataset contains no data variables.")
        scale_var = list(scale.data_vars)[0]

    if scale_var not in scale:
        raise KeyError(f"Scale variable not found: {scale_var}")

    bc_da = bias_corrected[bc_var]
    scale_da = scale[scale_var]

    # Climatological day-of-year mean scale factors.
    scale_clim = scale_da.groupby("time.dayofyear").mean("time")

    # Align coordinates with bias-corrected grid when present.
    if "lat" in bc_da.coords and "lat" in scale_clim.coords:
        scale_clim = scale_clim.assign_coords(lat=bc_da["lat"])
    if "lon" in bc_da.coords and "lon" in scale_clim.coords:
        scale_clim = scale_clim.assign_coords(lon=bc_da["lon"])

    scaled_chunks = []
    for key, val in bc_da.groupby("time.dayofyear"):
        lookup_key = (
            365 if int(key) == 366 and 366 not in scale_clim["dayofyear"] else int(key)
        )
        scaled = val * scale_clim.sel(dayofyear=lookup_key)
        scaled_chunks.append(scaled)

    bcsd = xr.concat(scaled_chunks, dim="time").sortby("time")
    return xr.Dataset({"bcsd": bcsd})


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Apply BCSD spatial scaling factors.")
    parser.add_argument(
        "bias_corrected", help="NetCDF file with the bias-corrected field."
    )
    parser.add_argument("scale_file", help="NetCDF file with scaling factors.")
    parser.add_argument("fout", help="Output NetCDF path.")
    parser.add_argument(
        "--bc-var",
        default="bias_corrected",
        help="Variable name in the bias-corrected file.",
    )
    parser.add_argument(
        "--scale-var",
        default=None,
        help="Variable name in the scale file. Defaults to the first data variable.",
    )
    args = parser.parse_args()

    scale = xr.open_dataset(args.scale_file)
    bc = xr.open_dataset(args.bias_corrected)

    out = apply_spatial_scaling(bc, scale, bc_var=args.bc_var, scale_var=args.scale_var)
    out.to_netcdf(args.fout)


if __name__ == "__main__":
    main()
