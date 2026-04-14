#!/usr/bin/env bash
set -euo pipefail

DATADIR=${DATADIR:-"$HOME/Workspace/corrdiff/bcsd/data"}
WORKDIR=${WORKDIR:-"$HOME/Workspace/corrdiff/bcsd/bcsd-run"}

PRISM="$DATADIR/prism_example.nc"
MERRA="$DATADIR/merra_example.nc"

PRISM_UPSCALED="$WORKDIR/prism_upscaled.nc"
MERRA_FILLED="$WORKDIR/merra_filled.nc"
TMP_FILLED="$WORKDIR/tmp_prism_filled.nc"

MERRA_BC="$WORKDIR/merra_bc.nc"
PRISM_GRID="$WORKDIR/prism_grid"
MERRA_BC_INTERP="$WORKDIR/merra_bc_interp.nc"
PRISM_REINTERPOLATED="$WORKDIR/prism_reinterpolated.nc"
PRISM_INTERP_YDAYAVG="$WORKDIR/prism_interpolated_ydayavg.nc"
PRISM_YDAYAVG="$WORKDIR/prism_ydayavg.nc"
SCALE_FACTORS="$WORKDIR/scale_factors.nc"
MERRA_BCSD="$WORKDIR/merra_bcsd.nc"

BIAS_SCRIPT="./merra_prism_example.py"
SPATIAL_SCRIPT="./spatial_scaling.py"

mkdir -p "$WORKDIR"

echo "DATADIR:  $DATADIR"
echo "WORKDIR:  $WORKDIR"
echo "PRISM:    $PRISM"
echo "MERRA:    $MERRA"

[[ -f "$PRISM" ]] || { echo "Missing input: $PRISM"; exit 1; }
[[ -f "$MERRA" ]] || { echo "Missing input: $MERRA"; exit 1; }
[[ -f "$BIAS_SCRIPT" ]] || { echo "Missing script: $BIAS_SCRIPT"; exit 1; }
[[ -f "$SPATIAL_SCRIPT" ]] || { echo "Missing script: $SPATIAL_SCRIPT"; exit 1; }

# --------------------------------
# Step 1: Preprocess
# --------------------------------
if [[ -f "$PRISM_UPSCALED" && -f "$MERRA_FILLED" ]]; then
    echo "=== Preprocess outputs already exist; skipping ==="
else
    echo "=== Preprocess ==="

    cdo griddes "$MERRA" > "$WORKDIR/merra_grid.txt"
    cdo fillmiss2 "$PRISM" "$TMP_FILLED"
    cdo -P 8 remapbil,"$WORKDIR/merra_grid.txt" -gridboxmean,3,3 "$TMP_FILLED" "$PRISM_UPSCALED"
    cdo fillmiss2 "$MERRA" "$MERRA_FILLED"

    [[ -f "$PRISM_UPSCALED" ]] || { echo "Failed to create $PRISM_UPSCALED"; exit 1; }
    [[ -f "$MERRA_FILLED" ]] || { echo "Failed to create $MERRA_FILLED"; exit 1; }

    rm -f "$TMP_FILLED" "$WORKDIR/merra_grid.txt"
fi

# --------------------------------
# Step 2: Bias Correction
# --------------------------------
if [[ -f "$MERRA_BC" ]]; then
    echo "=== Bias-corrected file already exists; skipping ==="
else
    echo "=== Bias Correction ==="
    python "$BIAS_SCRIPT" "$PRISM_UPSCALED" "$MERRA_FILLED" ppt PRECTOTLAND "$MERRA_BC"
    [[ -f "$MERRA_BC" ]] || { echo "Missing output: $MERRA_BC"; exit 1; }
fi

# --------------------------------
# Step 3: Spatial Disaggregation
# --------------------------------
if [[ ! -f "$PRISM_GRID" ]]; then
    echo "=== Create PRISM grid description ==="
    cdo griddes "$PRISM" > "$PRISM_GRID"
    [[ -f "$PRISM_GRID" ]] || { echo "Missing output: $PRISM_GRID"; exit 1; }
fi

if [[ -f "$MERRA_BC_INTERP" ]]; then
    echo "=== Remapped bias-corrected MERRA already exists; skipping ==="
else
    echo "=== Remap bias-corrected MERRA to PRISM grid ==="
    cdo -O remapbil,"$PRISM_GRID" "$MERRA_BC" "$MERRA_BC_INTERP"
    [[ -f "$MERRA_BC_INTERP" ]] || { echo "Missing output: $MERRA_BC_INTERP"; exit 1; }
fi

if [[ -f "$PRISM_REINTERPOLATED" ]]; then
    echo "=== Reinterpolated PRISM already exists; skipping ==="
else
    echo "=== Interpolate upscaled PRISM to original resolution ==="
    cdo -O remapbil,"$PRISM_GRID" "$PRISM_UPSCALED" "$PRISM_REINTERPOLATED"
    [[ -f "$PRISM_REINTERPOLATED" ]] || { echo "Missing output: $PRISM_REINTERPOLATED"; exit 1; }
fi

if [[ -f "$SCALE_FACTORS" ]]; then
    echo "=== Scale factors already exist; skipping ==="
else
    echo "=== Compute climatological scale factors ==="
    cdo -O ydayavg "$PRISM_REINTERPOLATED" "$PRISM_INTERP_YDAYAVG"
    cdo -O ydayavg "$PRISM" "$PRISM_YDAYAVG"
    cdo -O div "$PRISM_YDAYAVG" "$PRISM_INTERP_YDAYAVG" "$SCALE_FACTORS"

    [[ -f "$PRISM_INTERP_YDAYAVG" ]] || { echo "Missing output: $PRISM_INTERP_YDAYAVG"; exit 1; }
    [[ -f "$PRISM_YDAYAVG" ]] || { echo "Missing output: $PRISM_YDAYAVG"; exit 1; }
    [[ -f "$SCALE_FACTORS" ]] || { echo "Missing output: $SCALE_FACTORS"; exit 1; }
fi

# --------------------------------
# Step 4: Spatial Scaling
# --------------------------------
if [[ -f "$MERRA_BCSD" ]]; then
    echo "=== Final BCSD output already exists; skipping ==="
else
    echo "=== Execute Spatial Scaling ==="
    python "$SPATIAL_SCRIPT" "$MERRA_BC_INTERP" "$SCALE_FACTORS" "$MERRA_BCSD"
    [[ -f "$MERRA_BCSD" ]] || { echo "Missing output: $MERRA_BCSD"; exit 1; }
fi

echo "=== DONE ==="
echo "Outputs:"
echo "  $PRISM_UPSCALED"
echo "  $MERRA_FILLED"
echo "  $MERRA_BC"
echo "  $MERRA_BC_INTERP"
echo "  $PRISM_REINTERPOLATED"
echo "  $PRISM_INTERP_YDAYAVG"
echo "  $PRISM_YDAYAVG"
echo "  $SCALE_FACTORS"
echo "  $MERRA_BCSD"