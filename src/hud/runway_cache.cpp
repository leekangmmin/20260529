// ============================================================================
//  Conformal HUD – Runway Geometry Cache Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  Implements the spatial runway geometry cache.
// ============================================================================

#include "../../include/hud/runway_cache.h"

// ============================================================================
//  1.  Cache initialisation
// ============================================================================

void rc_init(RunwayCache* cache) {
    if (cache == 0) return;
    __builtin_memset(cache, 0, sizeof(RunwayCache));
    cache->num_entries = 0;
    cache->num_tiles = 0;
    cache->frame_counter = 0;
    cache->prefetch_target_idx = -1;
    cache->prefetch_active = false;
    cache->stat_hits = 0;
    cache->stat_misses = 0;
    cache->stat_evictions = 0;
    cache->initialised = true;
}

// ============================================================================
//  2.  Cache lookup
// ============================================================================

const RunwayCacheEntry* rc_lookup(RunwayCache* cache, int db_index) {
    if (cache == 0 || db_index < 0) return 0;

    for (int i = 0; i < cache->num_entries; ++i) {
        if (cache->entries[i].runway_db_index == db_index && cache->entries[i].valid) {
            cache->entries[i].frame_last_used = cache->frame_counter;
            cache->stat_hits++;
            return &cache->entries[i];
        }
    }

    cache->stat_misses++;
    return 0;
}

// ============================================================================
//  3.  Cache insert/update
// ============================================================================

int rc_insert(RunwayCache* cache,
              const RunwayRecord* rwy,
              int db_index,
              int current_frame) {
    if (cache == 0 || rwy == 0 || db_index < 0) return -1;

    // First check if already present
    for (int i = 0; i < cache->num_entries; ++i) {
        if (cache->entries[i].runway_db_index == db_index && cache->entries[i].valid) {
            // Update existing entry
            cache->entries[i].frame_last_used = current_frame;
            cache->entries[i].dirty = true;
            return i;
        }
    }

    // Find a free slot
    int slot = -1;

    // Try unused slots first
    for (int i = 0; i < RC_MAX_CACHED_RUNWAYS; ++i) {
        if (!cache->entries[i].valid) {
            slot = i;
            break;
        }
    }

    // If no free slot, evict LRU
    if (slot < 0) {
        int oldest_frame = cache->entries[0].frame_last_used;
        slot = 0;
        for (int i = 1; i < RC_MAX_CACHED_RUNWAYS; ++i) {
            if (cache->entries[i].frame_last_used < oldest_frame &&
                !cache->entries[i].prefetched) {
                oldest_frame = cache->entries[i].frame_last_used;
                slot = i;
            }
        }
        // Try including prefetched if all entries are prefetched
        if (slot >= 0 && cache->entries[slot].prefetched) {
            for (int i = 0; i < RC_MAX_CACHED_RUNWAYS; ++i) {
                if (cache->entries[i].frame_last_used < oldest_frame) {
                    oldest_frame = cache->entries[i].frame_last_used;
                    slot = i;
                }
            }
        }
        cache->stat_evictions++;
    }

    // Fill the slot
    __builtin_memset(&cache->entries[slot], 0, sizeof(RunwayCacheEntry));
    cache->entries[slot].runway_db_index = db_index;
    cache->entries[slot].frame_last_used = current_frame;
    cache->entries[slot].dirty = true;
    cache->entries[slot].valid = true;

    // Copy ICAO/runway IDs
    {
        const char* src = rwy->icao_code;
        char* dst = cache->entries[slot].icao_code;
        int ci = 0;
        while (*src != '\0' && ci < DB_ICAO_CODE_MAX - 1) {
            *dst++ = *src++;
            ++ci;
        }
        *dst = '\0';
    }
    {
        const char* src = rwy->runway_id;
        char* dst = cache->entries[slot].runway_id;
        int ci = 0;
        while (*src != '\0' && ci < DB_RUNWAY_NAME_MAX - 1) {
            *dst++ = *src++;
            ++ci;
        }
        *dst = '\0';
    }

    if (slot >= cache->num_entries) {
        cache->num_entries = slot + 1;
    }

    return slot;
}

// ============================================================================
//  4.  LRU eviction
// ============================================================================

void rc_evict_lru(RunwayCache* cache) {
    if (cache == 0 || cache->num_entries == 0) return;

    int oldest_frame = cache->entries[0].frame_last_used;
    int oldest_idx = 0;

    for (int i = 1; i < cache->num_entries; ++i) {
        if (cache->entries[i].frame_last_used < oldest_frame) {
            oldest_frame = cache->entries[i].frame_last_used;
            oldest_idx = i;
        }
    }

    __builtin_memset(&cache->entries[oldest_idx], 0, sizeof(RunwayCacheEntry));
    cache->stat_evictions++;

    // Compact the array if this was the last entry
    if (oldest_idx == cache->num_entries - 1) {
        cache->num_entries--;
    }
}

