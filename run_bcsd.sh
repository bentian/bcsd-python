#!/usr/bin/env bash
set -euo pipefail

DATADIR=${DATADIR:-"$HOME/Workspace/corrdiff/bcsd/data"}
WORKDIR=${WORKDIR:-"$HOME/Workspace/corrdiff/bcsd/bcsd-run"}

HR_NC="$DATADIR/highres.nc"
LR_NC="$DATADIR/lowres.nc"

HR_UPSCALED="$WORKDIR/hr_upscaled.nc"
LR_FILLED="$WORKDIR/lr_filled.nc"
TMP_HR_FILLED="$WORKDIR/tmp_hr_filled.nc"

LR_BC="$WORKDIR/lr_bc.nc"
HR_GRID="$WORKDIR/hr_grid"
LR_BC_INTERP="$WORKDIR/lr_bc_interp.nc"
HR_REINTERPOLATED="$WORKDIR/hr_reinterpolated.nc"
HR_INTERP_YDAYAVG="$WORKDIR/hr_interpolated_ydayavg.nc"
HR_YDAYAVG="$WORKDIR/hr_ydayavg.nc"
SCALE_FACTORS="$WORKDIR/scale_factors.nc"
LR_BCSD="$WORKDIR/lr_bcsd.nc"

BIAS_SCRIPT="./merra_prism_example.py"
SPATIAL_SCRIPT="./spatial_scaling.py"

mkdir -p "$WORKDIR"

echo "DATADIR:  $DATADIR"
echo "WORKDIR:  $WORKDIR"
echo "HR:    $HR_NC"
echo "LR:    $LR_NC"

[[ -f "$HR_NC" ]] || { echo "Missing input: $HR_NC"; exit 1; }
[[ -f "$LR_NC" ]] || { echo "Missing input: $LR_NC"; exit 1; }
[[ -f "$BIAS_SCRIPT" ]] || { echo "Missing script: $BIAS_SCRIPT"; exit 1; }
[[ -f "$SPATIAL_SCRIPT" ]] || { echo "Missing script: $SPATIAL_SCRIPT"; exit 1; }

# --------------------------------
# Step 1: Preprocess
# --------------------------------
if [[ -f "$HR_UPSCALED" && -f "$LR_FILLED" ]]; then
    echo "=== Preprocess outputs already exist; skipping ==="
else
    echo -e "\n=== Preprocess ==="

    # HR_NC -> fill missing (TMP_HR_FILLED)
    #       -> coarse via gridboxmean & remap to LOWRES grid (HR_UPSCALED)
    cdo griddes "$LR_NC" > "$WORKDIR/lr_grid.txt"
    cdo fillmiss2 "$HR_NC" "$TMP_HR_FILLED"
    cdo -P 8 remapbil,"$WORKDIR/lr_grid.txt" -gridboxmean,3,3 "$TMP_HR_FILLED" "$HR_UPSCALED"

    # LR_NC -> fill missing (LR_FILLED)
    cdo fillmiss2 "$LR_NC" "$LR_FILLED"

    [[ -f "$HR_UPSCALED" ]] || { echo "Failed to create $HR_UPSCALED"; exit 1; }
    [[ -f "$LR_FILLED" ]] || { echo "Failed to create $LR_FILLED"; exit 1; }

    rm -f "$TMP_HR_FILLED" "$WORKDIR/lr_grid.txt"
fi

# --------------------------------
# Step 2: Bias Correction
# --------------------------------
if [[ -f "$LR_BC" ]]; then
    echo "=== Bias-corrected file already exists; skipping ==="
else
    echo -e "\n=== Bias Correction ==="
    python "$BIAS_SCRIPT" "$HR_UPSCALED" "$LR_FILLED" ppt PRECTOTLAND "$LR_BC"
    [[ -f "$LR_BC" ]] || { echo "Missing output: $LR_BC"; exit 1; }
fi

# --------------------------------
# Step 3: Spatial Disaggregation
# --------------------------------
if [[ ! -f "$HR_GRID" ]]; then
    echo "=== Create HR grid description ==="
    cdo griddes "$HR_NC" > "$HR_GRID"
    [[ -f "$HR_GRID" ]] || { echo "Missing output: $HR_GRID"; exit 1; }
fi

if [[ -f "$LR_BC_INTERP" ]]; then
    echo "=== Remapped bias-corrected MERRA already exists; skipping ==="
else
    echo -e "\n=== Remap bias-corrected MERRA to PRISM grid ==="
    cdo -O remapbil,"$HR_GRID" "$LR_BC" "$LR_BC_INTERP"
    [[ -f "$LR_BC_INTERP" ]] || { echo "Missing output: $LR_BC_INTERP"; exit 1; }
fi

if [[ -f "$HR_REINTERPOLATED" ]]; then
    echo "=== Reinterpolated PRISM already exists; skipping ==="
else
    echo -e "\n=== Interpolate upscaled PRISM to original resolution ==="
    cdo -O remapbil,"$HR_GRID" "$HR_UPSCALED" "$HR_REINTERPOLATED"
    [[ -f "$HR_REINTERPOLATED" ]] || { echo "Missing output: $HR_REINTERPOLATED"; exit 1; }
fi

if [[ -f "$SCALE_FACTORS" ]]; then
    echo "=== Scale factors already exist; skipping ==="
else
    echo -e "\n=== Compute climatological scale factors ==="
    cdo -O ydayavg "$HR_REINTERPOLATED" "$HR_INTERP_YDAYAVG"
    cdo -O ydayavg "$HR_NC" "$HR_YDAYAVG"
    cdo -O div "$HR_YDAYAVG" "$HR_INTERP_YDAYAVG" "$SCALE_FACTORS"

    [[ -f "$HR_INTERP_YDAYAVG" ]] || { echo "Missing output: $HR_INTERP_YDAYAVG"; exit 1; }
    [[ -f "$HR_YDAYAVG" ]] || { echo "Missing output: $HR_YDAYAVG"; exit 1; }
    [[ -f "$SCALE_FACTORS" ]] || { echo "Missing output: $SCALE_FACTORS"; exit 1; }
fi

# --------------------------------
# Step 4: Spatial Scaling
# --------------------------------
if [[ -f "$LR_BCSD" ]]; then
    echo "=== Final BCSD output already exists; skipping ==="
else
    echo -e "\n=== Execute Spatial Scaling ==="
    python "$SPATIAL_SCRIPT" "$LR_BC_INTERP" "$SCALE_FACTORS" "$LR_BCSD"
    [[ -f "$LR_BCSD" ]] || { echo "Missing output: $LR_BCSD"; exit 1; }
fi

echo -e "\n=== DONE ==="
echo "Outputs:"
echo "  $HR_UPSCALED"
echo "  $LR_FILLED"
echo "  $LR_BC"
echo "  $LR_BC_INTERP"
echo "  $HR_REINTERPOLATED"
echo "  $HR_INTERP_YDAYAVG"
echo "  $HR_YDAYAVG"
echo "  $SCALE_FACTORS"
echo "  $LR_BCSD"