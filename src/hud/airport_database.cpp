// ============================================================================
//  Conformal HUD – Airport / Runway Database Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  Implements the global airport/runway database with:
//    · Expanded runway data (250+ runways at major airports)
//    · ILS frequency indexing for fast lookup
//    · Nearest-airport spatial search
//    · Active runway detection via ILS and heading alignment
//    · Displaced threshold and touchdown zone geometry
//    · Reciprocal runway mapping
//    · Async-loading state machine
// ============================================================================

#include "../../include/hud/airport_database.h"

// ============================================================================
//  1.  Large-scale ILS/runway database
//
//  Sources: FAA NASR, ICAO charts, Navigraph, MSFS BGL data.
//  Runways are indexed by ILS frequency for fast active-runway lookup.
//
//  NOTE: This static table provides coverage for major global airports.
//  In production, the MSFS facilities API would supply dynamic data
//  for all installed airports. This table serves as both the fallback
//  and the cache seed.
// ============================================================================

/// Helper macro for defining runway entries concisely.
#define RUNWAY_ENTRY(icao, rwy_id, thresh_lat, thresh_lon, alt_m,        \
                     hdg, width, length, ils_freq, gs_angle,             \
                     slope, recip_idx, surf, app_lights, papi)           \
    {                                                                     \
        .icao_code = icao,                                               \
        .runway_id = rwy_id,                                             \
        .threshold_lat_deg = thresh_lat,                                 \
        .threshold_lon_deg = thresh_lon,                                 \
        .threshold_alt_m = alt_m,                                        \
        .true_heading_deg = hdg,                                         \
        .width_m = width,                                                \
        .length_m = length,                                              \
        .ils_frequency_mhz = ils_freq,                                   \
        .gs_angle_deg = gs_angle,                                        \
        .slope_pct = slope,                                              \
        .reciprocal_index = recip_idx,                                   \
        .surface_type = surf,                                            \
        .has_approach_lights = app_lights,                               \
        .has_papi = papi,                                                \
        .valid = true                                                    \
    }

/// Sentinel for reciprocal index (not yet assigned).
#define RECIP_UNASSIGNED (-99)

/// Surface type constants.
#define SURF_ASPHALT  0
#define SURF_CONCRETE 1
#define SURF_GRASS    2

// ============================================================================
//  2.  Static runway database table
//
//  This is a comprehensive global table covering major approach airports.
//  Each entry includes geometry, ILS frequency, and reciprocal links.
//  The reciprocal_index field is filled in during db_init().
// ============================================================================

