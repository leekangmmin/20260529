#ifndef C_HUD_RUNWAY_CACHE_H
#define C_HUD_RUNWAY_CACHE_H

// ============================================================================
//  Conformal HUD – Runway Geometry Cache
//  MSFS 2024  ·  C++17  ·  WASM
//
//  Provides spatial caching of runway geometry for fast per-frame access.
//  Key features:
//    · Bounding-box spatial index for nearest-runway queries
//    · Geometry caching (projected corner coordinates, etc.)
//    · LRU eviction for memory management
//    · Dirty-flag invalidation when aircraft moves significantly
//    · Prefetch support for active approach runways
// ============================================================================

#include "../module.h"
#include "airport_database.h"
#include "runway_projection.h"

// ============================================================================
//  1.  Cache limits
// ============================================================================

#define RC_MAX_CACHED_RUNWAYS      32
#define RC_CACHE_TILE_SIZE_DEG     1.0    // 1° spatial tile
#define RC_MAX_TILES               64

// ============================================================================
//  2.  Runway cache entry
// ============================================================================

/// A single cached runway with precomputed projection data.
typedef struct RunwayCacheEntry {
    // --- Key ---
    char           icao_code[DB_ICAO_CODE_MAX];
    char           runway_id[DB_RUNWAY_NAME_MAX];
    int            runway_db_index;     // index into global runway DB (-1 = none)

    // --- Precomputed geometry (world frame) ---
    RunwayEnd      end;
    RunwayCorners  corners;

    // --- Cached projection results ---
    Vec2           screen_corners[8];   // last projected positions
    bool           behind[8];
    int            visible_count;
    bool           projection_valid;

    // --- Cache metadata ---
    int            frame_last_used;     // frame counter of last access
    bool           dirty;               // needs reprojection
    bool           valid;               // entry populated

    // --- Prefetch ---
    bool           prefetched;          // true if loaded via prefetch
} RunwayCacheEntry;

// ============================================================================
//  3.  Spatial tile for geographic indexing
// ============================================================================

/// A tile in the spatial grid for fast nearest-runway search.
typedef struct SpatialTile {
    int   tile_x;               // tile X coordinate
    int   tile_y;               // tile Y coordinate
    int   runway_indices[RC_MAX_CACHED_RUNWAYS];  // runway cache indices in this tile
    int   num_runways;          // number of runways in this tile
    bool  valid;
} SpatialTile;

// ============================================================================
//  4.  Cache state
// ============================================================================

typedef struct RunwayCache {
    // --- Cache entries ---
    RunwayCacheEntry entries[RC_MAX_CACHED_RUNWAYS];
    int               num_entries;

    // --- Spatial index ---
    SpatialTile       tiles[RC_MAX_TILES];
    int               num_tiles;

    // --- Global frame counter ---
    int               frame_counter;

    // --- Active runway prefetching ---
    int               prefetch_target_idx;  // which cache entry is prefetched
    bool              prefetch_active;
    FLOAT64           prefetch_lat;
    FLOAT64           prefetch_lon;

    // --- Statistics ---
    int               stat_hits;
    int               stat_misses;
    int               stat_evictions;

    bool              initialised;
} RunwayCache;

// ============================================================================
//  5.  Cache initialisation
// ============================================================================

/// Initialise the runway cache.
void rc_init(RunwayCache* cache);

// ============================================================================
//  6.  Cache operations
// ============================================================================

/// Look up a runway in the cache by its database index.
/// Returns the cache entry, or NULL if not found.
const RunwayCacheEntry* rc_lookup(RunwayCache* cache, int db_index);

/// Insert or update a runway in the cache.
/// Returns the cache entry index, or -1 if cache is full.
int rc_insert(RunwayCache* cache,
              const RunwayRecord* rwy,
              int db_index,
              int current_frame);

/// Evict the least-recently-used cache entry.
void rc_evict_lru(RunwayCache* cache);

/// Mark all cache entries as dirty (e.g., after significant aircraft movement).
void rc_invalidate_all(RunwayCache* cache);

// ============================================================================
//  7.  Spatial tile operations
// ============================================================================

/// Convert lat/lon to tile coordinates.
static inline void rc_latlon_to_tile(FLOAT64 lat_deg, FLOAT64 lon_deg,
                                      int* out_tile_x, int* out_tile_y) {
    if (out_tile_x) *out_tile_x = (int)proj_floor(lon_deg / RC_CACHE_TILE_SIZE_DEG);
    if (out_tile_y) *out_tile_y = (int)proj_floor(lat_deg / RC_CACHE_TILE_SIZE_DEG);
}

/// Find or create a spatial tile for the given coordinates.
/// Returns the tile index, or -1 if limit reached.
int rc_get_or_create_tile(RunwayCache* cache, int tile_x, int tile_y);

/// Find runways near a given position (within a tile radius).
void rc_find_nearby(RunwayCache* cache,
                     FLOAT64 lat_deg,
                     FLOAT64 lon_deg,
                     int* out_indices,
                     int* out_count,
                     int max_out);

// ============================================================================
//  8.  Prefetch support
// ============================================================================

/// Set the prefetch target based on aircraft position.
void rc_set_prefetch_target(RunwayCache* cache,
                             FLOAT64 ac_lat_deg,
                             FLOAT64 ac_lon_deg);

/// Execute one tick of prefetch loading.
void rc_tick_prefetch(RunwayCache* cache,
                       const AirportDatabase* db,
                       int current_frame);

// ============================================================================
//  9.  Statistics / debug
// ============================================================================

/// Log cache statistics.
void rc_debug_log(const RunwayCache* cache);

#endif // C_HUD_RUNWAY_CACHE_H
