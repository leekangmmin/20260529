#ifndef C_HUD_BOEING_HGS_BEHAVIOR_H
#define C_HUD_BOEING_HGS_BEHAVIOR_H

// ============================================================================
//  Conformal HUD – Boeing HGS Behavior Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  PHASE 1 — UNIFIED AIRCRAFT BEHAVIOR ARCHITECTURE
//
//  Concrete IHudAircraftBehavior for Boeing-style HGS aircraft:
//    · PMDG 737-700/800
//    · PMDG 777-300ER
//    · WT/Asobo 787-10
//
//  This wraps the existing pipeline logic that was previously inline
//  in main.cpp into a clean virtual-method interface.  All FPV, flare,
//  rollout, CAT III, declutter, and optics calls now go through this
//  class when a Boeing aircraft is detected.
// ============================================================================

#include "ihud_aircraft_behavior.h"
#include "../flare.h"
#include "../fpv.h"
#include "../rollout.h"
#include "../confidence.h"
#include "../declutter.h"
#include "../visual_response.h"
#include "../stabilization.h"
#include "../aircraft_profiles.h"

// ============================================================================
//  1.  Boeing HGS behavior class
// ============================================================================

class BoeingHGSBehavior : public IHudAircraftBehavior {
public:
    BoeingHGSBehavior();
    virtual ~BoeingHGSBehavior() = default;

    // --- Identification ---
    HudAircraftCategory category() const override { return HudAircraftCategory::BOEING_HGS; }
    const char* name() const override { return "Boeing HGS"; }

    // --- FPV ---
    void compute_fpv(
        const HudBehaviorContext& ctx,
        const HUDProfile*         profile,
        const Mat4*               b2w,
        Vec3                      eye_offset,
        FLOAT64                   focal_px,
        FPVState*                 fpv) override;

    // --- Flare ---
    void compute_flare(
        const HudBehaviorContext& ctx,
        const HUDProfile*         profile,
        Vec2                      td_ref,
        bool                      guidance_valid,
        FLOAT64                   gs_error_deg,
        FlareState*               flare,
        FlareCue*                 flare_cue,
        TouchdownZone*            td_zone) override;

    // --- Rollout ---
    void compute_rollout(
        const HudBehaviorContext& ctx,
        FLOAT64                   runway_heading_deg,
        FLOAT64                   lateral_deviation_m,
        RolloutState*             rs,
        RolloutCue*               cue) override;

    // --- CAT III ---
    void compute_cat3(
        const HudBehaviorContext& ctx,
        ConfidenceState*          cs,
        ConfidenceRenderParams*   render) override;

    // --- Declutter ---
    void compute_declutter(
        const HudBehaviorContext& ctx,
        HudFlightPhase            phase,
        DeclutterState*           ds) override;

    // --- Optics ---
    void compute_optics(
        const HudBehaviorContext& ctx,
        const HUDProfile*         profile,
        VisualResponseState*      vs,
        VisualRenderParams*       render) override;

private:
    // Boeing-specific internal state (replaces some g_hud fields)
    HUDStabilisation    m_stab;
    VisualResponseState m_visual;
    bool                m_stab_init;
    bool                m_visual_init;
};

#endif // C_HUD_BOEING_HGS_BEHAVIOR_H