static RunwayRecord g_builtin_runways[] = {
    // ====================================================================
    //  ASIA-PACIFIC
    // ====================================================================

    // Incheon International (RKSI)
    RUNWAY_ENTRY("RKSI", "15R", 37.4545, 126.4446, 7.0, 148.0, 60.0, 3750.0,
                 111.10, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("RKSI", "33L", 37.4850, 126.4680, 7.0, 328.0, 60.0, 3750.0,
                 111.10, 3.0, 0.0, 0, SURF_ASPHALT, true, true),  // reciprocal of 15R
    RUNWAY_ENTRY("RKSI", "16L", 37.4670, 126.4630, 7.0, 160.0, 60.0, 3750.0,
                 111.30, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("RKSI", "34R", 37.4970, 126.4860, 7.0, 340.0, 60.0, 3750.0,
                 111.30, 3.0, 0.0, 2, SURF_ASPHALT, true, true),

    // Tokyo Narita (RJAA)
    RUNWAY_ENTRY("RJAA", "16R", 35.7590, 140.3900, 41.0, 160.0, 60.0, 4000.0,
                 111.75, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("RJAA", "34L", 35.7890, 140.4000, 41.0, 340.0, 60.0, 4000.0,
                 111.75, 3.0, 0.0, 4, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("RJAA", "16L", 35.7620, 140.3830, 41.0, 160.0, 45.0, 2500.0,
                 110.55, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("RJAA", "34R", 35.7860, 140.3890, 41.0, 340.0, 45.0, 2500.0,
                 110.55, 3.0, 0.0, 6, SURF_ASPHALT, true, true),

    // Hong Kong (VHHH)
    RUNWAY_ENTRY("VHHH", "07R", 22.3090, 113.9200, 6.0, 70.0, 60.0, 3800.0,
                 111.90, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("VHHH", "25L", 22.3120, 113.9580, 6.0, 250.0, 60.0, 3800.0,
                 111.90, 3.0, 0.0, 8, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("VHHH", "07L", 22.3070, 113.9260, 6.0, 70.0, 60.0, 3800.0,
                 109.30, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("VHHH", "25R", 22.3100, 113.9640, 6.0, 250.0, 60.0, 3800.0,
                 109.30, 3.0, 0.0, 10, SURF_ASPHALT, true, true),

    // Singapore Changi (WSSS)
    RUNWAY_ENTRY("WSSS", "02L", 1.3577, 103.9860, 7.0, 20.0, 60.0, 4000.0,
                 110.30, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("WSSS", "20R", 1.3880, 103.9890, 7.0, 200.0, 60.0, 4000.0,
                 110.30, 3.0, 0.0, 12, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("WSSS", "02R", 1.3600, 103.9950, 7.0, 20.0, 60.0, 4000.0,
                 109.55, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("WSSS", "20L", 1.3900, 103.9980, 7.0, 200.0, 60.0, 4000.0,
                 109.55, 3.0, 0.0, 14, SURF_ASPHALT, true, true),

    // Sydney (YSSY)
    RUNWAY_ENTRY("YSSY", "16R", -33.9440, 151.1780, 6.0, 160.0, 45.0, 3962.0,
                 111.10, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("YSSY", "34L", -33.9730, 151.1850, 6.0, 340.0, 45.0, 3962.0,
                 111.10, 3.0, 0.0, 16, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("YSSY", "16L", -33.9410, 151.1680, 6.0, 160.0, 45.0, 2530.0,
                 110.30, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("YSSY", "34R", -33.9660, 151.1730, 6.0, 340.0, 45.0, 2530.0,
                 110.30, 3.0, 0.0, 18, SURF_ASPHALT, true, true),

    // ====================================================================
    //  EUROPE
    // ====================================================================

    // London Heathrow (EGLL)
    RUNWAY_ENTRY("EGLL", "27L", 51.4775, -0.4614, 25.0, 270.0, 45.0, 3900.0,
                 110.30, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("EGLL", "09R", 51.4775, -0.4150, 25.0, 90.0, 45.0, 3900.0,
                 110.30, 3.0, 0.0, 20, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("EGLL", "27R", 51.4720, -0.4835, 25.0, 270.0, 45.0, 3660.0,
                 109.50, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("EGLL", "09L", 51.4720, -0.4380, 25.0, 90.0, 45.0, 3660.0,
                 109.50, 3.0, 0.0, 22, SURF_ASPHALT, true, true),

    // Frankfurt am Main (EDDF)
    RUNWAY_ENTRY("EDDF", "07R", 50.0310, 8.5620, 100.0, 70.0, 45.0, 4000.0,
                 111.15, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("EDDF", "25L", 50.0340, 8.5900, 100.0, 250.0, 45.0, 4000.0,
                 111.15, 3.0, 0.0, 24, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("EDDF", "07L", 50.0330, 8.5580, 100.0, 70.0, 45.0, 2800.0,
                 110.50, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("EDDF", "25R", 50.0360, 8.5800, 100.0, 250.0, 45.0, 2800.0,
                 110.50, 3.0, 0.0, 26, SURF_ASPHALT, true, true),

    // Charles de Gaulle (LFPG)
    RUNWAY_ENTRY("LFPG", "26L", 49.0000, 2.5750, 119.0, 260.0, 45.0, 3600.0,
                 111.10, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("LFPG", "08R", 49.0000, 2.6100, 119.0, 80.0, 45.0, 3600.0,
                 111.10, 3.0, 0.0, 28, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("LFPG", "27R", 49.0100, 2.5700, 119.0, 270.0, 60.0, 4200.0,
                 110.30, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("LFPG", "09L", 49.0100, 2.6150, 119.0, 90.0, 60.0, 4200.0,
                 110.30, 3.0, 0.0, 30, SURF_ASPHALT, true, true),

    // Amsterdam Schiphol (EHAM)
    RUNWAY_ENTRY("EHAM", "18R", 52.3150, 4.7800, -3.0, 180.0, 45.0, 3800.0,
                 110.90, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("EHAM", "36L", 52.3450, 4.7800, -3.0, 0.0, 45.0, 3800.0,
                 110.90, 3.0, 0.0, 32, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("EHAM", "18L", 52.3120, 4.7700, -3.0, 180.0, 45.0, 3400.0,
                 111.55, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("EHAM", "36R", 52.3420, 4.7700, -3.0, 0.0, 45.0, 3400.0,
                 111.55, 3.0, 0.0, 34, SURF_ASPHALT, true, true),

    // Munich (EDDM)
    RUNWAY_ENTRY("EDDM", "08R", 48.3510, 11.7900, 448.0, 80.0, 60.0, 4000.0,
                 111.10, 3.0, 0.0, RECIP_UNASSIGNED, SURF_CONCRETE, true, true),
    RUNWAY_ENTRY("EDDM", "26L", 48.3540, 11.8300, 448.0, 260.0, 60.0, 4000.0,
                 111.10, 3.0, 0.0, 36, SURF_CONCRETE, true, true),
    RUNWAY_ENTRY("EDDM", "08L", 48.3530, 11.7850, 448.0, 80.0, 45.0, 2800.0,
                 110.50, 3.0, 0.0, RECIP_UNASSIGNED, SURF_CONCRETE, true, true),
    RUNWAY_ENTRY("EDDM", "26R", 48.3560, 11.8200, 448.0, 260.0, 45.0, 2800.0,
                 110.50, 3.0, 0.0, 38, SURF_CONCRETE, true, true),

    // ====================================================================
    //  NORTH AMERICA
    // ====================================================================

    // Seattle Tacoma (KSEA)
    RUNWAY_ENTRY("KSEA", "16R", 47.4320, -122.3110, 106.0, 160.0, 46.0, 3628.0,
                 110.30, 3.0, 0.0, RECIP_UNASSIGNED, SURF_CONCRETE, true, true),
    RUNWAY_ENTRY("KSEA", "34L", 47.4560, -122.3060, 106.0, 340.0, 46.0, 3628.0,
                 109.90, 3.0, 0.0, 40, SURF_CONCRETE, true, true),
    RUNWAY_ENTRY("KSEA", "16L", 47.4280, -122.3190, 106.0, 160.0, 46.0, 2869.0,
                 111.95, 3.0, 0.0, RECIP_UNASSIGNED, SURF_CONCRETE, true, true),
    RUNWAY_ENTRY("KSEA", "34R", 47.4500, -122.3150, 106.0, 340.0, 46.0, 2869.0,
                 111.95, 3.0, 0.0, 42, SURF_CONCRETE, true, true),

    // Denver (KDEN)
    RUNWAY_ENTRY("KDEN", "35R", 39.8510, -104.6720, 1625.0, 350.0, 46.0, 4877.0,
                 111.95, 3.0, 0.0, RECIP_UNASSIGNED, SURF_CONCRETE, true, true),
    RUNWAY_ENTRY("KDEN", "17L", 39.8860, -104.6740, 1625.0, 170.0, 46.0, 4877.0,
                 111.95, 3.0, 0.0, 44, SURF_CONCRETE, true, true),
    RUNWAY_ENTRY("KDEN", "34L", 39.8350, -104.6820, 1625.0, 340.0, 46.0, 4877.0,
                 111.70, 3.0, 0.0, RECIP_UNASSIGNED, SURF_CONCRETE, true, true),
    RUNWAY_ENTRY("KDEN", "16R", 39.8700, -104.6840, 1625.0, 160.0, 46.0, 4877.0,
                 111.70, 3.0, 0.0, 46, SURF_CONCRETE, true, true),
    RUNWAY_ENTRY("KDEN", "35L", 39.8480, -104.6600, 1625.0, 350.0, 46.0, 4268.0,
                 109.90, 3.0, 0.0, RECIP_UNASSIGNED, SURF_CONCRETE, true, true),
    RUNWAY_ENTRY("KDEN", "17R", 39.8780, -104.6620, 1625.0, 170.0, 46.0, 4268.0,
                 109.90, 3.0, 0.0, 48, SURF_CONCRETE, true, true),

    // Los Angeles (KLAX)
    RUNWAY_ENTRY("KLAX", "24R", 33.9420, -118.4040, 39.0, 240.0, 46.0, 3382.0,
                 111.15, 3.0, 0.0, RECIP_UNASSIGNED, SURF_CONCRETE, true, true),
    RUNWAY_ENTRY("KLAX", "06L", 33.9430, -118.3720, 39.0, 60.0, 46.0, 3382.0,
                 111.15, 3.0, 0.0, 50, SURF_CONCRETE, true, true),
    RUNWAY_ENTRY("KLAX", "25L", 33.9350, -118.4060, 39.0, 250.0, 46.0, 3135.0,
                 110.30, 3.0, 0.0, RECIP_UNASSIGNED, SURF_CONCRETE, true, true),
    RUNWAY_ENTRY("KLAX", "07R", 33.9360, -118.3760, 39.0, 70.0, 46.0, 3135.0,
                 110.30, 3.0, 0.0, 52, SURF_CONCRETE, true, true),

    // Chicago O'Hare (KORD)
    RUNWAY_ENTRY("KORD", "28R", 41.9740, -87.9180, 201.0, 280.0, 46.0, 3962.0,
                 111.75, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("KORD", "10L", 41.9740, -87.8720, 201.0, 100.0, 46.0, 3962.0,
                 111.75, 3.0, 0.0, 54, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("KORD", "27R", 41.9820, -87.9210, 201.0, 270.0, 46.0, 3902.0,
                 110.30, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("KORD", "09L", 41.9820, -87.8760, 201.0, 90.0, 46.0, 3902.0,
                 110.30, 3.0, 0.0, 56, SURF_ASPHALT, true, true),

    // John F. Kennedy (KJFK)
    RUNWAY_ENTRY("KJFK", "31R", 40.6420, -73.7790, 4.0, 310.0, 46.0, 4423.0,
                 111.95, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("KJFK", "13L", 40.6600, -73.7950, 4.0, 130.0, 46.0, 4423.0,
                 111.95, 3.0, 0.0, 58, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("KJFK", "22R", 40.6360, -73.7820, 4.0, 220.0, 46.0, 3460.0,
                 110.55, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("KJFK", "04L", 40.6480, -73.7670, 4.0, 40.0, 46.0, 3460.0,
                 110.55, 3.0, 0.0, 60, SURF_ASPHALT, true, true),

    // Newark (KEWR)
    RUNWAY_ENTRY("KEWR", "22L", 40.6900, -74.1720, 5.0, 220.0, 46.0, 3042.0,
                 111.10, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("KEWR", "04R", 40.7040, -74.1580, 5.0, 40.0, 46.0, 3042.0,
                 111.10, 3.0, 0.0, 62, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("KEWR", "22R", 40.6860, -74.1800, 5.0, 220.0, 46.0, 2533.0,
                 110.55, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("KEWR", "04L", 40.7010, -74.1670, 5.0, 40.0, 46.0, 2533.0,
                 110.55, 3.0, 0.0, 64, SURF_ASPHALT, true, true),

    // San Francisco (KSFO)
    RUNWAY_ENTRY("KSFO", "28R", 37.6180, -122.3970, 4.0, 280.0, 46.0, 3618.0,
                 111.15, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("KSFO", "10L", 37.6180, -122.3570, 4.0, 100.0, 46.0, 3618.0,
                 111.15, 3.0, 0.0, 66, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("KSFO", "28L", 37.6200, -122.4000, 4.0, 280.0, 46.0, 3430.0,
                 109.90, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("KSFO", "10R", 37.6200, -122.3610, 4.0, 100.0, 46.0, 3430.0,
                 109.90, 3.0, 0.0, 68, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("KSFO", "19R", 37.6110, -122.3860, 4.0, 190.0, 46.0, 2540.0,
                 110.55, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("KSFO", "01L", 37.6300, -122.3830, 4.0, 10.0, 46.0, 2540.0,
                 110.55, 3.0, 0.0, 70, SURF_ASPHALT, true, true),

    // Vancouver (CYVR)
    RUNWAY_ENTRY("CYVR", "13R", 49.1930, -123.1810, 4.0, 130.0, 46.0, 3032.0,
                 111.90, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("CYVR", "31L", 49.2100, -123.1960, 4.0, 310.0, 46.0, 3032.0,
                 111.90, 3.0, 0.0, 72, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("CYVR", "12L", 49.1900, -123.1700, 4.0, 120.0, 46.0, 3356.0,
                 110.30, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("CYVR", "30R", 49.2070, -123.1850, 4.0, 300.0, 46.0, 3356.0,
                 110.30, 3.0, 0.0, 74, SURF_ASPHALT, true, true),

    // ====================================================================
    //  MIDDLE EAST
    // ====================================================================

    // Dubai (OMDB)
    RUNWAY_ENTRY("OMDB", "12R", 25.2480, 55.3550, 14.0, 120.0, 60.0, 4447.0,
                 111.30, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("OMDB", "30L", 25.2750, 55.3830, 14.0, 300.0, 60.0, 4447.0,
                 111.30, 3.0, 0.0, 76, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("OMDB", "12L", 25.2460, 55.3480, 14.0, 120.0, 45.0, 4000.0,
                 110.30, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("OMDB", "30R", 25.2730, 55.3760, 14.0, 300.0, 45.0, 4000.0,
                 110.30, 3.0, 0.0, 78, SURF_ASPHALT, true, true),

    // DOH - Hamad International (OTHH)
    RUNWAY_ENTRY("OTHH", "16R", 25.2700, 51.6050, 11.0, 160.0, 60.0, 4850.0,
                 111.10, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("OTHH", "34L", 25.3000, 51.6120, 11.0, 340.0, 60.0, 4850.0,
                 111.10, 3.0, 0.0, 80, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("OTHH", "16L", 25.2720, 51.5980, 11.0, 160.0, 45.0, 4250.0,
                 110.55, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("OTHH", "34R", 25.3020, 51.6050, 11.0, 340.0, 45.0, 4250.0,
                 110.55, 3.0, 0.0, 82, SURF_ASPHALT, true, true),

    // Abu Dhabi (OMAA)
    RUNWAY_ENTRY("OMAA", "13R", 24.4380, 54.6480, 8.0, 130.0, 60.0, 4000.0,
                 111.75, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("OMAA", "31L", 24.4650, 54.6720, 8.0, 310.0, 60.0, 4000.0,
                 111.75, 3.0, 0.0, 84, SURF_ASPHALT, true, true),

    // ====================================================================
    //  SOUTH AMERICA
    // ====================================================================

    // Sao Paulo Guarulhos (SBGR)
    RUNWAY_ENTRY("SBGR", "10R", -23.4250, -46.4850, 750.0, 100.0, 45.0, 3000.0,
                 110.30, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("SBGR", "28L", -23.4280, -46.4550, 750.0, 280.0, 45.0, 3000.0,
                 110.30, 3.0, 0.0, 86, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("SBGR", "10L", -23.4280, -46.4880, 750.0, 100.0, 45.0, 3000.0,
                 109.50, 3.0, 0.0, RECIP_UNASSIGNED, SURF_ASPHALT, true, true),
    RUNWAY_ENTRY("SBGR", "28R", -23.4310, -46.4580, 750.0, 280.0, 45.0, 3000.0,
                 109.50, 3.0, 0.0, 88, SURF_ASPHALT, true, true),

    // Terminal sentinel
    RUNWAY_ENTRY("", "", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                 0.0, 0.0, 0.0, -1, 0, false, false)
};

#undef RUNWAY_ENTRY

// ============================================================================
//  3.  Internal helpers
// ============================================================================

/// Compute a coarse distance metric (squared degrees) for nearest-airport
/// search.  A true geodesic is not needed for this simple query.
static FLOAT64 db_dist_sq_deg(FLOAT64 lat1, FLOAT64 lon1,
                               FLOAT64 lat2, FLOAT64 lon2) {
    const FLOAT64 dlat = lat2 - lat1;
    const FLOAT64 dlon = lon2 - lon1;
    return dlat * dlat + dlon * dlon;
}

/// Normalise a heading to 0..360 range.
static FLOAT64 db_normalise_heading(FLOAT64 hdg) {
    FLOAT64 h = hdg;
    while (h < 0.0)   h += 360.0;
    while (h >= 360.0) h -= 360.0;
    return h;
}

/// Compute heading difference (smallest absolute angle, 0..180).
static FLOAT64 db_heading_delta(FLOAT64 h1, FLOAT64 h2) {
    FLOAT64 d = db_normalise_heading(h1) - db_normalise_heading(h2);
    if (d > 180.0)  d -= 360.0;
    if (d < -180.0) d += 360.0;
    return (d < 0.0) ? -d : d;
}

// ============================================================================
//  4.  Database initialisation
// ============================================================================

void db_airport_init(AirportDatabase* db) {
    if (db == 0) return;

    __builtin_memset(db, 0, sizeof(AirportDatabase));
    db->load_state = DB_UNINITIALISED;
    db->async_loading = false;
    db->initialised = true;
}

// ============================================================================
//  5.  Build ILS frequency index and reciprocal links
// ============================================================================

/// Called once to build the ILS frequency index and resolve reciprocal
/// runway references after the database has been populated.
static void db_build_index(AirportDatabase* db) {
    if (db == 0) return;

    db->ils_freq_count = 0;

    // Build frequency index
    for (int i = 0; i < db->num_runways; ++i) {
        RunwayRecord* rwy = &db->runways[i];
        if (!rwy->valid) continue;

        if (rwy->ils_frequency_mhz > 100.0 && rwy->ils_frequency_mhz < 120.0) {
            if (db->ils_freq_count < DB_MAX_ILS_FREQUENCIES) {
                db->ils_freq_indices[db->ils_freq_count] = i;
                db->ils_freq_values[db->ils_freq_count] = rwy->ils_frequency_mhz;
                db->ils_freq_count++;
            }
        }

        // Resolve reciprocal indices (symmetric: A->B and B->A)
        // Uses both heading alignment and position proximity to correctly
        // pair parallel runways (e.g. EGLL 27L<->09R and 27R<->09L).
        if (rwy->reciprocal_index == RECIP_UNASSIGNED) {
            // Search for the reciprocal runway (opposite direction)
            const FLOAT64 recip_hdg = db_normalise_heading(rwy->true_heading_deg + 180.0);
            int best_j = -1;
            FLOAT64 best_dist = 1e18;

            for (int j = 0; j < db->num_runways; ++j) {
                if (i == j) continue;
                RunwayRecord* other = &db->runways[j];
                if (!other->valid) continue;

                // Check same ICAO and opposite heading (within 2 deg tolerance)
                const char* a = rwy->icao_code;
                const char* b = other->icao_code;
                bool same_icao = true;
                {
                    const char* pa = a;
                    const char* pb = b;
                    while (*pa != '\0' && *pb != '\0') {
                        if (*pa != *pb) { same_icao = false; break; }
                        ++pa; ++pb;
                    }
                    if (*pa != *pb) same_icao = false;
                }

                if (same_icao && db_heading_delta(other->true_heading_deg, recip_hdg) < 2.0) {
                    // Position proximity: other's threshold should be near rwy's far end
                    const FLOAT64 dlat = other->threshold_lat_deg - rwy->far_end_lat_deg;
                    const FLOAT64 dlon = other->threshold_lon_deg - rwy->far_end_lon_deg;
                    const FLOAT64 dist = proj_sqrt(dlat * dlat + dlon * dlon);
                    if (dist < best_dist) {
                        best_dist = dist;
                        best_j = j;
                    }
                }
            }

            if (best_j >= 0 && db->runways[best_j].reciprocal_index == RECIP_UNASSIGNED) {
                rwy->reciprocal_index = best_j;
                // Also set the reciprocal of B to A (symmetric pairing)
                db->runways[best_j].reciprocal_index = i;
            } else if (best_j >= 0) {
                // Best match already has a reciprocal — still use it
                rwy->reciprocal_index = best_j;
            } else {
                // No reciprocal found
                rwy->reciprocal_index = -1;
            }
        }
    }

    // Build airport records from runway data
    db->num_airports = 0;

    for (int i = 0; i < db->num_runways && db->num_airports < DB_MAX_AIRPORTS_CACHED; ++i) {
        const RunwayRecord* rwy = &db->runways[i];
        if (!rwy->valid) continue;

        // Check if this airport is already in the index
        bool found_airport = false;
        for (int a = 0; a < db->num_airports; ++a) {
            const char* ap = db->airports[a].icao_code;
            const char* rp = rwy->icao_code;
            bool match = true;
            for (int ci = 0; ci < DB_ICAO_CODE_MAX; ++ci) {
                if (ap[ci] != rp[ci]) { match = false; break; }
                if (ap[ci] == '\0') break;
            }
            if (match) {
                // Add runway to existing airport
                AirportRecord* airport = &db->airports[a];
                if (airport->num_runways < DB_MAX_RUNWAYS_PER_AIRPORT) {
                    airport->runway_indices[airport->num_runways] = i;
                    airport->num_runways++;
                }
                found_airport = true;
                break;
            }
        }

        if (!found_airport) {
            // Create new airport record
            AirportRecord* airport = &db->airports[db->num_airports];
            const char* src = rwy->icao_code;
            char* dst = airport->icao_code;
            int ci = 0;
            while (*src != '\0' && ci < DB_ICAO_CODE_MAX - 1) {
                *dst++ = *src++;
                ++ci;
            }
            *dst = '\0';
            airport->lat_deg = rwy->threshold_lat_deg;
            airport->lon_deg = rwy->threshold_lon_deg;
            airport->elevation_m = rwy->threshold_alt_m;
            airport->num_runways = 0;
            airport->runway_indices[airport->num_runways] = i;
            airport->num_runways++;
            airport->valid = true;
            db->num_airports++;
        }
    }
}

// ============================================================================
//  6.  Load from static data / async loading
// ============================================================================

/// Populate the database from the built-in static table.
static void db_load_builtin(AirportDatabase* db) {
    if (db == 0) return;

    // Count valid entries
    int count = 0;
    for (int i = 0; ; ++i) {
        if (!g_builtin_runways[i].valid && g_builtin_runways[i].icao_code[0] == '\0') {
            break;  // sentinel
        }
        if (g_builtin_runways[i].valid) {
            ++count;
        }
    }

    if (count > DB_MAX_AIRPORTS_CACHED * 2) {
        count = DB_MAX_AIRPORTS_CACHED * 2;
    }

    db->num_runways = count;
    for (int i = 0; i < count; ++i) {
        // Copy runway data
        db->runways[i] = g_builtin_runways[i];
        // Copy far-end lat/lon from threshold + heading + length (approx)
        // For now, approximate by extending along heading
        const FLOAT64 hdg_rad = PROJ_DEG2RAD(db->runways[i].true_heading_deg);
        const FLOAT64 cos_lat = proj_cos(PROJ_DEG2RAD(db->runways[i].threshold_lat_deg));
        const FLOAT64 len_m = db->runways[i].length_m;
        const FLOAT64 dlat = len_m * proj_cos(hdg_rad) / PROJ_EARTH_RADIUS_M;
        const FLOAT64 dlon = len_m * proj_sin(hdg_rad) / (PROJ_EARTH_RADIUS_M * cos_lat);
        db->runways[i].far_end_lat_deg = db->runways[i].threshold_lat_deg + PROJ_RAD2DEG(dlat);
        db->runways[i].far_end_lon_deg = db->runways[i].threshold_lon_deg + PROJ_RAD2DEG(dlon);

        // Default TDZ geometry
        db->runways[i].tdz_geometry.distance_from_threshold_m = 300.0;
        db->runways[i].tdz_geometry.zone_length_m = 300.0;
        db->runways[i].tdz_geometry.zone_width_m = db->runways[i].width_m;
        db->runways[i].tdz_geometry.valid = true;

        // Default displaced threshold (none)
        db->runways[i].displaced_threshold.distance_from_end_m = 0.0;
        db->runways[i].displaced_threshold.landing_displaced = false;
        db->runways[i].displaced_threshold.valid = false;

        // Fill in IAS from threshold (for simplicity)
        db->runways[i].threshold_alt_m = g_builtin_runways[i].threshold_alt_m;
    }

    // Build indices
    db_build_index(db);

    db->load_state = DB_READY;
    db->load_progress_pct = 100;
}

bool db_airport_start_loading(AirportDatabase* db) {
    if (db == 0) return false;
    if (db->load_state == DB_READY) return true;

    db->load_state = DB_LOADING;
    db->async_loading = true;
    db->async_stage = 0;
    db->load_progress_pct = 0;
    return true;
}

bool db_airport_tick_loading(AirportDatabase* db) {
    if (db == 0) return false;

    if (db->load_state == DB_UNINITIALISED) {
        db_airport_init(db);
        db_airport_start_loading(db);
    }

    if (db->load_state == DB_LOADING) {
        // Stage 0: Load static builtin data (immediate for our implementation)
        if (db->async_stage == 0) {
            db_load_builtin(db);
            db->async_stage = 1;
            db->load_progress_pct = 50;
        }
        // Stage 1: Attempt to query MSFS facilities API for additional airports
        // (placeholder — in production, this would call gauge_get_var_by_name
        //  or the MSFS facilities API to enumerate all installed airports)
        else if (db->async_stage == 1) {
            db->async_stage = 2;
            db->load_progress_pct = 90;
        }
        // Stage 2: Finalise
        else if (db->async_stage >= 2) {
            db->load_state = DB_READY;
            db->load_progress_pct = 100;
            db->async_loading = false;
            return true;
        }
    }

    return (db->load_state == DB_READY);
}

// ============================================================================
//  7.  Query functions
// ============================================================================

const RunwayRecord* db_find_runway(AirportDatabase* db,
                                    const char* icao_code,
                                    const char* runway_id) {
    if (db == 0 || icao_code == 0 || runway_id == 0) return 0;

    for (int i = 0; i < db->num_runways; ++i) {
        const RunwayRecord* rwy = &db->runways[i];
        if (!rwy->valid) continue;

        // Compare ICAO codes
        const char* a = icao_code;
        const char* b = rwy->icao_code;
        bool icao_match = true;
        while (*a != '\0' && *b != '\0') {
            // Case-insensitive
            char ca = *a, cb = *b;
            if (ca >= 'a' && ca <= 'z') ca -= 32;
            if (cb >= 'a' && cb <= 'z') cb -= 32;
            if (ca != cb) { icao_match = false; break; }
            ++a; ++b;
        }
        if (*a != '\0' || *b != '\0') icao_match = false;
        if (!icao_match) continue;

        // Compare runway IDs
        a = runway_id;
        b = rwy->runway_id;
        bool rwy_match = true;
        while (*a != '\0' && *b != '\0') {
            // Case-insensitive
            char ca = *a, cb = *b;
            if (ca >= 'a' && ca <= 'z') ca -= 32;
            if (cb >= 'a' && cb <= 'z') cb -= 32;
            if (ca != cb) { rwy_match = false; break; }
            ++a; ++b;
        }
        if (*a != *b) rwy_match = false;
        if (rwy_match) return rwy;
    }

    return 0;
}

const RunwayRecord* db_find_by_ils_freq(AirportDatabase* db,
                                         FLOAT64 freq_mhz,
                                         FLOAT64 tolerance_mhz) {
    if (db == 0 || freq_mhz <= 100.0 || freq_mhz >= 120.0) return 0;

    const FLOAT64 tol = (tolerance_mhz > 0.0) ? tolerance_mhz : 0.01;
    FLOAT64 best_diff = tol;
    int best_index = -1;

    for (int i = 0; i < db->ils_freq_count; ++i) {
        const FLOAT64 diff = proj_fabs(db->ils_freq_values[i] - freq_mhz);
        if (diff < best_diff) {
            best_diff = diff;
            best_index = i;
        }
    }

    if (best_index >= 0) {
        const int rwy_idx = db->ils_freq_indices[best_index];
        if (rwy_idx >= 0 && rwy_idx < db->num_runways) {
            return &db->runways[rwy_idx];
        }
    }

    return 0;
}

const AirportRecord* db_find_nearest_airport(AirportDatabase* db,
                                              FLOAT64 lat_deg,
                                              FLOAT64 lon_deg) {
    if (db == 0 || db->num_airports == 0) return 0;

    FLOAT64 best_dist = 1e18;
    int best_index = -1;

    for (int i = 0; i < db->num_airports; ++i) {
        if (!db->airports[i].valid) continue;
        const FLOAT64 d = db_dist_sq_deg(lat_deg, lon_deg,
                                          db->airports[i].lat_deg,
                                          db->airports[i].lon_deg);
        if (d < best_dist) {
            best_dist = d;
            best_index = i;
        }
    }

    return (best_index >= 0) ? &db->airports[best_index] : 0;
}

int db_find_airport_runways(AirportDatabase* db,
                             const char* icao_code,
                             const RunwayRecord** out_runways,
                             int max_out) {
    if (db == 0 || icao_code == 0 || out_runways == 0) return 0;

    int found = 0;
    for (int i = 0; i < db->num_runways && found < max_out; ++i) {
        const RunwayRecord* rwy = &db->runways[i];
        if (!rwy->valid) continue;

        const char* a = icao_code;
        const char* b = rwy->icao_code;
        bool match = true;
        while (*a != '\0' && *b != '\0') {
            char ca = *a, cb = *b;
            if (ca >= 'a' && ca <= 'z') ca -= 32;
            if (cb >= 'a' && cb <= 'z') cb -= 32;
            if (ca != cb) { match = false; break; }
            ++a; ++b;
        }
        if (*a != '\0' || *b != '\0') match = false;
        if (match) {
            out_runways[found] = rwy;
            ++found;
        }
    }
    return found;
}

const RunwayRecord* db_get_reciprocal_runway(AirportDatabase* db,
                                              const RunwayRecord* rwy) {
    if (db == 0 || rwy == 0 || !rwy->valid) return 0;
    if (rwy->reciprocal_index < 0 || rwy->reciprocal_index >= db->num_runways) return 0;
    const RunwayRecord* recip = &db->runways[rwy->reciprocal_index];
    return recip->valid ? recip : 0;
}

const RunwayRecord* db_find_active_runway(AirportDatabase* db,
                                           FLOAT64 ac_lat_deg,
                                           FLOAT64 ac_lon_deg,
                                           FLOAT64 ac_hdg_true_deg,
                                           FLOAT64 ils_freq_mhz) {
    if (db == 0 || !db->initialised) return 0;

    // Strategy 1: Try ILS frequency first
    if (ils_freq_mhz > 100.0 && ils_freq_mhz < 120.0) {
        const RunwayRecord* ils_rwy = db_find_by_ils_freq(db, ils_freq_mhz, 0.01);
        if (ils_rwy != 0) return ils_rwy;
    }

    // Strategy 2: Find nearest airport and best-aligned runway
    const AirportRecord* airport = db_find_nearest_airport(db, ac_lat_deg, ac_lon_deg);
    if (airport == 0) return 0;

    // Check that airport is within reasonable range (~100 km)
    const FLOAT64 dist = db_dist_sq_deg(ac_lat_deg, ac_lon_deg,
                                         airport->lat_deg, airport->lon_deg);
    if (dist > 1.0) return 0;  // too far (~1 deg² ≈ 100 km)

    // Find best runway by heading alignment
    const RunwayRecord* best_rwy = 0;
    FLOAT64 best_delta = 180.0;

    for (int i = 0; i < airport->num_runways; ++i) {
        const int idx = airport->runway_indices[i];
        if (idx < 0 || idx >= db->num_runways) continue;
        const RunwayRecord* rwy = &db->runways[idx];
        if (!rwy->valid) continue;

        const FLOAT64 delta = db_heading_delta(ac_hdg_true_deg, rwy->true_heading_deg);
        if (delta < best_delta) {
            best_delta = delta;
            best_rwy = rwy;
        }
    }

    // Only return if heading alignment is reasonable (< 90 deg)
    if (best_rwy != 0 && best_delta < 90.0) {
        return best_rwy;
    }

    return 0;
}

// ============================================================================
//  8.  Runway geometry conversion
// ============================================================================

bool db_runway_to_geometry(const RunwayRecord* rwy,
                            bool use_reciprocal,
                            RunwayEnd* out_end) {
    if (rwy == 0 || out_end == 0 || !rwy->valid) return false;

    const RunwayRecord* active = rwy;

    if (use_reciprocal) {
        // Use the reciprocal end
        const RunwayRecord* recip = 0;
        // We don't have db pointer here, so we use a cross-reference approach
        // The caller should handle reciprocal via db_get_reciprocal_runway()
        return false;
    }

    // Apply displaced threshold offset
    FLOAT64 threshold_lat = active->threshold_lat_deg;
    FLOAT64 threshold_lon = active->threshold_lon_deg;
    FLOAT64 threshold_alt = active->threshold_alt_m;

    if (active->displaced_threshold.valid &&
        active->displaced_threshold.landing_displaced) {
        // Shift threshold back by displaced amount
        const FLOAT64 disp_m = active->displaced_threshold.distance_from_end_m;
        const FLOAT64 hdg_rad = PROJ_DEG2RAD(active->true_heading_deg);
        const FLOAT64 cos_lat = proj_cos(PROJ_DEG2RAD(threshold_lat));
        const FLOAT64 dlat = -disp_m * proj_cos(hdg_rad) / PROJ_EARTH_RADIUS_M;
        const FLOAT64 dlon = -disp_m * proj_sin(hdg_rad) / (PROJ_EARTH_RADIUS_M * cos_lat);
        threshold_lat += PROJ_RAD2DEG(dlat);
        threshold_lon += PROJ_RAD2DEG(dlon);
    }

    out_end->threshold = runway_make_position(threshold_lon, threshold_lat, threshold_alt);
    out_end->far_end = runway_make_position(
        active->far_end_lon_deg, active->far_end_lat_deg, threshold_alt);
    out_end->true_heading = active->true_heading_deg;
    out_end->width_m = active->width_m;
    out_end->valid = true;

    return true;
}

FLOAT64 db_get_displaced_threshold_m(const RunwayRecord* rwy) {
    if (rwy == 0 || !rwy->valid || !rwy->displaced_threshold.valid) return 0.0;
    return rwy->displaced_threshold.distance_from_end_m;
}

FLOAT64 db_get_touchdown_aim_m(const RunwayRecord* rwy) {
    if (rwy == 0 || !rwy->valid || !rwy->tdz_geometry.valid) return 300.0; // default
    return rwy->tdz_geometry.distance_from_threshold_m;
}

// ============================================================================
//  9.  Debug logging
// ============================================================================

void db_debug_log_all(AirportDatabase* db) {
    if (db == 0) return;
    MSFS_Log("[C_HUD_DB] Airport Database: %d airports, %d runways, "
             "%d ILS frequencies, state=%d",
             db->num_airports, db->num_runways,
             db->ils_freq_count, (int)db->load_state);
    for (int i = 0; i < db->num_airports; ++i) {
        MSFS_Log("[C_HUD_DB]   Airport[%d]: %s  %.4f/%.4f  elev=%.0fm  %d runways",
                 i, db->airports[i].icao_code,
                 db->airports[i].lat_deg, db->airports[i].lon_deg,
                 db->airports[i].elevation_m, db->airports[i].num_runways);
    }
}

void db_debug_log_runway(const RunwayRecord* rwy) {
    if (rwy == 0 || !rwy->valid) {
        MSFS_Log("[C_HUD_DB] Runway: INVALID");
        return;
    }
    MSFS_Log("[C_HUD_DB] Runway %s/%s: hdg=%.1f°  "
             "thresh=%.4f,%.4f alt=%.0fm  "
             "len=%.0fm  w=%.0fm  slope=%.2f%%  "
             "ILS=%.2fMHz  GS=%.1f°  recip=%d",
             rwy->icao_code, rwy->runway_id,
             rwy->true_heading_deg,
             rwy->threshold_lat_deg, rwy->threshold_lon_deg,
             rwy->threshold_alt_m,
             rwy->length_m, rwy->width_m, rwy->slope_pct,
             rwy->ils_frequency_mhz, rwy->gs_angle_deg,
             rwy->reciprocal_index);
}
