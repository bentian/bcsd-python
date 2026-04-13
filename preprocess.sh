#!/usr/bin/env bash
set -euo pipefail

# ================================
# CONFIG
# ================================
WORKDIR=~/repos/bcsd-python/data
cd "$WORKDIR"

PRISM="prism_example.nc"
MERRA="merra_example.nc"

PRISM_UPSCALED="prism_upscaled.nc"
MERRA_FILLED="merra_filled.nc"

TMP_FILLED="tmp_prism_filled.nc"
GRID_FILE="merra_grid.txt"

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

# ================================
# STEP 2: Fill missing (PRISM)
# ================================
echo "=== Filling missing values (PRISM) ==="
cdo fillmiss2 "$PRISM" "$TMP_FILLED"

# ================================
# STEP 3: Coarsen + Remap
# ================================
echo "=== Coarsen + Remap to MERRA grid ==="
cdo -P 8 remapbil,"$GRID_FILE" -gridboxmean,3,3 "$TMP_FILLED" "$PRISM_UPSCALED"

# ================================
# STEP 4: Fill missing (MERRA)
# ================================
echo "=== Filling missing values (MERRA) ==="
cdo fillmiss2 "$MERRA" "$MERRA_FILLED"

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