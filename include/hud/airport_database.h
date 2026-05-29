#ifndef C_HUD_AIRPORT_DATABASE_H
#define C_HUD_AIRPORT_DATABASE_H

// ============================================================================
//  Conformal HUD – Global Airport / Runway Database System
//  MSFS 2024  ·  C++17  ·  WASM
//
//  Provides a comprehensive runway database derived from MSFS BGL data.
//  Replaces the legacy hardcoded ILS frequency lookup with a global,
//  cache-friendly system supporting all installed airports.
//
//  Key features:
//    · Parses MSFS airport/runway data via SimVar API
//    · Supports all installed airports
//    · Geometry caching with spatial indexing
//    · Active runway detection via ILS frequency or nearest approach
//    · Displaced threshold handling
//    · Runway elevation / slope computation
//    · Touchdown zone geometry
//    · Reciprocal runway (opposite-end) mapping
//    · Async-loading friendly design
// ============================================================================

#include "../module.h"

// ============================================================================
//  1.  Database limits
// ============================================================================

#define DB_MAX_RUNWAYS_PER_AIRPORT      64
#define DB_MAX_AIRPORTS_CACHED          512
#define DB_MAX_ILS_FREQUENCIES          256
#define DB_RUNWAY_NAME_MAX              8
#define DB_ICAO_CODE_MAX                8

// ============================================================================
//  2.  Runway data structures
// ============================================================================

/// Displaced threshold definition (metres from physical runway end).
typedef struct DisplacedThreshold {
    FLOAT64  distance_from_end_m;  // distance from runway end (m)
    bool     landing_displaced;    // displaced for landing (vs. takeoff)
    bool     valid;
} DisplacedThreshold;

/// Touchdown zone geometry.
typedef struct TouchdownZoneGeometry {
    FLOAT64  distance_from_threshold_m;   // centre of TDZ (m)
    FLOAT64  zone_length_m;               // TDZ length (typically 300 m)
    FLOAT64  zone_width_m;                // TDZ width (typically runway width)
    bool     valid;
} TouchdownZoneGeometry;

/// Complete description of a single runway end.
typedef struct RunwayRecord {
    char     icao_code[DB_ICAO_CODE_MAX];     // e.g. "RKSI"
    char     runway_id[DB_RUNWAY_NAME_MAX];   // e.g. "15R"

    // --- Position ---
    FLOAT64  threshold_lat_deg;     // threshold latitude (degrees)
    FLOAT64  threshold_lon_deg;     // threshold longitude (degrees)
    FLOAT64  threshold_alt_m;       // threshold altitude (metres MSL)
    FLOAT64  far_end_lat_deg;       // opposite end latitude (degrees)
    FLOAT64  far_end_lon_deg;       // opposite end longitude (degrees)

    // --- Geometry ---
    FLOAT64  true_heading_deg;      // runway true heading (degrees)
    FLOAT64  width_m;               // runway width (metres)
    FLOAT64  length_m;              // runway length (metres surface length)
    FLOAT64  slope_pct;             // runway slope percentage (+ = uphill)

    // --- ILS ---
    FLOAT64  ils_frequency_mhz;     // ILS localizer frequency (MHz), 0 if none
    FLOAT64  gs_angle_deg;          // glideslope angle (degrees), 3.0 typical

    // --- Threshold / Landing ---
    DisplacedThreshold    displaced_threshold;
    TouchdownZoneGeometry tdz_geometry;

    // --- Reciprocal ---
    int      reciprocal_index;      // index of opposite runway in database (-1 = none)

    // --- Surface ---
    int      surface_type;          // 0=asphalt, 1=concrete, 2=grass, etc.
    bool     has_approach_lights;   // approach lighting system present
    bool     has_papi;              // PAPI/VASI available

    bool     valid;                 // true if this record is populated
} RunwayRecord;

// ============================================================================
//  3.  Airport record
// ============================================================================

typedef struct AirportRecord {
    char     icao_code[DB_ICAO_CODE_MAX];   // e.g. "RKSI"
    FLOAT64  lat_deg;                        // reference latitude
    FLOAT64  lon_deg;                        // reference longitude
    FLOAT64  elevation_m;                    // airport elevation (MSL)
    int      num_runways;                    // number of runways
    int      runway_indices[DB_MAX_RUNWAYS_PER_AIRPORT]; // indices into global runway array
    bool     valid;
} AirportRecord;

// ============================================================================
//  4.  Database state
// ============================================================================

/// Enum for database loading state.
typedef enum DBLoadState {
    DB_UNINITIALISED = 0,
    DB_LOADING       = 1,
    DB_READY         = 2,
    DB_ERROR         = 3
} DBLoadState;

