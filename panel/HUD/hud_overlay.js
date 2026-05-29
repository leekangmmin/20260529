// ============================================================================
//  Conformal HUD – Runway Symbology  |  Overlay renderer (Canvas 2-D)
//  Phase 2 + Phase 3: reads L: vars from the WASM C++ pipeline and draws
//  the runway outline on a transparent HUD canvas.
//
//  Features (v1.1.0):
//    · HUD active flag (L:C_HUD_HUD_Active) – enables/disables drawing
//    · ILS deviation crosshair (L:C_HUD_ILS_GS, L:C_HUD_ILS_LOC)
//    · Weather-adaptive line width (L:C_HUD_WeatherLineW)
//    · Weather-adaptive opacity  (L:C_HUD_WeatherAlpha)
//    · Per-vertex runway outline (L:C_HUD_RunwayV{n}_{X,Y})
// ============================================================================

(function () {
    "use strict";

    // -----------------------------------------------------------------------
    //  DOM handles
    // -----------------------------------------------------------------------
    var canvas = document.getElementById("hud_canvas");
    var ctx    = canvas.getContext("2d", { alpha: true });  // transparent BG

    // -----------------------------------------------------------------------
    //  Constants
    // -----------------------------------------------------------------------
    var CROSSHAIR_RADIUS = 12;   // px – ILS deviation crosshair half-size
    var MAX_VERTS        = 4;    // we only draw the first 4 vertices as a quad

    // -----------------------------------------------------------------------
    //  Size canvas to the viewport every frame (handles resize / DPI change)
    // -----------------------------------------------------------------------
    function fit_canvas() {
        var w = window.innerWidth;
        var h = window.innerHeight;

        if (canvas.width !== w || canvas.height !== h) {
            canvas.width  = w;
            canvas.height = h;
        }
    }

    // -----------------------------------------------------------------------
    //  Read a numeric L: var (returns NaN if unavailable)
    // -----------------------------------------------------------------------
    function read_lvar(name) {
        try {
            return SimVar.GetSimVarValue(name, "number");
        } catch (e) {
            return NaN;
        }
    }

    // -----------------------------------------------------------------------
    //  PHASE 4: Get combiner geometry (screen-space rect for clipping)
    // -----------------------------------------------------------------------
    function get_combiner() {
        var sx = read_lvar("L:C_HUD_CombinerScreenX");
        var sy = read_lvar("L:C_HUD_CombinerScreenY");
        var sw = read_lvar("L:C_HUD_CombinerScreenW");
        var sh = read_lvar("L:C_HUD_CombinerScreenH");
        if (!isNaN(sx) && !isNaN(sy) && !isNaN(sw) && !isNaN(sh) && sw > 0 && sh > 0) {
            return { x: sx, y: sy, w: sw, h: sh };
        }
        return { x: 0, y: 0, w: canvas.width, h: canvas.height };
    }

    // -----------------------------------------------------------------------
    //  Compute HUD centre (screen centre)
    -----------------------------------------------------------------------
    // -----------------------------------------------------------------------
    function get_hud_centre() {
        var cx = read_lvar("L:C_HUD_ScreenCX");
        var cy = read_lvar("L:C_HUD_ScreenCY");
        // Fall back to canvas centre if L: vars not available
        if (isNaN(cx) || cx <= 0) cx = canvas.width  * 0.5;
        if (isNaN(cy) || cy <= 0) cy = canvas.height * 0.5;
        return { x: cx, y: cy };
    }

    // -----------------------------------------------------------------------
    //  Draw the ILS deviation crosshair (glideslope horizontal, loc vertical)
    // -----------------------------------------------------------------------
    function draw_ils_crosshair(centre, alpha) {
        var gs_raw  = read_lvar("L:C_HUD_ILS_GS");   // glideslope error (degrees)
        var loc_raw = read_lvar("L:C_HUD_ILS_LOC");   // localizer error (degrees)

        if (isNaN(gs_raw) || isNaN(loc_raw)) {
            return;  // no ILS signal yet
        }

        // Scale factor: 1 degree deviation ≈ 20 px on screen (roughly 2 dots)
        var SCALE = 20.0;

        // Clamp to reasonable bounds
        var gs  = Math.max(-2.0, Math.min(2.0, gs_raw))  * SCALE;
        var loc = Math.max(-2.0, Math.min(2.0, loc_raw)) * SCALE;

        // Crosshair centre shifts by deviation
        var cx = centre.x + loc;
        var cy = centre.y + gs;   // positive GS = below glidepath → up on HUD

        ctx.save();
        ctx.globalAlpha = alpha * 0.9;
        ctx.strokeStyle = "#00FF00";
        ctx.lineWidth   = 1.5;

        // Vertical line
        ctx.beginPath();
        ctx.moveTo(cx, cy - CROSSHAIR_RADIUS);
        ctx.lineTo(cx, cy + CROSSHAIR_RADIUS);
        ctx.stroke();

        // Horizontal line
        ctx.beginPath();
        ctx.moveTo(cx - CROSSHAIR_RADIUS, cy);
        ctx.lineTo(cx + CROSSHAIR_RADIUS, cy);
        ctx.stroke();

        // Circle
        ctx.beginPath();
        ctx.arc(cx, cy, CROSSHAIR_RADIUS * 0.4, 0, 2 * Math.PI);
        ctx.stroke();

        ctx.restore();
    }

    // -----------------------------------------------------------------------
    //  Draw the runway outline from projected vertices
    // -----------------------------------------------------------------------
    function draw_runway_outline(line_width, alpha) {
        var vert_count = read_lvar("L:C_HUD_RunwayVertCount");
        if (isNaN(vert_count) || vert_count < 2) {
            return;
        }

        var count = Math.min(vert_count, MAX_VERTS);
        var pts = [];

        for (var i = 0; i < count; ++i) {
            var sx = read_lvar("L:C_HUD_RunwayV" + i + "_X");
            var sy = read_lvar("L:C_HUD_RunwayV" + i + "_Y");
            pts.push({ x: sx, y: sy });
        }

        // Compute bounding-box centre of the quad for visibility test
        var cx = 0, cy = 0;
        for (var i = 0; i < pts.length; ++i) {
            cx += pts[i].x;
            cy += pts[i].y;
        }
        cx /= pts.length;
        cy /= pts.length;

        // Skip if the centre is off-screen / all vertices are NaN
        if (isNaN(cx) || isNaN(cy) ||
            cx < -1000 || cx > canvas.width  + 1000 ||
            cy < -1000 || cy > canvas.height + 1000) {
            return;
        }

        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.strokeStyle = "#00FF00";
        ctx.lineWidth   = line_width;

        // Draw the outline as a closed polygon
        ctx.beginPath();
        for (var i = 0; i < pts.length; ++i) {
            if (isNaN(pts[i].x) || isNaN(pts[i].y)) {
                // Skip NaN vertices (behind camera) – start a new subpath
                ctx.closePath();
                continue;
            }
            if (i === 0) {
                ctx.moveTo(pts[i].x, pts[i].y);
            } else {
                ctx.lineTo(pts[i].x, pts[i].y);
            }
        }
        ctx.closePath();
        ctx.stroke();

        ctx.restore();
    }

    // -----------------------------------------------------------------------
    //  Main draw function – orchestrates all HUD elements
    // -----------------------------------------------------------------------
    function draw() {
        // Always clear to transparent first
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // --- PHASE 4: Check HUD deployment state ---
        var deploy_phase = read_lvar("L:C_HUD_Deploy_Phase");
        var deploy_fraction = read_lvar("L:C_HUD_Deploy_Fraction");
        
        // If deployment state is available, check it
        if (!isNaN(deploy_phase)) {
            if (deploy_phase < 1.5) {
                return;  // HUD stowed - don't render
            }
            // Apply deployment fraction to alpha
            if (!isNaN(deploy_fraction) && deploy_fraction >= 0.0) {
                // Will be multiplied with alpha below
            }
        } else {
            // Fallback: legacy HUD active check
            var hud_active = read_lvar("L:C_HUD_HUD_Active");
            if (isNaN(hud_active) || hud_active < 0.5) {
                return;
            }
        }

        // --- Read weather-adaptive rendering params ---
        var line_width = read_lvar("L:C_HUD_WeatherLineW");
        var alpha      = read_lvar("L:C_HUD_WeatherAlpha");

        // Fallback defaults
        if (isNaN(line_width) || line_width <= 0) line_width = 2.0;
        if (isNaN(alpha) || alpha <= 0)           alpha      = 0.8;
        
        // Apply deployment fraction to alpha (fade during transition)
        if (!isNaN(deploy_fraction) && deploy_fraction >= 0.0) {
            alpha *= Math.max(0.0, Math.min(1.0, deploy_fraction));
        }

        // --- PHASE 4: Clip to combiner glass area ---
        var comb = get_combiner();
        ctx.save();
        if (comb && comb.w > 0 && comb.h > 0) {
            ctx.beginPath();
            ctx.rect(comb.x, comb.y, comb.w, comb.h);
            ctx.clip();
        }

        // --- Compute HUD centre ---
        var centre = get_hud_centre();

        // --- Draw ILS crosshair ---
        draw_ils_crosshair(centre, alpha);

        // --- Draw runway outline ---
        draw_runway_outline(line_width, alpha);
        
        ctx.restore();
    }

    // -----------------------------------------------------------------------
    //  Per-frame loop (rAF tied to Coherent GT paint cycle)
    // -----------------------------------------------------------------------
    function frame() {
        fit_canvas();
        draw();
        requestAnimationFrame(frame);
    }

    // -----------------------------------------------------------------------
    //  Bootstrap
    // -----------------------------------------------------------------------
    fit_canvas();
    requestAnimationFrame(frame);

    // Debug: log that the overlay JS has loaded successfully.
    console.log("[C_HUD] overlay.js v1.1.0 loaded  –  canvas " +
                canvas.width + "×" + canvas.height);
})();
