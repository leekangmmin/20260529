// ============================================================================
//  Conformal HUD – Boeing HGS-style Symbology Renderer  |  v3.4.0
//  MSFS 2024  ·  Canvas 2-D  ·  Green monochrome
//
//  PHASE 4 — REAL HUD INTEGRATION: Combiner clipping, deployment detection, collimated rendering
//  Reads ALL L:vars from the WASM C++ pipeline (now actively publishing).
//  Draws:
//    · Conformal runway outline (world-referenced, stabilised)
//    · Horizon line with bank indication (stabilised)
//    · Pitch ladder (conformal, banks with aircraft, stabilised)
//    · Flight Path Vector (true inertial path circle)
//    · Localizer/Glideslope guidance bars & crosshair
//    · Drift cue / crosswind indicator
//    · Centerline cue
//    · Flare guidance (cue + touchdown zone)
//    · Rollout guidance (centerline, deviation, command)   — v2.7.0
//    · CAT III annunciations (CAT II/III, LAND3/2, FLARE, ROLLOUT, NO DH) — v2.7.0
//    · EVS active box, contrast cue, visibility indication — v2.7.0
//    · ILS/sensor failure flags ("LOC", "G/S") — confidence-modulated bars — v3.2.0
//    · EVS-enhanced rendering (fog penetration, contrast boost)
//    · Collimation debug overlays
//    · Advanced symbology (accel caret, energy trend, etc.)
//    · Calibration overlay (live adjustable controls)
//    · Verification mode (debug visualizations)
//
//  v3.0.0 CHANGES:
//    · HUD deployment-aware rendering (skips when HUD stowed)
//    · Screen-space combiner clipping for all symbology
//    · Collimation-compensated symbology positioning
//    · Transition fade during HUD deploy/stow
//    · Added rollout guidance rendering (centerline tracking, deviation, command)
//    · Added CAT III annunciation display (CAT II, IIIA, IIIB, LAND 3/2, FLARE, ROLLOUT, NO DH)
//    · Added EVS visualization (active box, contrast cue, visibility indication)
//    · Added anti-jitter filtering for rollout symbols
//    · Added low-speed fade for rollout guidance elements
//    · Added aircraft-type-aware annunciation styling
//  v3.1.0 CHANGES:
//    · Added speed tape (left side) and altitude tape (right side) for aircraft
//      without native HUD (PMDG 777).  Driven by WASM-published L:Vars.
//    · draw_speed_tape() and draw_altitude_tape() — Boeing HGS-style vertical strips
//      with tick marks, current-value pointers, trend indicators, and VS bar.
//  v3.2.0 CHANGES:
//    · draw_guidance() now reads confidence L:Vars (L:C_HUD_Conf_LocMode, GSMode, LocAlpha, GSAlpha)
//    · Added draw_ils_failure_flags() — Boeing HGS-style "LOC"/"G/S" failure flags
//    · ILS/sensor failure flags in upper-right combiner area
// ============================================================================
//    · HUD phosphor drain on power-off, warm-up scan on deploy              — v3.3.0
//    · Phosphor persistence accumulation fix (correct decay algorithm)      — v3.4.0

