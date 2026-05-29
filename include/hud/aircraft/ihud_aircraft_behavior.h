// ============================================================================
//  Conformal HUD – Unified Aircraft Behavior Interface
//  MSFS 2024  ·  C++17  ·  WASM
//
//  PHASE 1 — UNIFIED AIRCRAFT BEHAVIOR ARCHITECTURE
//
//  Pure virtual interface that defines the contract for all aircraft-
//  specific HUD behavior implementations.  Each supported aircraft
//  family (Boeing HGS, Airbus A350 HUD, etc.) provides a concrete
//  implementation that encapsulates its unique:
//    · FPV computation and filtering philosophy
//    · Flare law guidance
//    · Rollout augmentation
//    · CAT III confidence and augmentation
//    · Declutter priority scheme
//    · Optical realism and symbology styling
//
//  The pipeline (main.cpp) calls these virtual methods through
//  a pointer obtained from the aircraft detector — no aircraft-
//  specific #ifdefs or switch statements in the core loop.
//
//  NOTE: Because this is a freestanding WASM environment (-nostdlib,
//  -fno-exceptions, no heap), behavior instances are statically
//  allocated singletons, not heap-allocated objects.
// ============================================================================

#include "../../module.h"
#include "../../projection.h"
#include "../flare.h"        // FlareState, FlareCue, TouchdownZone
#include "../fpv.h"          // FPVState
#include "../rollout.h"      // RolloutState, RolloutCue
#include "../confidence.h"   // ConfidenceState, ConfidenceRenderParams
#include "../declutter.h"    // DeclutterState, FlightPhase
#include "../visual_response.h" // VisualResponseState, VisualRenderParams
#include "../aircraft_profiles.h" // HUDProfile

// ============================================================================
//  1.  Flight phase enumeration (shared across all behaviors)
// ============================================================================

/// Unified flight phase used by compute_declutter and other phase-aware
/// methods.  Maps to DeclutterState::FlightPhase but kept here so the
/// interface does not depend on declutter internals at the signature level.
enum class HudFlightPhase : int {
    CRUISE     = 0,
    APPROACH   = 1,
    FLARE      = 2,
    ROLLOUT    = 3,
    TAXI       = 4,
};

// ============================================================================
//  2.  Aircraft behavior category
// ============================================================================

enum class HudAircraftCategory : int {
    UNKNOWN     = 0,
    BOEING_HGS  = 1,   // Boeing HGS-style (PMDG 737/777, WT 787)
    AIRBUS_HUD  = 2,   // Airbus A350 HUD (iniBuilds A350)
};

// ============================================================================
//  3.  Behavior context — data passed into every compute method
// ============================================================================

/// Context struct aggregating all inputs needed by the behavior methods.
/// The pipeline populates this from g_state and passes it down so that
/// behavior implementations are stateless with respect to global state.
struct HudBehaviorContext {
    // --- Aircraft state ---
    FLOAT64 ac_lat;
    FLOAT64 ac_lon;
    FLOAT64 ac_alt_m;
    FLOAT64 ac_hdg_true;
    FLOAT64 ac_pitch_deg;
    FLOAT64 ac_bank_deg;
    FLOAT64 ac_groundspeed_ms;
    FLOAT64 ac_true_airspeed_ms;
    FLOAT64 ac_vertical_speed_ms;
    FLOAT64 ac_track_deg_true;
    FLOAT64 ac_radio_alt_m;
    FLOAT64 ac_accel_ms2;
    FLOAT64 ac_indicated_airspeed_ms;
    bool    ac_on_ground;

    // --- Weather ---
    FLOAT64 visibility_m;
    FLOAT64 ambient_luminance;

    // --- ILS ---
    FLOAT64 ils_loc_dots;
    FLOAT64 ils_gs_dots;
    bool    ils_loc_captured;
    bool    ils_gs_captured;

    // --- Timing ---
    FLOAT64 dt_s;
    int     frame_counter;

    // --- Screen ---
    int     screen_w;
    int     screen_h;
};

// ============================================================================
//  4.  Behavior context for publish phase
// ============================================================================

struct HudPublishContext {
    FLOAT64 screen_cx;
    FLOAT64 screen_cy;
};

// ============================================================================
//  5.  The interface
// ============================================================================

class IHudAircraftBehavior {
public:
    virtual ~IHudAircraftBehavior() = default;

    // ----------------------------------------------------------------
    //  Identification
    // ----------------------------------------------------------------
    virtual HudAircraftCategory category() const = 0;
    virtual const char* name() const = 0;

