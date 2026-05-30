#!/usr/bin/env bash
# ============================================================================
#  build_wasm.sh  –  C_HUD_Runway  WASM build script  (Unix / CI)
#
#  Requires:
#    · LLVM / Clang 17+ with wasm32-unknown-unknown target
#    · MSFS SDK 0.23+  (set MSFS_SDK_ROOT env or pass --sdk-path)
#
#  Usage:
#    chmod +x build_wasm.sh
#    ./build_wasm.sh                          # uses MSFS_SDK_ROOT env
#    ./build_wasm.sh --sdk-path /path/to/sdk  # explicit path
#
#  Output:  panel/C_HUD_Runway.wasm
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/panel"
OUTPUT_WASM="${OUTPUT_DIR}/C_HUD_Runway.wasm"

# -------------------------------------------------------------------------
#  SDK discovery
# -------------------------------------------------------------------------
if [[ "$*" == *--sdk-path* ]]; then
    # Parse --sdk-path value from arguments
    ARGS=( "$@" )
    for i in "${!ARGS[@]}"; do
        if [[ "${ARGS[$i]}" == "--sdk-path" ]] && [[ $((i+1)) -lt ${#ARGS[@]} ]]; then
            MSFS_SDK_ROOT="${ARGS[$((i+1))]}"
            break
        fi
    done
fi

if [[ -z "${MSFS_SDK_ROOT:-}" ]]; then
    echo "ERROR: MSFS_SDK_ROOT not set. Provide --sdk-path or set the environment variable."
    echo "  export MSFS_SDK_ROOT=/path/to/MSFS_SDK"
    exit 1
fi

MSFS_WASM_INCLUDE="${MSFS_SDK_ROOT}/WASM/include"
MSFS_WASM_LIB="${MSFS_SDK_ROOT}/WASM/lib/wasm32"

if [[ ! -d "${MSFS_WASM_INCLUDE}" ]]; then
    echo "ERROR: MSFS SDK WASM include not found at: ${MSFS_WASM_INCLUDE}"
    exit 1
fi

echo "==> C_HUD_Runway WASM Build"
echo "    SDK root: ${MSFS_SDK_ROOT}"
echo "    Output:   ${OUTPUT_WASM}"

# -------------------------------------------------------------------------
#  Source files
# -------------------------------------------------------------------------
SRC_ROOT="${SCRIPT_DIR}/src"
INCLUDE_ROOT="${SCRIPT_DIR}/include"

SRC_FILES=(
    # Core lifecycle
    "${SRC_ROOT}/main.cpp"
    "${SRC_ROOT}/module.cpp"
    "${SRC_ROOT}/lvar_table.cpp"

    # HUD core
    "${SRC_ROOT}/hud/aircraft_profiles.cpp"
    "${SRC_ROOT}/hud/runway_projection.cpp"
    "${SRC_ROOT}/hud/fpv.cpp"
    "${SRC_ROOT}/hud/guidance.cpp"
    "${SRC_ROOT}/hud/symbology.cpp"
    "${SRC_ROOT}/hud/collimation.cpp"
    "${SRC_ROOT}/hud/flare.cpp"
    "${SRC_ROOT}/hud/evs.cpp"
    "${SRC_ROOT}/hud/stabilization.cpp"
    "${SRC_ROOT}/hud/advanced_symbology.cpp"
    "${SRC_ROOT}/hud/airport_database.cpp"
    "${SRC_ROOT}/hud/runway_cache.cpp"
    "${SRC_ROOT}/hud/calibration.cpp"
    "${SRC_ROOT}/hud/rollout.cpp"
    "${SRC_ROOT}/hud/visual_response.cpp"
    "${SRC_ROOT}/hud/declutter.cpp"
    "${SRC_ROOT}/hud/confidence.cpp"
    "${SRC_ROOT}/hud/depth_illusion.cpp"

    # A350-specific modules
    "${SRC_ROOT}/hud/aircraft/a350_profile.cpp"
    "${SRC_ROOT}/hud/aircraft/airbus_fpv.cpp"
    "${SRC_ROOT}/hud/aircraft/a350_flare_law.cpp"
    "${SRC_ROOT}/hud/aircraft/a350_rollout.cpp"
    "${SRC_ROOT}/hud/aircraft/a350_cat3.cpp"
    "${SRC_ROOT}/hud/aircraft/a350_symbology.cpp"
    "${SRC_ROOT}/hud/aircraft/a350_fpv_controller.cpp"
    "${SRC_ROOT}/hud/aircraft/a350_horizon.cpp"
    "${SRC_ROOT}/hud/aircraft/a350_autoland.cpp"
    "${SRC_ROOT}/hud/aircraft/a350_landing_energy.cpp"
    "${SRC_ROOT}/hud/aircraft/a350_runway_augmentation.cpp"

    # Multi-aircraft abstraction
    "${SRC_ROOT}/hud/aircraft/boeing_hgs_behavior.cpp"
    "${SRC_ROOT}/hud/aircraft/airbus_hud_behavior.cpp"
    "${SRC_ROOT}/hud/aircraft_detector.cpp"
    "${SRC_ROOT}/hud/telemetry.cpp"

    # Phase 4 — Real HUD Integration
    "${SRC_ROOT}/hud/hud_deployment.cpp"
    "${SRC_ROOT}/hud/combiner_geometry.cpp"
)

# -------------------------------------------------------------------------
#  Compile & link
# -------------------------------------------------------------------------
CLANG="${CLANG:-clang++}"
CLANG_VERSION=$("${CLANG}" --version 2>/dev/null | head -1 || echo "unknown")
echo "    Compiler: ${CLANG}  (${CLANG_VERSION})"

# Create output directory
mkdir -p "${OUTPUT_DIR}"

# Compile flags — freestanding, wasm32 target, no libc
CXXFLAGS=(
    -std=c++17
    -target wasm32-unknown-unknown
    -nostdlib
    -nostdinc
    -fno-exceptions
    -fno-rtti
    -mcpu=generic
    -mllvm -wasm-disable-explicit-locals
    -fno-strict-aliasing
    -Wall -Wextra -Wpedantic
    -Wno-unused-parameter
    -Wno-unused-private-field
    -Wno-c++11-narrowing
    -D_C_HUD_WASM_BUILD_=1
    -O2
    -I"${INCLUDE_ROOT}"
    -I"${MSFS_WASM_INCLUDE}"
)

# Link flags — no entry point, export required symbols
LDFLAGS=(
    -nostdlib
    -Wl,--no-entry
    -Wl,--allow-undefined
    -Wl,--stack-first
    -Wl,--initial-memory=16777216
    -Wl,--max-memory=67108864
    -Wl,--export=module_init
    -Wl,--export=module_deinit
    -Wl,--export=gauge_callback_post_install
    -Wl,--export=gauge_callback_pre_update
    -Wl,--export=gauge_callback_post_draw
    -Wl,--export=gauge_callback
    -Wl,--strip-all
    -Wl,--gc-sections
    -o "${OUTPUT_WASM}"
)

echo "==> Compiling ${#SRC_FILES[@]} source files..."
"${CLANG}" "${CXXFLAGS[@]}" "${SRC_FILES[@]}" "${LDFLAGS[@]}"

# -------------------------------------------------------------------------
#  Verify output
# -------------------------------------------------------------------------
if [[ -f "${OUTPUT_WASM}" ]]; then
    WASM_SIZE=$(stat -f "%z" "${OUTPUT_WASM}" 2>/dev/null || stat -c "%s" "${OUTPUT_WASM}" 2>/dev/null || echo "?")
    echo "==> SUCCESS: ${OUTPUT_WASM}  (${WASM_SIZE} bytes)"
else
    echo "==> FAILED: ${OUTPUT_WASM} not generated"
    exit 1
fi
