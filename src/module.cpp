// ============================================================================
//  Conformal HUD – Runway Symbology  |  WASM gauge callbacks
//  MSFS SDK 0.23+  ·  C++17  ·  v2.7.0 — ROLLOUT/CAT-III/EVS ENHANCEMENT
//
//  Three gauge service callbacks:
//    PANEL_SERVICE_POST_INSTALL  →  resolve SimVar tokens
//    PANEL_SERVICE_PRE_UPDATE    →  read SimVars via module_update_read_vars()
//    PANEL_SERVICE_POST_DRAW     →  project & publish via module_update_*()
// ============================================================================

#include "module.h"
#include "hud/aircraft_profiles.h"

// ============================================================================
//  Cross-translation-unit declarations
//  (definitions live in main.cpp; declared here so the gauge callbacks below
//   can call them.)
// ============================================================================
bool module_update_read_vars(FsContext ctx);
bool module_update_project(const sGaugeDrawData* dd);
void module_update_publish(const sGaugeDrawData* dd);

// SimVar token globals shared with the projection pipeline (defined in main.cpp)
extern GAUGE_VAR g_simvar_plane_latitude;
extern GAUGE_VAR g_simvar_plane_longitude;
extern GAUGE_VAR g_simvar_plane_heading_deg_true;

// ============================================================================
//  Aircraft identification – HUD-capable model allowlist
// ============================================================================

static const char* const hud_allowed_aircraft[] = {
    "PMDG 737-800",
    "PMDG 737-700",
    "PMDG 737 MAX",
    "PMDG 777-300ER",
    "INI A350",
    "INIBUILDS A350",
    "INI A330",
    "FBW",
    "HEADWIND A330-900",
    "FENIX A320",
    "ASOBO BOEING 787-10",
    "WT_787_10",
    0  // sentinel
};

static bool aircraft_supports_hud(const char* name) {
    if (name == 0 || name[0] == '\0') return true;
    for (int i = 0; hud_allowed_aircraft[i] != 0; ++i) {
        const char* allowed = hud_allowed_aircraft[i];
        const char* n = name;
        const char* a = allowed;
        while (*n != '\0' && *a != '\0') {
            char nc = *n;
            char ac = *a;
            if (nc >= 'A' && nc <= 'Z') nc += 32;
            if (ac >= 'A' && ac <= 'Z') ac += 32;
            if (nc != ac) break;
            ++n; ++a;
        }
        if (*a == '\0') return true;
    }
    return false;
}

static void register_simvar(const char* name, GAUGE_VAR* out) {
    if (out == 0) return;
    *out = gauge_get_var_by_name(name, "number");
    if (*out == 0) {
        MSFS_Log("[C_HUD] WARN: SimVar '%s' not resolved", name);
    }
}

static void register_runway_vertex_tokens(GAUGE_VAR* vx, GAUGE_VAR* vy) {
    for (int i = 0; i < 8; ++i) {
        char buf_x[64], buf_y[64];
        unsigned int pos_x = 0, pos_y = 0;
        const char prefix[] = "L:C_HUD_RunwayV";
        for (unsigned int si = 0; prefix[si] != '\0' && pos_x < sizeof(buf_x) - 1; ++si) {
            buf_x[pos_x++] = prefix[si];
            buf_y[pos_y++] = prefix[si];
        }
        if (i < 10) {
            buf_x[pos_x++] = (char)('0' + i);
            buf_y[pos_y++] = (char)('0' + i);
        } else {
            buf_x[pos_x++] = (char)('0' + (i / 10));
            buf_x[pos_x++] = (char)('0' + (i % 10));
            buf_y[pos_y++] = (char)('0' + (i / 10));
            buf_y[pos_y++] = (char)('0' + (i % 10));
        }
        buf_x[pos_x++] = '_'; buf_x[pos_x++] = 'X'; buf_x[pos_x] = '\0';
        buf_y[pos_y++] = '_'; buf_y[pos_y++] = 'Y'; buf_y[pos_y] = '\0';
        register_simvar(buf_x, &vx[i]);
        register_simvar(buf_y, &vy[i]);
    }
}

static void register_pitch_ladder_tokens(GAUGE_VAR* pl) {
    for (int i = 0; i < 5; ++i) {
        char buf[64];
        unsigned int pos = 0;
        const char prefix[] = "L:C_HUD_PitchLadder_";
        for (unsigned int si = 0; prefix[si] != '\0' && pos < sizeof(buf) - 1; ++si) {
            buf[pos++] = prefix[si];
        }
        buf[pos++] = (char)('0' + i);
        buf[pos++] = '_'; buf[pos++] = 'Y';
        buf[pos] = '\0';
        register_simvar(buf, &pl[i]);
    }
}