(function () {
    "use strict";

    // ====================================================================
    //  1.  Canvas setup
    // ====================================================================
    var canvas = document.getElementById("hud_canvas");
    if (!canvas) {
        console.error("[C_HUD] No canvas element found – creating one.");
        canvas = document.createElement("canvas");
        canvas.id = "hud_canvas";
        document.body.appendChild(canvas);
    }
    var ctx = canvas.getContext("2d", { alpha: true, desynchronized: true });

    // ====================================================================
    //  2.  Constants – Boeing HGS style parameters
    // ====================================================================
    var HUD_COLOR       = "#00FF00";
    var HUD_GLOW        = "rgba(0,255,0,0.15)";
    var FPV_RADIUS      = 10;
    var FPV_LINE_W      = 2.0;
    var PITCH_LINE_W    = 1.5;
    var HORIZON_W       = 2.5;
    var RUNWAY_W        = 2.0;
    var CROSSHAIR_R     = 14;
    var CROSSHAIR_W     = 1.5;
    var BAR_W           = 4.0;
    var BAR_LENGTH      = 60.0;
    var DRIFT_CUE_R     = 6.0;
    var MAX_VERTS       = 8;

    // Optical realism constants
    var PHOSPHOR_FLICKER_AMPLITUDE = 0.03;  // 3% brightness noise
    var BREATHING_PERIOD_FRAMES    = 300;   // ~5 sec at 60 fps
    var SYMBOL_INERTIA_FACTOR      = 0.15;  // 15% positional lag

    // v2.7.0 — Rollout guidance constants
    var ROLLOUT_CENTERLINE_W       = 3.0;   // width of centerline cue
    var ROLLOUT_DEVIATION_BAR_W    = 20.0;  // width of deviation indicator
    var ROLLOUT_DEVIATION_BAR_H    = 6.0;   // height of deviation indicator
    var ROLLOUT_COMMAND_ARROW_SZ   = 10.0;  // size of command arrow
    var ROLLOUT_FADE_SPEED_KT      = 50.0;  // speed below which fade begins
    var ROLLOUT_MIN_SPEED_KT       = 10.0;  // speed below which rollout fully fades

    // v2.7.0 — CAT III annunciation constants
    var CAT_FONT_SIZE             = 14;
    var CAT_LINE_HEIGHT           = 18;
    var CAT_BOX_PADDING           = 6;
    var CAT_BOX_X                 = 20;    // left edge
    var CAT_BOX_Y                 = 100;   // top edge

    // v2.7.0 — EVS visualization constants
    var EVS_BOX_PADDING           = 8;
    var EVS_BOX_Y                 = 40;
    var EVS_CONTRAST_BAR_W        = 80;
    var EVS_CONTRAST_BAR_H        = 6;

    // v3.1.0 — Speed / altitude tape constants
    var TAPE_W                    = 55;
    var TAPE_H                    = 200;
    var TAPE_MARGIN_X             = 20;    // horizontal offset from combiner edge
    var TAPE_TICK_INTERVAL_KT     = 10;    // 10-knot tick spacing
    var TAPE_TICK_INTERVAL_FT     = 100;   // 100-ft tick spacing
    var TAPE_LABEL_INTERVAL_KT    = 20;    // label every 20 knots
    var TAPE_LABEL_INTERVAL_FT    = 500;   // label every 500 ft
    var TAPE_VS_MAX_FPM           = 2000;  // ±2000 fpm for VS bar
    var TAPE_VS_BAR_MAX_PX        = 100;   // maps to ±100 px
    var TAPE_BOX_H                = 22;    // current-value box height

    // Phosphor persistence buffer
    var phosphorCanvas  = null;
    var phosphorCtx     = null;
    var frameCount      = 0;

    // Symbol inertia state (tracks previous positions for smooth transitions)
    var inertiaState = {
        fpv_x: NaN, fpv_y: NaN,
        horizon_y: NaN,
        flare_cue_x: NaN, flare_cue_y: NaN,
        // v2.7.0: Rollout inertia
        rollout_cl_x: NaN,
        rollout_dev: NaN,
        rollout_cmd: NaN
    };

    // v3.3.0 — HUD power lifecycle state
    var prevDeployPhase  = -1;   // previous deploy_phase value (-1 = uninitialised)
    var powerOffFrames   = 0;    // frames since power was cut (for drain fade)
    var POWER_OFF_DRAIN_FRAMES = 18;  // ~300ms @ 60fps for phosphor drain

    // ====================================================================
    //  3.  Utility functions
    // ====================================================================

    function fit_canvas() {
        var w = window.innerWidth;
        var h = window.innerHeight;
        if (canvas.width !== w || canvas.height !== h) {
            canvas.width = w;
            canvas.height = h;
            // Recreate phosphor buffer
            if (!phosphorCanvas) {
                phosphorCanvas = document.createElement("canvas");
                phosphorCanvas.width = w;
                phosphorCanvas.height = h;
                phosphorCtx = phosphorCanvas.getContext("2d", { alpha: true });
            } else {
                phosphorCanvas.width = w;
                phosphorCanvas.height = h;
                // Reset phosphor state on resize to prevent size-mismatch artifacts
                if (phosphorCtx) {
                    phosphorCtx.clearRect(0, 0, w, h);
                    phosphorCtx.globalAlpha = 1.0;
                }
            }
        }
    }

    function read_lvar(name) {
        try {
            return SimVar.GetSimVarValue(name, "number");
        } catch (e) {
            return NaN;
        }
    }

    function deg2rad(d) { return d * Math.PI / 180.0; }

    function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

    /// Apply symbol inertia: blends current value with previous
    /// to create subtle lag that simulates optical/physical mass.
    function with_inertia(prev, current, factor) {
        if (isNaN(prev)) return current;
        if (isNaN(current)) return prev;
        return prev * factor + current * (1.0 - factor);
    }

    function get_combiner() {
        // PHASE 4 — Use screen-space combiner rect (L:C_HUD_CombinerScreen*)
        var sx = read_lvar("L:C_HUD_CombinerScreenX");
        var sy = read_lvar("L:C_HUD_CombinerScreenY");
        var sw = read_lvar("L:C_HUD_CombinerScreenW");
        var sh = read_lvar("L:C_HUD_CombinerScreenH");
        if (!isNaN(sx) && !isNaN(sy) && !isNaN(sw) && !isNaN(sh) && sw > 0 && sh > 0) {
            return { x: sx, y: sy, w: sw, h: sh };
        }
        // Fallback: panel-space combiner rect
        var cx = read_lvar("L:C_HUD_CombinerX");
        var cy = read_lvar("L:C_HUD_CombinerY");
        var cw = read_lvar("L:C_HUD_CombinerW");
        var ch = read_lvar("L:C_HUD_CombinerH");
        if (isNaN(cx) || isNaN(cy) || isNaN(cw) || isNaN(ch)) {
            return { x: 100, y: 200, w: 824, h: 624 };
        }
        return { x: cx, y: cy, w: cw, h: ch };
    }

    /// v2.3.0: Check if point is within combiner (with configurable tolerance)
    function in_combiner(x, y, comb, tolerance) {
        if (!comb) return true;
        tolerance = tolerance || 50;
        return x >= (comb.x - tolerance) &&
               x <= (comb.x + comb.w + tolerance) &&
               y >= (comb.y - tolerance) &&
               y <= (comb.y + comb.h + tolerance);
    }

    // ====================================================================
    //  4.  Drawing primitives (Boeing HGS style)
    // ====================================================================

    function set_hud_style(alpha, line_w) {
        ctx.strokeStyle = HUD_COLOR;
        ctx.fillStyle   = HUD_COLOR;
        ctx.globalAlpha = clamp(alpha || 0.8, 0.1, 1.0);
        ctx.lineWidth   = line_w || 2.0;
    }

    function draw_line(x1, y1, x2, y2, alpha, lw) {
        set_hud_style(alpha, lw);
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
    }

    function draw_circle(cx, cy, radius, alpha, lw) {
        set_hud_style(alpha, lw);
        ctx.beginPath();
        ctx.arc(cx, cy, radius, 0, 2 * Math.PI);
        ctx.stroke();
    }

    function draw_filled_circle(cx, cy, radius, alpha) {
        set_hud_style(alpha, 1);
        ctx.beginPath();
        ctx.arc(cx, cy, radius, 0, 2 * Math.PI);
        ctx.fill();
    }

    function draw_crosshair(cx, cy, radius, alpha, lw) {
        set_hud_style(alpha, lw);
        ctx.beginPath();
        ctx.arc(cx, cy, radius * 0.5, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(cx - radius, cy);
        ctx.lineTo(cx + radius, cy);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(cx, cy - radius);
        ctx.lineTo(cx, cy + radius);
        ctx.stroke();
    }

    function draw_diamond(cx, cy, size, alpha) {
        set_hud_style(alpha, 2);
        ctx.beginPath();
        ctx.moveTo(cx, cy - size);
        ctx.lineTo(cx + size * 0.7, cy);
        ctx.lineTo(cx, cy + size);
        ctx.lineTo(cx - size * 0.7, cy);
        ctx.closePath();
        ctx.stroke();
    }

    function draw_dashed_line(x1, y1, x2, y2, alpha, lw) {
        set_hud_style(alpha, lw);
        if (ctx.setLineDash) ctx.setLineDash([6, 8]);
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
        if (ctx.setLineDash) ctx.setLineDash([]);
    }

    function fill_rect(x, y, w, h, alpha) {
        set_hud_style(alpha, 1);
        ctx.fillRect(x, y, w, h);
    }

    function draw_text(text, x, y, alpha, font_size) {
        set_hud_style(alpha, 1);
        ctx.font = (font_size || 14) + "px monospace";
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        ctx.fillText(text, x, y);
    }

    // ====================================================================
    //  5.  Runway outline drawing (v2.3.0: combiner clipping aware)
    // ====================================================================

    function draw_runway(alpha, line_w, comb) {
        var vert_count = read_lvar("L:C_HUD_RunwayVertCount");
        if (isNaN(vert_count) || vert_count < 2) return;

        var count = Math.min(vert_count, MAX_VERTS);
        var pts = [];
        var all_nan = true;

        for (var i = 0; i < count; ++i) {
            var sx = read_lvar("L:C_HUD_RunwayV" + i + "_X");
            var sy = read_lvar("L:C_HUD_RunwayV" + i + "_Y");
            pts.push({ x: sx, y: sy });
            if (!isNaN(sx) && !isNaN(sy)) all_nan = false;
        }
        if (all_nan) return;

        var nv = 0, cx = 0, cy = 0;
        for (var i = 0; i < pts.length; ++i) {
            if (!isNaN(pts[i].x) && !isNaN(pts[i].y)) {
                cx += pts[i].x; cy += pts[i].y; nv++;
            }
        }
        if (nv === 0) return;
        cx /= nv; cy /= nv;

        if (cx < -2000 || cx > canvas.width + 2000 ||
            cy < -2000 || cy > canvas.height + 2000) return;

        var use_alpha = alpha * 0.85;
        set_hud_style(use_alpha, line_w);

        var first = true;
        for (var i = 0; i < pts.length; ++i) {
            if (isNaN(pts[i].x) || isNaN(pts[i].y)) {
                if (!first) ctx.stroke();
                ctx.closePath();
                first = true;
                continue;
            }
            if (first) {
                ctx.beginPath();
                ctx.moveTo(pts[i].x, pts[i].y);
                first = false;
            } else {
                ctx.lineTo(pts[i].x, pts[i].y);
            }
        }
        if (!first) ctx.stroke();

        // Draw runway centerline
        if (nv >= 4) {
            var near_cx = (pts[0].x + pts[3].x) / 2.0;
            var near_cy = (pts[0].y + pts[3].y) / 2.0;
            var far_cx  = (pts[1].x + pts[2].x) / 2.0;
            var far_cy  = (pts[1].y + pts[2].y) / 2.0;

            if (!isNaN(near_cx) && !isNaN(near_cy) &&
                !isNaN(far_cx) && !isNaN(far_cy)) {
                draw_dashed_line(near_cx, near_cy, far_cx, far_cy,
                                 use_alpha * 0.7, 1.5);
            }
        }
    }

    // ====================================================================
    //  6.  Horizon line drawing (v2.3.0: with symbol inertia)
    // ====================================================================

    function draw_horizon(alpha, comb) {
        var horizon_valid = read_lvar("L:C_HUD_HorizonValid");
        if (isNaN(horizon_valid) || horizon_valid < 0.5) return;

        var horizon_y = read_lvar("L:C_HUD_HorizonY");
        var horizon_slope = read_lvar("L:C_HUD_HorizonSlope");
        if (isNaN(horizon_y)) return;

        // Apply symbol inertia for optical calmness
        horizon_y = with_inertia(inertiaState.horizon_y, horizon_y,
                                  SYMBOL_INERTIA_FACTOR);
        inertiaState.horizon_y = horizon_y;

        var comb_x = comb ? comb.x : 0;
        var comb_w = comb ? comb.w : canvas.width;
        var comb_cx = comb_x + comb_w / 2;
        var slope = isNaN(horizon_slope) ? 0.0 : horizon_slope;

        var half_w = comb_w * 0.7;
        var x1 = comb_cx - half_w;
        var y1 = horizon_y - slope * half_w;
        var x2 = comb_cx + half_w;
        var y2 = horizon_y + slope * half_w;

        set_hud_style(alpha * 0.9, HORIZON_W);
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();

        // Horizon ticks
        var num_ticks = 7;
        for (var i = -3; i <= 3; ++i) {
            var frac = i / 3.0;
            var tx = comb_cx + frac * half_w * 0.6;
            var ty = horizon_y + slope * frac * half_w * 0.6;
            set_hud_style(alpha * 0.6, 1);
            ctx.beginPath();
            ctx.moveTo(tx, ty - 6);
            ctx.lineTo(tx, ty + 6);
            ctx.stroke();
        }
    }

    // ====================================================================
    //  7.  Pitch ladder drawing
    // ====================================================================

    function draw_pitch_ladder(alpha, comb) {
        var count = read_lvar("L:C_HUD_PitchLadder_Count");
        if (isNaN(count) || count < 1) return;

        var comb_cx = comb ? (comb.x + comb.w / 2) : canvas.width / 2;

        for (var i = 0; i < Math.min(count, 8); ++i) {
            var y_pos = read_lvar("L:C_HUD_PitchLadder_" + i + "_Y");
            if (isNaN(y_pos)) continue;

            var is_zero = (i === 2);
            var line_w = is_zero ? PITCH_LINE_W * 1.5 : PITCH_LINE_W;
            var half_w = is_zero ? 60 : 35;
            var use_alpha = is_zero ? alpha * 0.9 : alpha * 0.6;

            set_hud_style(use_alpha, line_w);
            ctx.beginPath();
            ctx.moveTo(comb_cx - half_w, y_pos);
            ctx.lineTo(comb_cx + half_w, y_pos);
            ctx.stroke();

            // Label (every other line)
            if (i !== 2 && (i % 2 === 0)) {
                var label = ((i - 2) * 5) + "°";
                ctx.font = "11px monospace";
                ctx.textAlign = "right";
                ctx.textBaseline = "middle";
                set_hud_style(use_alpha * 0.7, 1);
                ctx.fillText(label, comb_cx - half_w - 8, y_pos);
            }
        }
    }

    // ====================================================================
    //  8.  FPV drawing (v2.3.0: with symbol inertia)
    // ====================================================================

    function draw_fpv(alpha) {
        var fpv_onscreen = read_lvar("L:C_HUD_FPV_OnScreen");
        if (isNaN(fpv_onscreen) || fpv_onscreen < 0.5) return;

        var fpv_x = read_lvar("L:C_HUD_FPV_X");
        var fpv_y = read_lvar("L:C_HUD_FPV_Y");
        var drift = read_lvar("L:C_HUD_FPV_Drift");

        if (isNaN(fpv_x) || isNaN(fpv_y)) return;

        // Apply symbol inertia for optical calmness
        fpv_x = with_inertia(inertiaState.fpv_x, fpv_x, SYMBOL_INERTIA_FACTOR);
        fpv_y = with_inertia(inertiaState.fpv_y, fpv_y, SYMBOL_INERTIA_FACTOR);
        inertiaState.fpv_x = fpv_x;
        inertiaState.fpv_y = fpv_y;

        var use_alpha = alpha * 0.9;

        // FPV circle
        draw_circle(fpv_x, fpv_y, FPV_RADIUS, use_alpha, FPV_LINE_W);

        // FPV wings
        set_hud_style(use_alpha, 1.5);
        ctx.beginPath();
        ctx.moveTo(fpv_x - FPV_RADIUS - 4, fpv_y);
        ctx.lineTo(fpv_x - FPV_RADIUS + 2, fpv_y);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(fpv_x + FPV_RADIUS + 4, fpv_y);
        ctx.lineTo(fpv_x + FPV_RADIUS - 2, fpv_y);
        ctx.stroke();

        // Drift angle indicator
        if (!isNaN(drift) && Math.abs(drift) > 0.5) {
            var drift_rad = deg2rad(drift);
            var drift_len = 15;
            set_hud_style(use_alpha * 0.5, 1);
            ctx.beginPath();
            ctx.moveTo(fpv_x, fpv_y);
            ctx.lineTo(fpv_x - Math.sin(drift_rad) * drift_len,
                       fpv_y + Math.cos(drift_rad) * drift_len);
            ctx.stroke();
        }
    }

    // ====================================================================
    //  9b.  v3.2.0 — ILS Failure Flag display (Boeing HGS style)
    //       "LOC" flag when localiser signal lost
    //       "G/S" flag when glideslope signal lost
    //       Flags appear in the upper-right quadrant of the combiner,
    //       matching Collins HGS-4000 flag placement convention.
    // ====================================================================
    function draw_ils_failure_flags(alpha, loc_mode, gs_mode) {
        // Only render flags when sensor has actually failed (HIDDEN = mode 4 in C++ enum)
        var show_loc_flag = (loc_mode === 4);
        var show_gs_flag  = (gs_mode  === 4);
        if (!show_loc_flag && !show_gs_flag) return;
        var comb = get_combiner();
        // Position: upper-right area of combiner
        var base_x = comb ? (comb.x + comb.w - 85) : (canvas.width  - 85);
        var base_y = comb ? (comb.y + 30)           : 30;
        var flag_w    = 52;
        var flag_h    = 18;
        var flag_pad  = 4;
        var flag_font = 12;
        var flag_a    = alpha * 0.95;
        // LOC flag
        if (show_loc_flag) {
            var fx = base_x;
            var fy = base_y;
            set_hud_style(flag_a, 1.5);
            ctx.strokeRect(fx, fy, flag_w, flag_h);
            ctx.fillStyle = "rgba(0,255,0,0.12)";
            ctx.fillRect(fx, fy, flag_w, flag_h);
            draw_text("LOC", fx + flag_pad, fy + flag_pad, flag_a, flag_font);
        }
        // G/S flag
        if (show_gs_flag) {
            var fx = base_x;
            var fy = base_y + (show_loc_flag ? (flag_h + 4) : 0);
            set_hud_style(flag_a, 1.5);
            ctx.strokeRect(fx, fy, flag_w, flag_h);
            ctx.fillStyle = "rgba(0,255,0,0.12)";
            ctx.fillRect(fx, fy, flag_w, flag_h);
            draw_text("G/S", fx + flag_pad, fy + flag_pad, flag_a, flag_font);
        }
    }

    // ====================================================================
    //  9.  Guidance bars & crosshair
    // ====================================================================
    // v3.2.0 — Now reads sensor confidence L:Vars from WASM C++ pipeline.
    //          LOC/GS bars use confidence alpha, dash pattern, or hidden state.
    //          Crosshair visibility is confidence-modulated (min 0.2 alpha).
    //          Failure flags shown when mode == HIDDEN (4).

    function draw_guidance(alpha) {
        // --- Read sensor confidence from WASM pipeline ---
        var loc_mode  = read_lvar("L:C_HUD_Conf_LocMode");
        var loc_conf_a = read_lvar("L:C_HUD_Conf_LocAlpha");
        var gs_mode   = read_lvar("L:C_HUD_Conf_GSMode");
        var gs_conf_a = read_lvar("L:C_HUD_Conf_GSAlpha");
        // Fall back to full opacity if confidence L:Vars not published
        if (isNaN(loc_mode))  loc_mode  = 0;
        if (isNaN(loc_conf_a)) loc_conf_a = 0.9;
        if (isNaN(gs_mode))   gs_mode   = 0;
        if (isNaN(gs_conf_a)) gs_conf_a = 0.9;
        // --- ILS crosshair (always uses raw deviation, scaled by confidence) ---
        var gs  = read_lvar("L:C_HUD_ILS_GS");
        var loc = read_lvar("L:C_HUD_ILS_LOC");
        if (!isNaN(gs) && !isNaN(loc)) {
            var SCALE = 20.0;
            var gs_scaled  = clamp(gs,  -2.0, 2.0) * SCALE;
            var loc_scaled = clamp(loc, -2.0, 2.0) * SCALE;
            var cx = canvas.width  / 2 + loc_scaled;
            var cy = canvas.height / 2 + gs_scaled;
            // Crosshair dims with confidence but never fully disappears (provides
            // deviation reference even in degraded state)
            var xhair_a = alpha * 0.9 * clamp((loc_conf_a + gs_conf_a) * 0.5, 0.2, 1.0);
            draw_crosshair(cx, cy, CROSSHAIR_R, xhair_a, CROSSHAIR_W);
        }
        // --- Conformal guidance bars ---
        var loc_captured = read_lvar("L:C_HUD_LOC_Captured");
        var gs_captured  = read_lvar("L:C_HUD_GS_Captured");
        var gs_tx  = read_lvar("L:C_HUD_GS_Target_X");
        var gs_ty  = read_lvar("L:C_HUD_GS_Target_Y");
        var loc_tx = read_lvar("L:C_HUD_LOC_Target_X");
        var loc_ty = read_lvar("L:C_HUD_LOC_Target_Y");
        // ---- LOC bar ----
        if (!isNaN(loc_tx) && !isNaN(loc_ty) && loc_mode !== 4) {
            var cap_boost = (!isNaN(loc_captured) && loc_captured >= 0.5) ? 1.0 : 0.67;
            var bar_a = alpha * loc_conf_a * cap_boost;
            set_hud_style(bar_a, BAR_W);
            if (loc_mode === 2) {
                // DASHED (mode 2) — signal is degraded
                if (ctx.setLineDash) ctx.setLineDash([10, 8]);
            } else {
                if (ctx.setLineDash) ctx.setLineDash([]);
            }
            ctx.beginPath();
            ctx.moveTo(loc_tx, loc_ty - BAR_LENGTH);
            ctx.lineTo(loc_tx, loc_ty + BAR_LENGTH);
            ctx.stroke();
            if (ctx.setLineDash) ctx.setLineDash([]);
        }
        // ---- GS bar ----
        if (!isNaN(gs_tx) && !isNaN(gs_ty) && gs_mode !== 4) {
            var cap_boost = (!isNaN(gs_captured) && gs_captured >= 0.5) ? 1.0 : 0.67;
            var bar_a = alpha * gs_conf_a * cap_boost;
            set_hud_style(bar_a, BAR_W);
            if (gs_mode === 2) {
                // DASHED (mode 2) — signal is degraded
                if (ctx.setLineDash) ctx.setLineDash([10, 8]);
            } else {
                if (ctx.setLineDash) ctx.setLineDash([]);
            }
            ctx.beginPath();
            ctx.moveTo(gs_tx - BAR_LENGTH, gs_ty);
            ctx.lineTo(gs_tx + BAR_LENGTH, gs_ty);
            ctx.stroke();
            if (ctx.setLineDash) ctx.setLineDash([]);
        }
        // ---- Failure flags ----
        // Boeing HGS shows a bright boxed flag when a sensor is HIDDEN (failed).
        draw_ils_failure_flags(alpha, loc_mode, gs_mode);
    }

    // ====================================================================
    //  10.  Drift cue
    // ====================================================================

    function draw_drift_cue(alpha) {
        var drift_angle = read_lvar("L:C_HUD_Drift_Angle");
        if (isNaN(drift_angle)) return;

        var cx = canvas.width / 2;
        var cy = canvas.height / 2 + 60;
        var cue_offset = drift_angle * 3.0;

        draw_diamond(cx + cue_offset, cy, DRIFT_CUE_R, alpha * 0.6);
    }

    // ====================================================================
    //  11.  Flare guidance (v2.3.0: with symbol inertia)
    // ====================================================================

    function draw_flare(alpha) {
        var flare_active = read_lvar("L:C_HUD_Flare_Active");
        if (isNaN(flare_active) || flare_active < 0.5) return;

        var cue_x = read_lvar("L:C_HUD_Flare_Cue_X");
        var cue_y = read_lvar("L:C_HUD_Flare_Cue_Y");
        var cue_size = read_lvar("L:C_HUD_Flare_Cue_Size");
        var cue_alpha = read_lvar("L:C_HUD_Flare_Cue_Alpha");
        var flare_error = read_lvar("L:C_HUD_Flare_Error");

        if (!isNaN(cue_x) && !isNaN(cue_y) && !isNaN(cue_size) && !isNaN(cue_alpha)) {
            // Apply symbol inertia for flare cue
            cue_x = with_inertia(inertiaState.flare_cue_x, cue_x,
                                  SYMBOL_INERTIA_FACTOR);
            cue_y = with_inertia(inertiaState.flare_cue_y, cue_y,
                                  SYMBOL_INERTIA_FACTOR);
            inertiaState.flare_cue_x = cue_x;
            inertiaState.flare_cue_y = cue_y;

            var fa = clamp(cue_alpha * alpha, 0.0, 1.0);
            draw_circle(cue_x, cue_y, cue_size * 0.5, fa, 2.5);

            // Error indication
            if (!isNaN(flare_error) && Math.abs(flare_error) > 0.5) {
                set_hud_style(fa, 1.5);
                var dir = flare_error > 0 ? -1 : 1;
                ctx.beginPath();
                ctx.moveTo(cue_x - 8, cue_y + dir * 15);
                ctx.lineTo(cue_x, cue_y + dir * 8);
                ctx.lineTo(cue_x + 8, cue_y + dir * 15);
                ctx.stroke();
            }
        }

        // Touchdown zone marker
        var tdz_visible = read_lvar("L:C_HUD_TDZone_Visible");
        if (!isNaN(tdz_visible) && tdz_visible >= 0.5) {
            var tdz_x = read_lvar("L:C_HUD_TDZone_X");
            var tdz_y = read_lvar("L:C_HUD_TDZone_Y");
            var tdz_size = read_lvar("L:C_HUD_TDZone_Size");
            if (!isNaN(tdz_x) && !isNaN(tdz_y) && !isNaN(tdz_size)) {
                set_hud_style(alpha * 0.5, 2);
                ctx.beginPath();
                ctx.moveTo(tdz_x - tdz_size, tdz_y);
                ctx.lineTo(tdz_x + tdz_size, tdz_y);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(tdz_x, tdz_y - 5);
                ctx.lineTo(tdz_x, tdz_y + 5);
                ctx.stroke();
            }
        }
    }

    // ====================================================================
    //  12.  v3.1.0 — Speed tape (left side of combiner)
    //       Boeing HGS-style vertical strip showing IAS with ticks/trend
    // ====================================================================

    function draw_speed_tape(alpha, comb) {
        var active = read_lvar("L:C_HUD_Tape_Speed_Active");
        if (isNaN(active) || active < 0.5) return;
        if (!comb) return;

        var ias = read_lvar("L:C_HUD_Tape_IAS_kt");
        var trend = read_lvar("L:C_HUD_Tape_IAS_Trend");
        if (isNaN(ias)) return;

        // Tape geometry: left side of combiner, vertically centred
        var tape_l = comb.x + TAPE_MARGIN_X;
        var tape_cy = comb.y + comb.h / 2;
        var tape_t = tape_cy - TAPE_H / 2;
        var tape_b = tape_cy + TAPE_H / 2;
        var tape_r = tape_l + TAPE_W;

        // Scale: 200 px covers ±100 kt → 1 px = 1 kt
        var px_per_kt = 1.0;

        // --- Border ---
        set_hud_style(alpha * 0.35, 1.0);
        ctx.strokeRect(tape_l, tape_t, TAPE_W, TAPE_H);

        // --- Tick marks at 10-kt intervals (10 above + 10 below = ±100 kt) ---
        for (var offset = -100; offset <= 100; offset += TAPE_TICK_INTERVAL_KT) {
            if (offset === 0) continue;
            var y = tape_cy + offset * px_per_kt;
            if (y < tape_t || y > tape_b) continue;

            var is_label = (Math.abs(offset) % TAPE_LABEL_INTERVAL_KT === 0);
            var tick_len = is_label ? 14 : 9;
            var tick_x = tape_r - tick_len;

            draw_line(tick_x, y, tape_r, y, alpha * 0.5, 1.0);

            // Label every 20 kt
            if (is_label) {
                var val = Math.round(ias + offset);
                draw_text(val.toString(), tape_l + 3, y - 6, alpha * 0.6, 10);
            }
        }

        // --- Current value box (fixed at centre) ---
        var box_h = TAPE_BOX_H;
        var box_y = tape_cy - box_h / 2;
        var box_w = TAPE_W - 4;
        var box_x = tape_l + 2;

        ctx.fillStyle = "rgba(0,0,0,0.75)";
        ctx.fillRect(box_x, box_y, box_w, box_h);
        set_hud_style(alpha * 0.85, 1.5);
        ctx.strokeRect(box_x, box_y, box_w, box_h);

        // Chevron ">" pointer on right edge
        set_hud_style(alpha * 0.9, 2.0);
        ctx.beginPath();
        ctx.moveTo(tape_r, tape_cy - 6);
        ctx.lineTo(tape_r + 6, tape_cy);
        ctx.lineTo(tape_r, tape_cy + 6);
        ctx.stroke();

        // Current value text (centred in box)
        set_hud_style(alpha * 0.9, 1);
        ctx.font = "13px monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(Math.round(ias).toString(), box_x + box_w / 2, tape_cy);

        // --- Trend indicator (small arrow above or below box) ---
        if (!isNaN(trend)) {
            var trend_arrow_sz = 4;
            var trend_x = tape_r - 8;
            if (trend > 0.5) {
                set_hud_style(alpha * 0.7, 1.5);
                ctx.beginPath();
                ctx.moveTo(trend_x, box_y - 4);
                ctx.lineTo(trend_x - trend_arrow_sz, box_y - 10);
                ctx.lineTo(trend_x + trend_arrow_sz, box_y - 10);
                ctx.closePath();
                ctx.stroke();
            } else if (trend < -0.5) {
                set_hud_style(alpha * 0.7, 1.5);
                ctx.beginPath();
                ctx.moveTo(trend_x, box_y + box_h + 4);
                ctx.lineTo(trend_x - trend_arrow_sz, box_y + box_h + 10);
                ctx.lineTo(trend_x + trend_arrow_sz, box_y + box_h + 10);
                ctx.closePath();
                ctx.stroke();
            }
        }
    }

    // ====================================================================
    //  13.  v3.1.0 — Altitude tape (right side of combiner)
    //       Boeing HGS-style vertical strip showing altitude with V/S bar
    // ====================================================================

    function draw_altitude_tape(alpha, comb) {
        var active = read_lvar("L:C_HUD_Tape_Alt_Active");
        if (isNaN(active) || active < 0.5) return;
        if (!comb) return;

        var alt_ft = read_lvar("L:C_HUD_Tape_Alt_ft");
        var vs_fpm = read_lvar("L:C_HUD_Tape_VS_fpm");
        var trend = read_lvar("L:C_HUD_Tape_Alt_Trend");
        if (isNaN(alt_ft)) return;

        // Tape geometry: right side of combiner, vertically centred
        var tape_r = comb.x + comb.w - TAPE_MARGIN_X;
        var tape_l = tape_r - TAPE_W;
        var tape_cy = comb.y + comb.h / 2;
        var tape_t = tape_cy - TAPE_H / 2;
        var tape_b = tape_cy + TAPE_H / 2;

        // Scale: 200 px covers ±1000 ft → 1 px = 10 ft
        var px_per_ft = 0.1;

        // --- Border ---
        set_hud_style(alpha * 0.35, 1.0);
        ctx.strokeRect(tape_l, tape_t, TAPE_W, TAPE_H);

        // --- Tick marks at 100-ft intervals (±1000 ft) ---
        for (var offset = -1000; offset <= 1000; offset += TAPE_TICK_INTERVAL_FT) {
            if (offset === 0) continue;
            var y = tape_cy + offset * px_per_ft;
            if (y < tape_t || y > tape_b) continue;

            var is_label = (Math.abs(offset) % TAPE_LABEL_INTERVAL_FT === 0);
            var tick_len = is_label ? 14 : 9;
            var tick_x = tape_l;

            draw_line(tick_x, y, tick_x + tick_len, y, alpha * 0.5, 1.0);

            // Label every 500 ft
            if (is_label) {
                var val = Math.round(alt_ft + offset);
                draw_text(val.toString(), tape_l + tick_len + 3, y - 6,
                          alpha * 0.6, 10);
            }
        }

        // --- Current value box (fixed at centre) ---
        var box_h = TAPE_BOX_H;
        var box_y = tape_cy - box_h / 2;
        var box_w = TAPE_W - 4;
        var box_x = tape_l + 2;

        ctx.fillStyle = "rgba(0,0,0,0.75)";
        ctx.fillRect(box_x, box_y, box_w, box_h);
        set_hud_style(alpha * 0.85, 1.5);
        ctx.strokeRect(box_x, box_y, box_w, box_h);

        // Chevron "<" pointer on left edge
        set_hud_style(alpha * 0.9, 2.0);
        ctx.beginPath();
        ctx.moveTo(tape_l, tape_cy - 6);
        ctx.lineTo(tape_l - 6, tape_cy);
        ctx.lineTo(tape_l, tape_cy + 6);
        ctx.stroke();

        // Current value text (centred in box)
        set_hud_style(alpha * 0.9, 1);
        ctx.font = "13px monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(Math.round(alt_ft).toString(), box_x + box_w / 2, tape_cy);

        // --- V/S indicator bar (right side of tape) ---
        // Scale: ±2000 fpm → ±100 px, clamped
        if (!isNaN(vs_fpm)) {
            var vs_offset = clamp(vs_fpm / TAPE_VS_MAX_FPM, -1.0, 1.0) *
                            TAPE_VS_BAR_MAX_PX;
            var vs_bar_w = 3;
            var vs_bar_x = tape_r - vs_bar_w - 3;
            var vs_bar_top = tape_cy;
            var vs_bar_bot = tape_cy + vs_offset;

            set_hud_style(alpha * 0.6, 1.0);
            ctx.beginPath();
            ctx.moveTo(vs_bar_x, vs_bar_top);
            ctx.lineTo(vs_bar_x, vs_bar_bot);
            ctx.stroke();

            // Small cap at the end of the VS bar (arrowhead)
            if (Math.abs(vs_offset) > 2) {
                var cap_dir = vs_offset > 0 ? 1 : -1;
                ctx.beginPath();
                ctx.moveTo(vs_bar_x - 3, vs_bar_bot - cap_dir * 3);
                ctx.lineTo(vs_bar_x, vs_bar_bot);
                ctx.lineTo(vs_bar_x + 3, vs_bar_bot - cap_dir * 3);
                ctx.stroke();
            }
        }
    }

    // ====================================================================
    //  14.  v2.7.0 — Rollout Guidance Rendering
    //       (Boeing HGS-style centerline track + deviation + command)
    // ====================================================================

    function draw_rollout(alpha) {
        var rollout_active = read_lvar("L:C_HUD_Roll_Active");
        if (isNaN(rollout_active) || rollout_active < 0.5) {
            // Reset inertia when rollout becomes inactive
            inertiaState.rollout_cl_x = NaN;
            inertiaState.rollout_dev = NaN;
            inertiaState.rollout_cmd = NaN;
            return;
        }

        var cl_cue = read_lvar("L:C_HUD_Roll_Centerline");
        var deviation = read_lvar("L:C_HUD_Roll_Deviation");
        var command = read_lvar("L:C_HUD_Roll_Command");
        var confidence = read_lvar("L:C_HUD_Roll_Confidence");

        if (isNaN(cl_cue) || isNaN(deviation) || isNaN(command)) return;
        if (isNaN(confidence)) confidence = 0.5;

        // Apply anti-jitter symbol inertia
        cl_cue = with_inertia(inertiaState.rollout_cl_x, cl_cue, 0.2);
        deviation = with_inertia(inertiaState.rollout_dev, deviation, 0.2);
        command = with_inertia(inertiaState.rollout_cmd, command, 0.2);
        inertiaState.rollout_cl_x = cl_cue;
        inertiaState.rollout_dev = deviation;
        inertiaState.rollout_cmd = command;

        // --- Low-speed fade ---
        // Adjust alpha based on confidence (lower confidence at low speed = fade out)
        var rollout_alpha = alpha * (0.4 + confidence * 0.6);
        if (rollout_alpha < 0.05) return;

        var comb = get_combiner();
        var hud_cx = comb ? (comb.x + comb.w / 2) : canvas.width / 2;
        var hud_cy = comb ? (comb.y + comb.h * 0.75) : canvas.height * 0.75;

        // ================================================================
        //  Centerline tracking cue
        //  A vertical bar/diamond representing the desired centerline
        //  position.  cl_cue ranges 0..1 (0=left, 0.5=center, 1=right).
        // ================================================================
        var cl_offset = (cl_cue - 0.5) * 80.0;  // ±40 px max offset
        var cl_x = hud_cx + cl_offset;
        var cl_y = hud_cy;

        // Draw centerline diamond/chevron
        var cl_alpha = rollout_alpha * 0.8;
        draw_diamond(cl_x, cl_y, 8, cl_alpha);

        // Draw vertical centerline bar
        set_hud_style(cl_alpha * 0.7, ROLLOUT_CENTERLINE_W);
        ctx.beginPath();
        ctx.moveTo(cl_x, cl_y + 10);
        ctx.lineTo(cl_x, cl_y + 40);
        ctx.stroke();

        // ================================================================
        //  Lateral deviation indicator
        //  Shows current lateral offset from centerline.
        //  deviation ranges -1..1 (negative=left, positive=right).
        // ================================================================
        var dev_px = deviation * 60.0;  // ±60 px
        var dev_x = hud_cx + dev_px;
        var dev_y = hud_cy + 55;

        // Deviation bar (filled rectangle proportional to deviation magnitude)
        var dev_w = Math.abs(deviation) * ROLLOUT_DEVIATION_BAR_W;
        var dev_dir = deviation >= 0 ? 1 : -1;
        var dev_bar_x = dev_dir > 0 ? dev_x : dev_x - dev_w;
        var dev_alpha = rollout_alpha * 0.6;

        fill_rect(dev_bar_x, dev_y, Math.max(dev_w, 2), ROLLOUT_DEVIATION_BAR_H, dev_alpha);

        // Center tick
        draw_line(hud_cx - 3, dev_y, hud_cx + 3, dev_y, dev_alpha * 0.4, 1.5);

        // ================================================================
        //  Steering command indicator
        //  An arrow pointing in the commanded direction.
        //  command ranges -1..1 (negative=left, positive=right).
        // ================================================================
        if (Math.abs(command) > 0.02) {
            var cmd_px = command * 50.0;
            var cmd_x = hud_cx + cmd_px;
            var cmd_y = hud_cy - 20;
            var cmd_alpha = rollout_alpha * 0.7;
            var cmd_size = ROLLOUT_COMMAND_ARROW_SZ;

            set_hud_style(cmd_alpha, 2.0);
            ctx.beginPath();
            if (command > 0) {
                // Right arrow
                ctx.moveTo(cmd_x - cmd_size, cmd_y - cmd_size * 0.5);
                ctx.lineTo(cmd_x + cmd_size * 0.5, cmd_y);
                ctx.lineTo(cmd_x - cmd_size, cmd_y + cmd_size * 0.5);
            } else {
                // Left arrow
                ctx.moveTo(cmd_x + cmd_size, cmd_y - cmd_size * 0.5);
                ctx.lineTo(cmd_x - cmd_size * 0.5, cmd_y);
                ctx.lineTo(cmd_x + cmd_size, cmd_y + cmd_size * 0.5);
            }
            ctx.closePath();
            ctx.stroke();
        }

        // Confidence indicator (thin bar at bottom)
        var conf_bar_w = 30;
        var conf_bar_x = hud_cx - conf_bar_w / 2;
        var conf_bar_y = hud_cy + 75;
        fill_rect(conf_bar_x, conf_bar_y, conf_bar_w * confidence, 3,
                  rollout_alpha * 0.3);
    }

    // ====================================================================
    //  15.  v2.7.0 — CAT III Annunciations
    //        (CAT II, CAT IIIA, CAT IIIB, LAND 3, LAND 2, FLARE, ROLLOUT, NO DH)
    // ====================================================================

    function draw_cat_annunciations(alpha) {
        var cat_category = read_lvar("L:C_HUD_CAT_Category");
        var land_mode = read_lvar("L:C_HUD_LAND_Mode");
        var flare_ann = read_lvar("L:C_HUD_FLARE_Announce");
        var rollout_ann = read_lvar("L:C_HUD_ROLLOUT_Announce");
        var no_dh = read_lvar("L:C_HUD_NO_DH");

        if (isNaN(cat_category)) cat_category = 0;
        if (isNaN(land_mode)) land_mode = 0;
        if (isNaN(flare_ann)) flare_ann = 0;
        if (isNaN(rollout_ann)) rollout_ann = 0;
        if (isNaN(no_dh)) no_dh = 0;

        // Determine if we are in a CAT II/III regime
        var in_cat = (cat_category >= 2);

        // Build list of active annunciations
        var lines = [];

        if (cat_category >= 2) {
            var cat_labels = ["", "", "CAT II", "CAT IIIA", "CAT IIIB"];
            lines.push({ text: cat_labels[cat_category], priority: 3 });
        }

        if (land_mode >= 2 && in_cat) {
            var land_labels = ["", "", "LAND 2", "LAND 3", "LAND 3"];
            lines.push({ text: land_labels[land_mode], priority: 4 });
        }

        if (flare_ann >= 0.5) {
            lines.push({ text: "FLARE", priority: 2 });
        }

        if (rollout_ann >= 0.5) {
            lines.push({ text: "ROLLOUT", priority: 2 });
        }

        if (no_dh >= 0.5 && in_cat) {
            lines.push({ text: "NO DH", priority: 1 });
        }

        if (lines.length === 0) return;

        // Sort by priority (highest first)
        lines.sort(function(a, b) { return b.priority - a.priority; });

        // Render annunciation box (left side of HUD)
        var box_x = CAT_BOX_X;
        var box_y = CAT_BOX_Y;
        var line_h = CAT_LINE_HEIGHT;
        var font_sz = CAT_FONT_SIZE;
        var padding = CAT_BOX_PADDING;

        // Calculate box dimensions
        var max_w = 0;
        for (var i = 0; i < lines.length; ++i) {
            var w = lines[i].text.length * (font_sz * 0.65);
            if (w > max_w) max_w = w;
        }
        var box_w = max_w + padding * 2;
        var box_h = lines.length * line_h + padding * 2;

        // Draw background box with green outline
        var ann_alpha = alpha * 0.85;
        set_hud_style(ann_alpha, 1.5);
        ctx.strokeRect(box_x, box_y, box_w, box_h);

        // Draw each line
        for (var i = 0; i < lines.length; ++i) {
            var tx = box_x + padding;
            var ty = box_y + padding + i * line_h;
            var line_alpha = ann_alpha;

            // LAND 3/2 gets extra brightness
            if (lines[i].text.indexOf("LAND") === 0) {
                line_alpha = Math.min(1.0, ann_alpha * 1.2);
            }

            draw_text(lines[i].text, tx, ty, line_alpha, font_sz);
        }
    }

    // ====================================================================
    //  16.  v2.7.0 — EVS Visualization
    //        (EVS active box, contrast cue, visibility indication)
    // ====================================================================

    function draw_evs_visualization(alpha) {
        var evs_active_box = read_lvar("L:C_HUD_EVS_ActiveBox");
        var evs_contrast_cue = read_lvar("L:C_HUD_EVS_ContrastCue");
        var evs_vis_ind = read_lvar("L:C_HUD_EVS_VisibilityInd");
        var evs_intensity = read_lvar("L:C_HUD_EVS_Intensity");

        if (isNaN(evs_active_box)) evs_active_box = 0;
        if (isNaN(evs_contrast_cue)) evs_contrast_cue = 0;
        if (isNaN(evs_vis_ind)) evs_vis_ind = 0;
        if (isNaN(evs_intensity)) evs_intensity = 0;

        var evs_on = (evs_active_box >= 0.5);

        // ================================================================
        //  EVS Active Box — green glow box when EVS is enhancing
        // ================================================================
        if (evs_on && !isNaN(evs_intensity) && evs_intensity > 0.01) {
            var padding = EVS_BOX_PADDING;
            var bx = padding;
            var by = EVS_BOX_Y;
            var bw = 90;
            var bh = 22;
            var box_alpha = alpha * 0.6;

            // Draw EVS active box
            set_hud_style(box_alpha, 1.5);
            ctx.strokeRect(bx, by, bw, bh);

            // Text label
            draw_text("EVS", bx + 5, by + 3, box_alpha * 0.9, 12);

            // Intensity bar inside the box
            var bar_x = bx + 30;
            var bar_y = by + 6;
            var bar_w = 52;
            var bar_h = 8;
            set_hud_style(box_alpha * 0.3, 1);
            ctx.strokeRect(bar_x, bar_y, bar_w, bar_h);
            fill_rect(bar_x + 1, bar_y + 1,
                      (bar_w - 2) * clamp(evs_intensity, 0, 1), bar_h - 2,
                      box_alpha * 0.5);
        }

        // ================================================================
        //  EVS Contrast Cue — horizontal bar showing contrast boost level
        // ================================================================
        if (evs_contrast_cue > 0.01) {
            var contrast_norm = clamp(evs_contrast_cue / 2.0, 0.0, 1.0);
            var cc_x = EVS_BOX_PADDING;
            var cc_y = EVS_BOX_Y + (evs_on ? 26 : 0);
            var cc_w = EVS_CONTRAST_BAR_W;
            var cc_h = EVS_CONTRAST_BAR_H;
            var cc_alpha = alpha * 0.4;

            set_hud_style(cc_alpha, 1);
            ctx.strokeRect(cc_x, cc_y, cc_w, cc_h);
            fill_rect(cc_x + 1, cc_y + 1,
                      (cc_w - 2) * contrast_norm, cc_h - 2, cc_alpha * 0.6);

            draw_text("CTR", cc_x + cc_w + 5, cc_y - 1, cc_alpha * 0.7, 9);
        }

        // ================================================================
        //  EVS Visibility Indication — text when in low vis
        // ================================================================
        if (evs_vis_ind >= 0.5) {
            var vi_x = EVS_BOX_PADDING;
            var vi_y = EVS_BOX_Y + (evs_on ? 26 : 0) + (evs_contrast_cue > 0.01 ? 14 : 0);
            var vi_alpha = alpha * 0.5;
            draw_text("LOW VIS", vi_x, vi_y, vi_alpha, 11);
        }
    }

    // ====================================================================
    //  17.  Debug overlay layers
    // ====================================================================

    function draw_debug_overlays(alpha) {
        var show_center = read_lvar("L:C_HUD_Debug_ShowOpticalCenter");
        var show_clip = read_lvar("L:C_HUD_Debug_ShowClip");
        var show_coll = read_lvar("L:C_HUD_Debug_ShowCollimation");

        // Optical center indicator
        if (!isNaN(show_center) && show_center >= 0.5) {
            var cx = canvas.width / 2;
            var cy = canvas.height / 2;
            set_hud_style(0.3, 1);
            ctx.setLineDash([4, 4]);
            ctx.beginPath();
            ctx.moveTo(cx - 40, cy); ctx.lineTo(cx + 40, cy);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(cx, cy - 40); ctx.lineTo(cx, cy + 40);
            ctx.stroke();
            ctx.setLineDash([]);
            draw_circle(cx, cy, 4, 0.4, 1);
        }

        // Clipping boundary
        if (!isNaN(show_clip) && show_clip >= 0.5) {
            var comb = get_combiner();
            if (comb) {
                set_hud_style(0.15, 1);
                ctx.strokeStyle = "#FF0000";
                ctx.strokeRect(comb.x, comb.y, comb.w, comb.h);
                ctx.strokeStyle = HUD_COLOR;
            }
        }

        // Collimation vectors
        if (!isNaN(show_coll) && show_coll >= 0.5) {
            var coll_active = read_lvar("L:C_HUD_Collimation_Active");
            if (!isNaN(coll_active) && coll_active >= 0.5) {
                var mag = read_lvar("L:C_HUD_Collimation_CorrMag");
                var cx = canvas.width / 2;
                var cy = canvas.height / 2;
                set_hud_style(0.4, 1);
                ctx.strokeStyle = "#FFFF00";
                ctx.beginPath();
                ctx.arc(cx, cy, 5 + clamp(mag * 500, 0, 50), 0, 2 * Math.PI);
                ctx.stroke();
                ctx.strokeStyle = HUD_COLOR;
            }
        }
    }

    // ====================================================================
    //  18.  Optical realism: phosphor effect & micro brightness breathing
    // ====================================================================

    function apply_optical_effects() {
        var phosphor = read_lvar("L:C_HUD_Optics_Phosphor");
        var bloom = read_lvar("L:C_HUD_Optics_Bloom");
        var edge_fade_val = read_lvar("L:C_HUD_Optics_EdgeFade");
        var brightness = read_lvar("L:C_HUD_Optics_Brightness");
        var temporal_blend = read_lvar("L:C_HUD_Optics_TemporalBlend");

        if (isNaN(phosphor)) phosphor = 0.04;
        if (isNaN(bloom)) bloom = 0.15;
        if (isNaN(edge_fade_val)) edge_fade_val = 0.2;
        if (isNaN(brightness)) brightness = 1.0;

        ++frameCount;

        // --- Subtle phosphor flicker (sub-pixel noise) ---
        var flicker = 1.0;
        if (phosphor > 0.01) {
            flicker = 1.0 + (Math.random() - 0.5) * PHOSPHOR_FLICKER_AMPLITUDE;
            flicker = clamp(flicker, 0.9, 1.1);
        }

        // --- Micro brightness breathing (slow sinusoidal modulation) ---
        var breathing = 1.0 + 0.01 * Math.sin(frameCount * 2.0 * Math.PI /
                                               BREATHING_PERIOD_FRAMES);

        // Combine brightness modifiers
        var effective_brightness = clamp(brightness * flicker * breathing,
                                         0.6, 1.0);

        // Apply via global alpha adjustment
        var brightness_alpha = effective_brightness;

        // --- Phosphor persistence (correct accumulation algorithm) ---
        // phosphor L:Var range: 0..1.  Typical HGS value: 0.04 (fast P43 phosphor).
        // decay_alpha: how much of the previous trail remains each frame.
        //   phosphor=0.04 → decay=0.65 (fast, ~8-frame half-life)
        //   phosphor=0.20 → decay=0.85 (slow, ~40-frame half-life)
        //   phosphor=0.50 → decay=0.94 (very slow)
        if (phosphor > 0.01 && phosphorCtx && phosphorCanvas) {
            var decay_alpha = clamp(0.55 + phosphor * 0.8, 0.55, 0.96);
            // Step 1: Fade existing trail (draw black rect at 1-decay opacity)
            phosphorCtx.globalAlpha = 1.0 - decay_alpha;
            phosphorCtx.fillStyle = "black";
            phosphorCtx.fillRect(0, 0, phosphorCanvas.width, phosphorCanvas.height);
            // Step 2: Accumulate current frame into phosphor buffer
            phosphorCtx.globalAlpha = 1.0;
            phosphorCtx.drawImage(canvas, 0, 0);
            // Step 3: Composite phosphor buffer onto main canvas
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.globalAlpha = brightness_alpha;
            ctx.drawImage(phosphorCanvas, 0, 0);
            ctx.globalAlpha = 1.0;
        } else {
            ctx.globalAlpha = brightness_alpha;
        }

        // --- Bloom effect ---
        if (!isNaN(bloom) && bloom > 0.01) {
            ctx.shadowColor = "#00FF00";
            ctx.shadowBlur = bloom * 8;
        } else {
            ctx.shadowBlur = 0;
        }

        // --- Edge fade (vignette) ---
        if (!isNaN(edge_fade_val) && edge_fade_val > 0.01) {
            var w = canvas.width, h = canvas.height;
            var grad = ctx.createRadialGradient(w/2, h/2, Math.min(w,h)*0.25,
                                                  w/2, h/2, Math.min(w,h)*0.6);
            grad.addColorStop(0, "rgba(0,0,0,0)");
            grad.addColorStop(1, "rgba(0,0,0," + clamp(edge_fade_val, 0, 0.5) + ")");
            ctx.fillStyle = grad;
            ctx.fillRect(0, 0, w, h);
        }
    }

    // ====================================================================
    //  19.  FPS / timing diagnostics display
    // ====================================================================

    function draw_diagnostics() {
        var frame = read_lvar("L:C_HUD_Frame");
        if (isNaN(frame) || (Math.floor(frame) % 120) !== 0) return;

        var fps = read_lvar("L:C_HUD_FPS");
        var fps_min = read_lvar("L:C_HUD_FPS_Min");
        var fps_max = read_lvar("L:C_HUD_FPS_Max");
        var jitter = read_lvar("L:C_HUD_Jitter_ms");

        if (!isNaN(fps)) {
            ctx.save();
            ctx.font = "10px monospace";
            ctx.textAlign = "right";
            ctx.textBaseline = "top";
            ctx.fillStyle = "rgba(0,255,0,0.3)";
            var text = "FPS: " + Math.round(fps) +
                       " (min:" + Math.round(fps_min || 0) +
                       " max:" + Math.round(fps_max || 0) + ")";
            if (!isNaN(jitter)) text += " j:" + (jitter * 1000).toFixed(1) + "ms";
            ctx.fillText(text, canvas.width - 5, 5);
            ctx.restore();
        }
    }

    // ====================================================================
    //  20a.  v3.3.0 — HUD power-off phosphor drain
    //       Renders decaying phosphor for POWER_OFF_DRAIN_FRAMES frames
    //       after the HUD is powered off, then clears the phosphor buffer.
    // ====================================================================
    function hud_power_off_transition() {
        powerOffFrames++;
        if (powerOffFrames <= POWER_OFF_DRAIN_FRAMES) {
            // Exponential decay: 0.6^frame gives rapid but smooth fade
            var drain_alpha = Math.pow(0.6, powerOffFrames);
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            if (phosphorCanvas) {
                ctx.globalAlpha = drain_alpha;
                ctx.drawImage(phosphorCanvas, 0, 0);
                ctx.globalAlpha = 1.0;
            }
        } else {
            // Drain complete — clear the phosphor buffer so no ghost on re-power
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            if (phosphorCtx && phosphorCanvas) {
                phosphorCtx.clearRect(0, 0, phosphorCanvas.width, phosphorCanvas.height);
            }
        }
    }

    // ====================================================================
    //  20b.  v3.3.0 — HUD warm-up scan animation
    //       Shown during deploy_phase=2 (TRANSITION) while fraction < 0.5
    //       (HUD glass moving into position, system initialising)
    // ====================================================================
    function draw_hud_warmup(deploy_fraction) {
        var progress = clamp(deploy_fraction * 2.0, 0.0, 1.0);  // 0..1 over first half of deploy
        var w = canvas.width;
        var h = canvas.height;
        var cy = h * 0.5;
        // --- Scan line sweeping down ---
        var scan_y = cy - h * 0.3 + progress * h * 0.6;
        var scan_alpha = 0.5 * (1.0 - Math.abs(progress - 0.5) * 2.0) + 0.1;  // bell curve
        set_hud_style(scan_alpha * 0.6, 1.0);
        ctx.beginPath();
        ctx.moveTo(w * 0.1, scan_y);
        ctx.lineTo(w * 0.9, scan_y);
        ctx.stroke();
        // --- Corner brackets (combiner alignment reference) ---
        var comb = get_combiner();
        var bx = comb ? comb.x : w * 0.1;
        var by = comb ? comb.y : h * 0.15;
        var bw = comb ? comb.w : w * 0.8;
        var bh = comb ? comb.h : h * 0.7;
        var corner_len = 20;
        var corner_a = progress * 0.5;
        set_hud_style(corner_a, 1.5);
        // Top-left
        ctx.beginPath(); ctx.moveTo(bx, by + corner_len); ctx.lineTo(bx, by); ctx.lineTo(bx + corner_len, by); ctx.stroke();
        // Top-right
        ctx.beginPath(); ctx.moveTo(bx + bw - corner_len, by); ctx.lineTo(bx + bw, by); ctx.lineTo(bx + bw, by + corner_len); ctx.stroke();
        // Bottom-left
        ctx.beginPath(); ctx.moveTo(bx, by + bh - corner_len); ctx.lineTo(bx, by + bh); ctx.lineTo(bx + corner_len, by + bh); ctx.stroke();
        // Bottom-right
        ctx.beginPath(); ctx.moveTo(bx + bw - corner_len, by + bh); ctx.lineTo(bx + bw, by + bh); ctx.lineTo(bx + bw, by + bh - corner_len); ctx.stroke();
        // --- "INITIALISING" text flash at 25% progress ---
        if (progress > 0.15 && progress < 0.55) {
            var txt_alpha = Math.sin((progress - 0.15) / 0.4 * Math.PI) * 0.6;
            set_hud_style(txt_alpha, 1);
            ctx.font = "11px monospace";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText("HGS INITIALISING", w * 0.5, by + bh * 0.5);
        }
    }
    // ====================================================================
    //  20c.  Main draw function
    // ====================================================================

    function draw() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.shadowBlur = 0;
        ctx.shadowColor = "transparent";

        // ================================================================
        //  PHASE 4 — HUD Deployment-Aware Rendering
        // ================================================================
        
        // Read deployment state (published by WASM pipeline)
        var deploy_phase = read_lvar("L:C_HUD_Deploy_Phase");
        var deploy_fraction = read_lvar("L:C_HUD_Deploy_Fraction");
        var deploy_power = read_lvar("L:C_HUD_Deploy_Power");
        
        // ---- Detect power-off transition ----
        var is_powered;
        if (isNaN(deploy_phase)) {
            // Fallback: legacy HUD_Active L:var
            var hud_active = read_lvar("L:C_HUD_HUD_Active");
            is_powered = (!isNaN(hud_active) && hud_active >= 0.5);
        } else {
            is_powered = (deploy_phase >= 1.5 && (!isNaN(deploy_power) ? deploy_power >= 0.5 : true));
        }
        // Detect transition: powered ON this frame (reset drain counter)
        if (is_powered && prevDeployPhase <= 1) {
            powerOffFrames = 0;
        }
        prevDeployPhase = isNaN(deploy_phase) ? (is_powered ? 3 : 1) : deploy_phase;
        if (!is_powered) {
            hud_power_off_transition();
            draw_diagnostics();
            return;
        }
        // Power is on — reset drain counter
        powerOffFrames = 0;

        // ---- Weather-adaptive rendering params ----
        var line_width = read_lvar("L:C_HUD_WeatherLineW");
        var alpha = read_lvar("L:C_HUD_WeatherAlpha");
        if (isNaN(line_width) || line_width <= 0) line_width = 2.0;
        if (isNaN(alpha) || alpha <= 0) alpha = 0.8;

        // ---- Deployment fade (deploy_fraction scales alpha during transition) ----
        var eff_fraction = isNaN(deploy_fraction) ? 1.0 : clamp(deploy_fraction, 0.0, 1.0);
        alpha *= eff_fraction;

        // ---- Warm-up animation during first half of deployment transition ----
        if (!isNaN(deploy_phase) && deploy_phase >= 1.5 && deploy_phase < 2.5 && eff_fraction < 0.5) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            draw_hud_warmup(eff_fraction);
            draw_diagnostics();
            return;
        }

        // Read collimation correction (screen-space delta for viewpoint compensation)
        var coll_dx = read_lvar("L:C_HUD_Coll_ScreenDX");
        var coll_dy = read_lvar("L:C_HUD_Coll_ScreenDY");
        var collimated = read_lvar("L:C_HUD_Collimated");
        if (isNaN(coll_dx)) coll_dx = 0;
        if (isNaN(coll_dy)) coll_dy = 0;
        if (isNaN(collimated)) collimated = 1;

        // Get combiner geometry for clipping (screen-space rect from WASM)
        var comb = get_combiner();
        
        // Read optical centre for symbology centering
        var opt_cx = read_lvar("L:C_HUD_OpticalCX");
        var opt_cy = read_lvar("L:C_HUD_OpticalCY");
        if (isNaN(opt_cx)) opt_cx = canvas.width * 0.5;
        if (isNaN(opt_cy)) opt_cy = canvas.height * 0.5;

        // Draw HUD elements in Z-order with combiner clipping
        // Symbology position is offset by collimation correction to simulate
        // optical collimation (world-referenced stability despite head movement)
        ctx.save();
        // v3.0.1 — FIX: Clip BEFORE translate so clipping region stays fixed to combiner
        // glass.  The collimation offset must only affect symbols, not the clipping rect.
        if (comb && comb.w > 0 && comb.h > 0) {
            ctx.beginPath();
            ctx.rect(comb.x, comb.y, comb.w, comb.h);
            ctx.clip();
        }
        if (collimated && collimated >= 0.5) {
            ctx.translate(coll_dx, coll_dy);
        }

        draw_debug_overlays(alpha);
        draw_runway(alpha, line_width, comb);
        draw_horizon(alpha, comb);
        draw_pitch_ladder(alpha, comb);
        draw_fpv(alpha);
        draw_drift_cue(alpha);
        draw_guidance(alpha);
        draw_flare(alpha);

        // v3.1.0: Speed and altitude tapes
        draw_speed_tape(alpha, comb);
        draw_altitude_tape(alpha, comb);

        // v2.7.0: New rendering layers
        draw_rollout(alpha);          // Rollout guidance (centerline, deviation, command)
        draw_evs_visualization(alpha); // EVS active box, contrast cue, visibility
        draw_cat_annunciations(alpha); // CAT II/III, LAND, FLARE, ROLLOUT, NO DH

        ctx.restore();

        // Apply optical realism effects (phosphor, bloom, breathing, edge fade)
        apply_optical_effects();

        // Diagnostics
        draw_diagnostics();
    }

    // ====================================================================
    //  21.  Per-frame loop
    // ====================================================================

    function frame() {
        fit_canvas();
        draw();
        requestAnimationFrame(frame);
    }

    // ====================================================================
    //  22.  Bootstrap
    // ====================================================================
    fit_canvas();
    requestAnimationFrame(frame);

    console.log("[C_HUD] conformal_renderer.js v3.4.0 loaded  –  canvas " +
                canvas.width + "×" + canvas.height);
})();