// ============================================================================
//  5.  Invalidation
// ============================================================================

void rc_invalidate_all(RunwayCache* cache) {
    if (cache == 0) return;
    for (int i = 0; i < cache->num_entries; ++i) {
        cache->entries[i].dirty = true;
    }
}

// ============================================================================
//  6.  Spatial tile operations
// ============================================================================

int rc_get_or_create_tile(RunwayCache* cache, int tile_x, int tile_y) {
    if (cache == 0) return -1;

    // Search existing tiles
    for (int i = 0; i < cache->num_tiles; ++i) {
        if (cache->tiles[i].tile_x == tile_x && cache->tiles[i].tile_y == tile_y) {
            return i;
        }
    }

    // Create new tile
    if (cache->num_tiles >= RC_MAX_TILES) return -1;

    int idx = cache->num_tiles;
    cache->tiles[idx].tile_x = tile_x;
    cache->tiles[idx].tile_y = tile_y;
    cache->tiles[idx].num_runways = 0;
    cache->tiles[idx].valid = true;
    cache->num_tiles++;

    return idx;
}

void rc_find_nearby(RunwayCache* cache,
                     FLOAT64 lat_deg,
                     FLOAT64 lon_deg,
                     int* out_indices,
                     int* out_count,
                     int max_out) {
    if (cache == 0 || out_indices == 0 || out_count == 0) return;

    int tile_x, tile_y;
    rc_latlon_to_tile(lat_deg, lon_deg, &tile_x, &tile_y);

    *out_count = 0;

    // Check the tile and its 4 neighbours
    const int nx[] = {0, -1, 1, 0, 0};
    const int ny[] = {0, 0, 0, -1, 1};

    for (int n = 0; n < 5 && *out_count < max_out; ++n) {
        const int tx = tile_x + nx[n];
        const int ty = tile_y + ny[n];

        for (int t = 0; t < cache->num_tiles; ++t) {
            if (cache->tiles[t].tile_x == tx && cache->tiles[t].tile_y == ty) {
                for (int r = 0; r < cache->tiles[t].num_runways && *out_count < max_out; ++r) {
                    out_indices[*out_count] = cache->tiles[t].runway_indices[r];
                    (*out_count)++;
                }
                break;
            }
        }
    }
}

// ============================================================================
//  7.  Prefetch support
// ============================================================================

void rc_set_prefetch_target(RunwayCache* cache,
                             FLOAT64 ac_lat_deg,
                             FLOAT64 ac_lon_deg) {
    if (cache == 0) return;
    cache->prefetch_lat = ac_lat_deg;
    cache->prefetch_lon = ac_lon_deg;
    cache->prefetch_active = true;
}

void rc_tick_prefetch(RunwayCache* cache,
                       const AirportDatabase* db,
                       int current_frame) {
    if (cache == 0 || db == 0 || !cache->prefetch_active) return;

    // Find nearest airport to prefetch target position
    const AirportRecord* airport = db_find_nearest_airport(
        (AirportDatabase*)db,
        cache->prefetch_lat,
        cache->prefetch_lon);

    if (airport == 0) {
        cache->prefetch_active = false;
        return;
    }

    // Prefetch all runways at this airport
    for (int i = 0; i < airport->num_runways; ++i) {
        const int idx = airport->runway_indices[i];
        if (idx < 0 || idx >= db->num_runways) continue;

        // Check if already cached
        if (rc_lookup(cache, idx) != 0) continue;

        // Insert into cache
        rc_insert(cache, &db->runways[idx], idx, current_frame);
        // Mark as prefetched
        for (int e = 0; e < cache->num_entries; ++e) {
            if (cache->entries[e].runway_db_index == idx) {
                cache->entries[e].prefetched = true;
                break;
            }
        }
    }

    cache->prefetch_active = false;
}

// ============================================================================
//  8.  Debug logging
// ============================================================================

void rc_debug_log(const RunwayCache* cache) {
    if (cache == 0) {
        MSFS_Log("[C_HUD_RC] Cache: NULL");
        return;
    }
    MSFS_Log("[C_HUD_RC] Cache: %d entries, %d tiles, "
             "hits=%d misses=%d evictions=%d frame=%d",
             cache->num_entries, cache->num_tiles,
             cache->stat_hits, cache->stat_misses,
             cache->stat_evictions, cache->frame_counter);
    for (int i = 0; i < cache->num_entries; ++i) {
        MSFS_Log("[C_HUD_RC]   [%d] %s/%s dirty=%d prefetched=%d last_frame=%d",
                 i, cache->entries[i].icao_code, cache->entries[i].runway_id,
                 (int)cache->entries[i].dirty, (int)cache->entries[i].prefetched,
                 cache->entries[i].frame_last_used);
    }
}
