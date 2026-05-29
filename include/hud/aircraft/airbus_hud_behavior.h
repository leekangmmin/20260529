#ifndef C_HUD_AIRBUS_HUD_BEHAVIOR_H
#define C_HUD_AIRBUS_HUD_BEHAVIOR_H

// ============================================================================
//  Conformal HUD – Airbus HUD Behavior Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  PHASE 1 — UNIFIED AIRCRAFT BEHAVIOR ARCHITECTURE
//
//  Concrete IHudAircraftBehavior for Airbus-style HUD aircraft:
//    · iniBuilds A350
//
//  This wraps the existing A350-specific modules (AirbusFPVFilter,
//  A350FlareLaw, A350RolloutAugmentation, A350CatIIIState,
//  A350SymbologyStyle) into a clean virtual-method interface.
//
//  The Airbus HUD philosophy is fundamentally different from Boeing:
//    · Calm, filtered, highly augmented
//    · Low-workload, predictive, "smoothly computed" not raw
//    · CAT III natural operations
//    · Reduced pilot workload during all phases
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
#include "a350_profile.h"
#include "airbus_fpv.h"
#include "a350_flare_law.h"
#include "a350_rollout.h"
#include "a350_cat3.h"
#include "a350_symbology.h"

// ============================================================================
//  1.  Airbus HUD behavior class
// ============================================================================

class AirbusHUDBehavior : public IHudAircraftBehavior {
public:
    AirbusHUDBehavior();
    virtual ~AirbusHUDBehavior() = default;

    // --- Identification ---
    HudAircraftCategory category() const override { return HudAircraftCategory::AIRBUS_HUD; }
    const char* name() const override { return "Airbus A350 HUD"; }

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
    // Airbus-specific internal state
    AirbusFPVFilter         m_airbus_fpv;
    A350FlareLaw            m_a350_flare;
    A350RolloutAugmentation m_a350_rollout;
    A350CatIIIState         m_a350_cat3;
    A350SymbologyStyle      m_a350_symbology;
    A350HUDProfile          m_a350_profile;
    bool                    m_fpv_init;
    bool                    m_flare_init;
    bool                    m_rollout_init;
    bool                    m_cat3_init;
    bool                    m_symbology_init;
};

#endif // C_HUD_AIRBUS_HUD_BEHAVIOR_H
