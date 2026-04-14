#!/usr/bin/env bash
set -euo pipefail

# ================================
# CONFIG
# ================================
DATADIR=${DATADIR:-"$HOME/bcsd/data"}
WORKDIR=${WORKDIR:-"$HOME/bcsd/bcsd-run"}
mkdir -p "$WORKDIR"

PRISM=$DATADIR/"prism_example.nc"
MERRA=$DATADIR/"merra_example.nc"

PRISM_UPSCALED=$WORKDIR/"prism_upscaled.nc"
MERRA_FILLED=$WORKDIR/"merra_filled.nc"
TMP_FILLED=$WORKDIR/"tmp_prism_filled.nc"
GRID_FILE=$WORKDIR/"merra_grid.txt"

echo "DATADIR:  $DATADIR"
echo "WORKDIR:  $WORKDIR"
echo "PRISM:    $PRISM"
echo "MERRA:    $MERRA"

# ================================
# CHECK INPUTS
# ================================
[[ -f "$PRISM" ]] || { echo "Missing $PRISM"; exit 1; }
[[ -f "$MERRA" ]] || { echo "Missing $MERRA"; exit 1; }

# ================================
# CLEAN OLD FILES (optional)
# ================================
rm -f "$PRISM_UPSCALED" "$MERRA_FILLED" "$TMP_FILLED" "$GRID_FILE"

# ================================
# STEP 1: Extract grid
# ================================
echo "=== Extracting MERRA grid ==="
cdo griddes "$MERRA" > "$GRID_FILE"
[[ -f "$GRID_FILE" ]] || { echo "Failed to create $GRID_FILE"; exit 1; }

# ================================
# STEP 2: Fill missing (PRISM)
# ================================
echo "=== Filling missing values (PRISM) ==="
cdo fillmiss2 "$PRISM" "$TMP_FILLED"
[[ -f "$TMP_FILLED" ]] || { echo "Failed to create $TMP_FILLED"; exit 1; }

# ================================
# STEP 3: Coarsen + Remap
# ================================
echo "=== Coarsen + Remap to MERRA grid ==="
cdo -P 8 remapbil,"$GRID_FILE" -gridboxmean,3,3 "$TMP_FILLED" "$PRISM_UPSCALED"
[[ -f "$PRISM_UPSCALED" ]] || { echo "Failed to create $PRISM_UPSCALED"; exit 1; }

# ================================
# STEP 4: Fill missing (MERRA)
# ================================
echo "=== Filling missing values (MERRA) ==="
cdo fillmiss2 "$MERRA" "$MERRA_FILLED"
[[ -f "$MERRA_FILLED" ]] || { echo "Failed to create $MERRA_FILLED"; exit 1; }

# ================================
# CLEAN TEMP
# ================================
rm -f "$TMP_FILLED" "$GRID_FILE"

# ================================
# DONE
# ================================
echo "=== DONE ==="
echo "Created:"
echo "  $PRISM_UPSCALED"
echo "  $MERRA_FILLED"