    // ----------------------------------------------------------------
    //  FPV
    // ----------------------------------------------------------------
    /// Compute the Flight Path Vector from raw aircraft state.
    /// @param ctx       Behavior context (aircraft state, timing, screen)
    /// @param profile   Active HUD profile (for alignment offsets)
    /// @param b2w       Body-to-world rotation matrix
    /// @param eye_offset Corrected HUD eye position (body frame)
    /// @param focal_px  Focal length in pixels
    /// @param fpv       [out] FPV state
    virtual void compute_fpv(
        const HudBehaviorContext& ctx,
        const HUDProfile*         profile,
        const Mat4*               b2w,
        Vec3                      eye_offset,
        FLOAT64                   focal_px,
        FPVState*                 fpv) = 0;

    // ----------------------------------------------------------------
    //  Flare
    // ----------------------------------------------------------------
    /// Compute flare guidance state and project flare cues.
    /// @param ctx       Behavior context
    /// @param profile   Active HUD profile
    /// @param td_ref    Touchdown reference point on HUD (pixels)
    /// @param guidance_valid Whether guidance data is valid
    /// @param gs_error_deg  Glideslope error (degrees)
    /// @param flare     [out] Flare state
    /// @param flare_cue [out] Flare cue rendering params
    /// @param td_zone   [out] Touchdown zone rendering params
    virtual void compute_flare(
        const HudBehaviorContext& ctx,
        const HUDProfile*         profile,
        Vec2                      td_ref,
        bool                      guidance_valid,
        FLOAT64                   gs_error_deg,
        FlareState*               flare,
        FlareCue*                 flare_cue,
        TouchdownZone*            td_zone) = 0;

    // ----------------------------------------------------------------
    //  Rollout
    // ----------------------------------------------------------------
    /// Compute rollout guidance after touchdown.
    /// @param ctx       Behavior context
    /// @param runway_heading_deg  Runway true heading
    /// @param lateral_deviation_m Lateral deviation from centerline (m)
    /// @param rs        [out] Rollout state
    /// @param cue       [out] Rollout cue rendering params
    virtual void compute_rollout(
        const HudBehaviorContext& ctx,
        FLOAT64                   runway_heading_deg,
        FLOAT64                   lateral_deviation_m,
        RolloutState*             rs,
        RolloutCue*               cue) = 0;

    // ----------------------------------------------------------------
    //  CAT III
    // ----------------------------------------------------------------
    /// Compute CAT III augmentation and confidence.
    /// @param ctx       Behavior context
    /// @param cs        [in/out] Confidence state (updated with CAT III logic)
    /// @param render    [out] Confidence-based render parameters
    virtual void compute_cat3(
        const HudBehaviorContext& ctx,
        ConfidenceState*          cs,
        ConfidenceRenderParams*   render) = 0;

    // ----------------------------------------------------------------
    //  Declutter
    // ----------------------------------------------------------------
    /// Compute declutter priorities and symbol visibility.
    /// @param ctx       Behavior context
    /// @param phase     Current flight phase
    /// @param ds        [out] Declutter state
    virtual void compute_declutter(
        const HudBehaviorContext& ctx,
        HudFlightPhase            phase,
        DeclutterState*           ds) = 0;

    // ----------------------------------------------------------------
    //  Optics / Symbology styling
    // ----------------------------------------------------------------
    /// Compute optical realism and symbology styling parameters.
    /// @param ctx       Behavior context
    /// @param profile   Active HUD profile
    /// @param vs        [in/out] Visual response state
    /// @param render    [out] Visual render params
    virtual void compute_optics(
        const HudBehaviorContext& ctx,
        const HUDProfile*         profile,
        VisualResponseState*      vs,
        VisualRenderParams*       render) = 0;
};

// ============================================================================
//  6.  Factory function — get the appropriate behavior for an aircraft
// ============================================================================

/// Get the appropriate IHudAircraftBehavior instance for the given aircraft ID.
/// Returns a pointer to a statically-allocated singleton (no heap used).
///
/// In the freestanding WASM environment (-nostdlib), we cannot use
/// operator new/delete.  Instead, the factory returns a pointer to a
/// pre-allocated global instance that is configured for the aircraft.
///
/// @param aircraft_id  Aircraft title string from MSFS (e.g. "PMDG 737-800")
/// @return             Pointer to a behavior instance, or to a safe-mode
///                     fallback if the aircraft is unsupported.
IHudAircraftBehavior* hud_behavior_create(const char* aircraft_id);


#endif // C_HUD_IHUD_AIRCRAFT_BEHAVIOR_H
