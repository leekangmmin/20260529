#ifndef C_HUD_VERIFICATION_H
#define C_HUD_VERIFICATION_H

// ============================================================================
//  Conformal HUD – Verification / Debug Overlay (v2.2.0)
//  MSFS 2024  ·  C++17  ·  WASM
//
//  Runtime verification and calibration visualization modes:
//    · Projected runway corner markers (world-space axis indicators)
//    · FPV vector traces (historical path)
//    · Guidance beam visualization (LOC + GS beams)
//    · Clipping boundary visualization (combiner edges)
//    · Optical center indicator
//    · Collimation correction vectors
//
//  All visualizations are driven by L:var toggles written by the
//  JS debug overlay and read in the C++ pipeline.
// ============================================================================

// This header provides the DebugOverlay type and debug_init / debug_read_lvars
// functions, defined in module.h and implemented in calibration.cpp.

// The DebugOverlay state struct is defined in module.h.
// The init and read functions are also declared in module.h.

#endif // C_HUD_VERIFICATION_H