// ============================================================================
//  PANEL_SERVICE_POST_INSTALL  –  resolve all tokens (called once)
// ============================================================================
GAUGE_CALLBACK gauge_callback_post_install(FsContext ctx,
                                           int       service_id,
                                           void*     pData) {
    (void)ctx;
    (void)service_id;
    (void)pData;

    MSFS_Log("[C_HUD] POST_INSTALL — resolving all tokens...");

    // Initialise aircraft profiles
    hud_profiles_init_all();

    // SimVar tokens
    register_simvar("PLANE LATITUDE",            &g_state.tok_plane_lat);
    register_simvar("PLANE LONGITUDE",           &g_state.tok_plane_lon);
    register_simvar("PLANE ALTITUDE",            &g_state.tok_plane_alt);
    register_simvar("PLANE HEADING DEGREES TRUE",&g_state.tok_plane_hdg);
    register_simvar("PLANE PITCH DEGREES",       &g_state.tok_plane_pitch);
    register_simvar("PLANE BANK DEGREES",        &g_state.tok_plane_bank);

    g_simvar_plane_latitude  = g_state.tok_plane_lat;
    g_simvar_plane_longitude = g_state.tok_plane_lon;
    g_simvar_plane_heading_deg_true = g_state.tok_plane_hdg;

    register_simvar("L:HUD_POWER_SWITCH",        &g_state.tok_hud_power);
    register_simvar("TITLE",                     &g_state.tok_aircraft_title);
    register_simvar("NAV GLIDE SLOPE ERROR",     &g_state.tok_nav_gs_error);
    register_simvar("NAV LOCALIZER ERROR",       &g_state.tok_nav_loc_error);
    register_simvar("AMBIENT VISIBILITY",        &g_state.tok_ambient_vis);
    register_simvar("GROUND VELOCITY",           &g_state.tok_groundspeed);
    register_simvar("TRUE AIRSPEED",             &g_state.tok_true_airspeed);
    register_simvar("VERTICAL SPEED",            &g_state.tok_vertical_speed);
    register_simvar("GPS GROUND TRUE HEADING",   &g_state.tok_track);

    register_simvar("RADIO HEIGHT",              &g_state.tok_radio_height);
    register_simvar("ACCELERATION BODY Z",       &g_state.tok_accel);
    register_simvar("AIRSPEED INDICATED",        &g_state.tok_indicated_airspeed);
    register_simvar("SIM ON GROUND",             &g_state.tok_on_ground);

    // v3.1.0 — Live eyepoint position for real-time collimation
    register_simvar("EYEPOINT POSITION X",       &g_state.tok_eyepoint_x);
    register_simvar("EYEPOINT POSITION Y",       &g_state.tok_eyepoint_y);
    register_simvar("EYEPOINT POSITION Z",       &g_state.tok_eyepoint_z);

    // v2.2.0 — NAV1 frequency
    register_simvar("NAV ACTIVE FREQUENCY:1",    &g_state.tok_nav1_freq);
    g_state.nav1_freq_mhz = 0.0;

    register_simvar("L:C_HUD_ScreenCX",          &g_state.tok_screen_cx);
    register_simvar("L:C_HUD_ScreenCY",          &g_state.tok_screen_cy);

    register_runway_vertex_tokens(g_state.tok_runway_vx, g_state.tok_runway_vy);
    register_pitch_ladder_tokens(g_state.tok_pitch_line_y);

    // Resolve L:var output table
    lvar_init();

    // Aircraft identification
    if (g_state.tok_aircraft_title != 0) {
        char title_buf[C_HUD_AIRCRAFT_ID_MAX];
        __builtin_memset(title_buf, 0, sizeof(title_buf));
        gauge_var_get(g_state.tok_aircraft_title,
                      title_buf, (int)sizeof(title_buf) - 1);
        title_buf[sizeof(title_buf) - 1] = '\0';

        if (title_buf[0] != '\0') {
            g_state.hud_allowed = aircraft_supports_hud(title_buf);
            unsigned int di = 0;
            while (di < sizeof(g_state.aircraft_id) - 1 && title_buf[di] != '\0') {
                g_state.aircraft_id[di] = title_buf[di];
                ++di;
            }
            g_state.aircraft_id[di] = '\0';
            MSFS_Log("[C_HUD] Aircraft: '%s'  HUD_allowed=%d",
                     title_buf, (int)g_state.hud_allowed);
        } else {
            g_state.hud_allowed = true;
            g_state.aircraft_id[0] = '\0';
        }
    } else {
        g_state.hud_allowed = true;
        g_state.aircraft_id[0] = '\0';
    }

    // Initialise filters
    ema_init(&g_state.ils_filter.gs,   0.35);
    ema_init(&g_state.ils_filter.loc,  0.35);
    g_state.weather.valid = false;

    g_state.initialised = true;
    g_state.module_load_complete = true;

    MSFS_Log("[C_HUD] POST_INSTALL complete  —  HUD system ready");
    return (GAUGE_RESULT)0;
}

// ============================================================================
//  PANEL_SERVICE_PRE_UPDATE  –  read SimVars
// ============================================================================
GAUGE_CALLBACK gauge_callback_pre_update(FsContext ctx,
                                          int       service_id,
                                          void*     pData) {
    (void)ctx;
    (void)service_id;
    (void)pData;
    if (!g_state.initialised) return (GAUGE_RESULT)0;
    module_update_read_vars(ctx);
    return (GAUGE_RESULT)0;
}

// ============================================================================
//  PANEL_SERVICE_POST_DRAW  –  project & publish
// ============================================================================
GAUGE_CALLBACK gauge_callback_post_draw(FsContext ctx,
                                         int       service_id,
                                         void*     pData) {
    (void)ctx;
    if (service_id != PANEL_SERVICE_POST_DRAW) return (GAUGE_RESULT)0;
    if (!g_state.initialised || pData == 0) return (GAUGE_RESULT)0;

    const sGaugeDrawData* dd = (const sGaugeDrawData*)pData;
    module_update_project(dd);
    module_update_publish(dd);
    return (GAUGE_RESULT)0;
}