/// Complete airport database state.
typedef struct AirportDatabase {
    // --- Airport storage ---
    AirportRecord  airports[DB_MAX_AIRPORTS_CACHED];
    int            num_airports;

    // --- Runway storage ---
    RunwayRecord   runways[DB_MAX_AIRPORTS_CACHED * 2]; // avg 2 runways/airport
    int            num_runways;

    // --- ILS frequency index (fast lookup) ---
    int            ils_freq_indices[DB_MAX_ILS_FREQUENCIES];
    FLOAT64        ils_freq_values[DB_MAX_ILS_FREQUENCIES];
    int            ils_freq_count;

    // --- Loading ---
    DBLoadState    load_state;
    int            load_progress_pct;
    bool           async_loading;
    int            async_stage;           // for multi-frame loading

    // --- Active runway prefetching ---
    int            prefetch_target_airport;  // index of prefetched airport
    bool           prefetch_active;

    bool           initialised;
} AirportDatabase;

// ============================================================================
//  5.  Database initialisation
// ============================================================================

/// Initialise the airport database (clears all state).
void db_airport_init(AirportDatabase* db);

/// Start async loading of the runway database.
/// In a real MSFS context, this would query SimVar airport facilities.
/// Returns true if loading was started.
bool db_airport_start_loading(AirportDatabase* db);

/// Perform one tick of async loading (call each frame during loading).
/// Returns true when loading is complete.
bool db_airport_tick_loading(AirportDatabase* db);

// ============================================================================
//  6.  Runway queries
// ============================================================================

/// Find a runway by ICAO code and runway ID (e.g. "RKSI", "15R").
/// Returns the runway record pointer, or NULL if not found.
const RunwayRecord* db_find_runway(AirportDatabase* db,
                                    const char* icao_code,
                                    const char* runway_id);

/// Find a runway by ILS frequency (best match within tolerance).
/// Returns the runway record pointer, or NULL if not found.
const RunwayRecord* db_find_by_ils_freq(AirportDatabase* db,
                                         FLOAT64 freq_mhz,
                                         FLOAT64 tolerance_mhz);

/// Find the closest airport to a given lat/lon coordinate.
/// Returns the airport record pointer, or NULL if none found.
const AirportRecord* db_find_nearest_airport(AirportDatabase* db,
                                              FLOAT64 lat_deg,
                                              FLOAT64 lon_deg);

/// Find all runways at a given airport.
/// Returns the number of runways found, or 0 if airport not found.
int db_find_airport_runways(AirportDatabase* db,
                             const char* icao_code,
                             const RunwayRecord** out_runways,
                             int max_out);

/// Get the reciprocal (opposite-end) runway for a given runway.
/// Returns the reciprocal runway record, or NULL if not found.
const RunwayRecord* db_get_reciprocal_runway(AirportDatabase* db,
                                              const RunwayRecord* rwy);

/// Find the best active runway for a given aircraft state.
/// Uses ILS frequency first, then heading alignment, then nearest airport.
/// Returns the runway record pointer, or NULL if no suitable runway found.
const RunwayRecord* db_find_active_runway(AirportDatabase* db,
                                           FLOAT64 ac_lat_deg,
                                           FLOAT64 ac_lon_deg,
                                           FLOAT64 ac_hdg_true_deg,
                                           FLOAT64 ils_freq_mhz);

// ============================================================================
//  7.  Runway geometry helpers
// ============================================================================

/// Compute the full geometry of a runway (corners, centerline, etc.)
/// and populate a RunwayEnd structure for the projection pipeline.
///
/// @param rwy          Source runway record
/// @param use_reciprocal  If true, swap threshold/far_end for opposite direction
/// @param out_end      [out] Populated RunwayEnd for projection
/// @return             true if geometry was computed
bool db_runway_to_geometry(const RunwayRecord* rwy,
                            bool use_reciprocal,
                            RunwayEnd* out_end);

/// Get displaced threshold offset for a runway.
/// Returns the usable threshold offset in metres (0 if no displacement).
FLOAT64 db_get_displaced_threshold_m(const RunwayRecord* rwy);

/// Get the touchdown zone aim point (distance from threshold in metres).
FLOAT64 db_get_touchdown_aim_m(const RunwayRecord* rwy);

// ============================================================================
//  8.  Debug / diagnostics
// ============================================================================

/// Log the full airport database contents.
void db_debug_log_all(AirportDatabase* db);

/// Log details for a specific runway.
void db_debug_log_runway(const RunwayRecord* rwy);

#endif // C_HUD_AIRPORT_DATABASE_H
