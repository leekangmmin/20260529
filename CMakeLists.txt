# ============================================================================
#  Conformal HUD – Runway Symbology  (C_HUD_Runway)
#  MSFS 2024 WASM gauge module  ·  v2.7.0  ·  MULTI-AIRCRAFT AVIONICS PLATFORM
#
#  v2.6.0 additions:
#    · IHudAircraftBehavior interface for Boeing/Airbus abstraction
#    · BoeingHGSBehavior concrete implementation
#    · AirbusHUDBehavior concrete implementation
#    · Automatic aircraft detection engine
#    · Flight data telemetry recording & replay
#
#  v2.4.0 additions:
#    · Full L:var publishing pipeline (critical dead-code fix)
#    · Subsystem registration logging and heartbeat counters
#    · Frame timing diagnostics (FPS min/max/avg, jitter)
#    · Live calibration framework (calibration.cpp)
#    · Projection verification mode (debug toggles)
#    · Optical realism (phosphor, bloom, edge fade, temporal blend)
#    · NAV1 frequency token for ILS runway detection
#
#  v2.1.0 additions:
#    · Semi-collimated rendering (collimation.cpp)
#    · Boeing-style flare guidance (flare.cpp)
#    · Enhanced Vision System (evs.cpp)
#    · Symbol stabilisation filters (stabilization.cpp)
#    · Advanced symbology (advanced_symbology.cpp)
#
#  Build:
#    cmake -B build -DMSFS_SDK_ROOT=… [-DNANOVG_DIR=…]
#    cmake --build build
# ============================================================================
cmake_minimum_required(VERSION 3.22)
project(C_HUD_Runway VERSION 2.7.0 LANGUAGES C CXX)

# ---------------------------------------------------------------------------
#  C++17 – required by MSFS gauge API and our own code
# ---------------------------------------------------------------------------
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ============================================================================
#  1.  MSFS SDK discovery
# ============================================================================
if(NOT DEFINED MSFS_SDK_ROOT)
    if(DEFINED ENV{MSFS_SDK_ROOT})
        set(MSFS_SDK_ROOT "$ENV{MSFS_SDK_ROOT}")
    else()
        set(MSFS_SDK_ROOT "C:/MSFS_SDK"
            CACHE PATH "Root of the MSFS SDK installation")
    endif()
endif()

# --- WASM header tree ---
set(MSFS_WASM_INCLUDE "${MSFS_SDK_ROOT}/WASM/include")
# --- Precompiled MSFS WASM import libraries ---
set(MSFS_WASM_LIB     "${MSFS_SDK_ROOT}/WASM/lib/wasm32")

# ============================================================================
#  2.  NanoVG discovery (optional)
# ============================================================================
option(NANOVG_ENABLED "Build and link NanoVG for C++-side vector rendering" ON)

if(NANOVG_ENABLED)
    if(NOT DEFINED NANOVG_DIR)
        set(NANOVG_DIR "${CMAKE_SOURCE_DIR}/lib/nanovg"
            CACHE PATH "Directory containing nanovg/src/nanovg.h")
    endif()
    if(NOT EXISTS "${NANOVG_DIR}/src/nanovg.h")
        message(WARNING
            "NanoVG not found at ${NANOVG_DIR}/src/nanovg.h.\n"
            "  Clone it:  git clone https://github.com/memononen/nanovg ${NANOVG_DIR}\n"
        )
        set(NANOVG_ENABLED OFF)
    endif()
endif()

# ============================================================================
#  3.  Toolchain – LLVM/Clang → wasm32-unknown-unknown
# ============================================================================
set(CMAKE_SYSTEM_NAME       Generic)
set(CMAKE_SYSTEM_PROCESSOR  wasm32)

set(CMAKE_C_COMPILER        clang)
set(CMAKE_CXX_COMPILER      clang++)
set(CMAKE_AR                llvm-ar)
set(CMAKE_RANLIB            llvm-ranlib)

set(CMAKE_C_COMPILER_TARGET    wasm32-unknown-unknown)
set(CMAKE_CXX_COMPILER_TARGET  wasm32-unknown-unknown)

set(CMAKE_CXX_STANDARD_INCLUDE_DIRECTORIES "")
set(CMAKE_C_STANDARD_INCLUDE_DIRECTORIES   "")

# --- Compile flags ---
set(WASM_C_FLAGS
    -nostdlib
    -nostdinc
    -target wasm32-unknown-unknown
    -mcpu=generic
    -fno-exceptions
    -mllvm -wasm-disable-explicit-locals
    -fno-strict-aliasing
    -Wall -Wextra -Wpedantic
    -Wno-unused-parameter
)
set(WASM_CXX_FLAGS ${WASM_C_FLAGS}
    -fno-rtti
)

set(CMAKE_C_FLAGS           "${WASM_C_FLAGS} -std=c11")
set(CMAKE_CXX_FLAGS         "${WASM_CXX_FLAGS} -std=c++17")

# --- Link flags ---
string(APPEND CMAKE_EXE_LINKER_FLAGS
    -nostdlib
    -Wl,--no-entry
    -Wl,--export-all
    -Wl,--allow-undefined
    -Wl,--stack-first
    -Wl,--initial-memory=16777216
    -Wl,--max-memory=67108864
    -Wl,--export=module_init
    -Wl,--export=module_deinit
    -Wl,--export=gauge_callback
)

# ============================================================================
#  4.  Source files
# ============================================================================
set(GAUGE_SOURCES
    src/main.cpp                        # WASM lifecycle + update pipeline
    src/module.cpp                      # Gauge callbacks
    src/lvar_table.cpp                  # L:Var token table (v2.2.0)
    src/hud/aircraft_profiles.cpp       # Aircraft HUD profile database
    src/hud/runway_projection.cpp       # Runway corner computation & projection
    src/hud/fpv.cpp                     # Flight Path Vector computation
    src/hud/guidance.cpp                # ILS guidance & flight director
    src/hud/symbology.cpp               # Symbology aggregation & publishing
    src/hud/collimation.cpp             # Semi-collimated rendering (v2.1.0)
    src/hud/flare.cpp                   # Flare guidance system (v2.1.0)
    src/hud/evs.cpp                     # Enhanced Vision System (v2.1.0)
    src/hud/stabilization.cpp           # Symbol stabilisation filters (v2.1.0)
    src/hud/advanced_symbology.cpp      # Advanced symbology (v2.1.0)
    src/hud/airport_database.cpp        # Airport/runway database (v2.2.0)
    src/hud/runway_cache.cpp            # Runway geometry cache (v2.2.0)
    src/hud/calibration.cpp             # Calibration system (v2.2.0)
    src/hud/rollout.cpp                 # Rollout guidance (v2.4.0)
    src/hud/visual_response.cpp         # Visual response effects (v2.4.0)
    src/hud/declutter.cpp               # Declutter system (v2.4.0)
    src/hud/confidence.cpp              # Confidence-based rendering (v2.4.0)
    src/hud/depth_illusion.cpp          # Optical depth effects (v2.4.0)
    # ================================================================
    #  v2.4.0 — Airbus A350-specific modules
    # ================================================================
    src/hud/aircraft/a350_profile.cpp       # A350 HUD behaviour profile
    src/hud/aircraft/airbus_fpv.cpp         # Airbus FPV filter
    src/hud/aircraft/a350_flare_law.cpp     # Airbus flare law
    src/hud/aircraft/a350_rollout.cpp       # Airbus rollout augmentation
    src/hud/aircraft/a350_cat3.cpp          # Airbus CAT III augmentation
    src/hud/aircraft/a350_symbology.cpp     # Airbus symbology styling
    # ================================================================
    #  v3.0.0 — A350 XWB Certification Package
    # ================================================================
    src/hud/aircraft/a350_fpv_controller.cpp    # A350 FPV controller
    src/hud/aircraft/a350_horizon.cpp           # A350 horizon stabilization
    src/hud/aircraft/a350_autoland.cpp          # A350 autoland HUD layer
    src/hud/aircraft/a350_landing_energy.cpp    # A350 landing energy model
    src/hud/aircraft/a350_runway_augmentation.cpp # A350 runway augmentation
    # ================================================================
    #  v2.6.0 — Multi-aircraft abstraction & telemetry
    # ================================================================
    src/hud/aircraft/boeing_hgs_behavior.cpp    # Boeing HGS behavior
    src/hud/aircraft/airbus_hud_behavior.cpp    # Airbus HUD behavior
    src/hud/aircraft_detector.cpp               # Automatic aircraft detection
    src/hud/telemetry.cpp                       # Flight data recording & replay
    # ================================================================
    #  PHASE 4 — Real HUD Integration
    # ================================================================
    src/hud/hud_deployment.cpp               # HUD deployment/stow detection
    src/hud/combiner_geometry.cpp            # Combiner glass geometry management

)

set(GAUGE_HEADERS
    include/module.h
    include/projection.h
    include/hud/symbology.h
    include/hud/aircraft_profiles.h
    include/hud/runway_projection.h
    include/hud/fpv.h
    include/hud/guidance.h
    include/hud/collimation.h
    include/hud/flare.h
    include/hud/evs.h
    include/hud/stabilization.h
    include/hud/advanced_symbology.h
    include/hud/verification.h          # Verification / debug overlay (v2.2.0)
    include/hud/airport_database.h      # Airport/runway database (v2.2.0)
    include/hud/runway_cache.h          # Runway geometry cache (v2.2.0)
    include/hud/rollout.h               # Rollout guidance (v2.4.0)
    include/hud/visual_response.h       # Visual response effects (v2.4.0)
    include/hud/declutter.h             # Declutter system (v2.4.0)
    include/hud/confidence.h            # Confidence-based rendering (v2.4.0)
    include/hud/depth_illusion.h        # Optical depth effects (v2.4.0)
    # ================================================================
    #  v2.4.0 — Airbus A350-specific headers
    # ================================================================
    include/hud/aircraft/a350_profile.h     # A350 HUD behaviour profile
    include/hud/aircraft/airbus_fpv.h       # Airbus FPV filter
    include/hud/aircraft/a350_flare_law.h   # Airbus flare law
    include/hud/aircraft/a350_rollout.h     # Airbus rollout augmentation
    include/hud/aircraft/a350_cat3.h        # Airbus CAT III augmentation
    include/hud/aircraft/a350_symbology.h   # Airbus symbology styling
    # ================================================================
    #  v3.0.0 — A350 XWB Certification Package headers
    # ================================================================
    include/hud/aircraft/a350_fpv_controller.h  # A350 FPV controller
    include/hud/aircraft/a350_horizon.h         # A350 horizon stabilization
    include/hud/aircraft/a350_autoland.h        # A350 autoland HUD layer
    include/hud/aircraft/a350_landing_energy.h  # A350 landing energy model
    include/hud/aircraft/a350_runway_augmentation.h # A350 runway augmentation
    # ================================================================
    #  v2.6.0 — Multi-aircraft abstraction & telemetry headers
    # ================================================================
    include/hud/aircraft/ihud_aircraft_behavior.h   # Unified behavior interface
    include/hud/aircraft/boeing_hgs_behavior.h      # Boeing HGS behavior
    include/hud/aircraft/airbus_hud_behavior.h      # Airbus HUD behavior
    include/hud/aircraft_detector.h                 # Automatic aircraft detection
    include/hud/telemetry.h                         # Flight data recording & replay
    # ================================================================
    #  PHASE 4 — Real HUD Integration headers
    # ================================================================
    include/hud/hud_deployment.h                # HUD deployment/stow detection
    include/hud/combiner_geometry.h             # Combiner glass geometry management

)

# ============================================================================
#  5.  NanoVG static library target
# ============================================================================
if(NANOVG_ENABLED)
    add_library(nanovg STATIC
        "${NANOVG_DIR}/src/nanovg.c"
    )
    target_include_directories(nanovg PUBLIC
        "${NANOVG_DIR}/src"
    )
    target_compile_options(nanovg PRIVATE
        ${WASM_C_FLAGS}
        -std=c99
        -DNANOVG_IMPLEMENTATION
        -O2
    )
    target_compile_definitions(nanovg PRIVATE
        NANOVG_IMPLEMENTATION
    )
    set_target_properties(nanovg PROPERTIES
        LINKER_LANGUAGE C
    )
    message(STATUS "NanoVG enabled  →  ${NANOVG_DIR}")
endif()

# ============================================================================
#  6.  Executable target → C_HUD_Runway.wasm
# ============================================================================
add_executable(C_HUD_Runway ${GAUGE_SOURCES} ${GAUGE_HEADERS})

target_include_directories(C_HUD_Runway PRIVATE
    include
    include/hud
    src
    "${MSFS_WASM_INCLUDE}"
)

target_link_directories(C_HUD_Runway PRIVATE
    "${MSFS_WASM_LIB}"
)

set(WASM_LINK_LIBS "")
if(EXISTS "${MSFS_WASM_LIB}/libSimConnect.a")
    list(APPEND WASM_LINK_LIBS "${MSFS_WASM_LIB}/libSimConnect.a")
elseif(EXISTS "${MSFS_WASM_LIB}/SimConnect.lib")
    list(APPEND WASM_LINK_LIBS "${MSFS_WASM_LIB}/SimConnect.lib")
else()
    message(WARNING "SimConnect stub not found at ${MSFS_WASM_LIB}.")
endif()

if(NANOVG_ENABLED)
    target_link_libraries(C_HUD_Runway PRIVATE nanovg)
endif()

if(WASM_LINK_LIBS)
    target_link_libraries(C_HUD_Runway PRIVATE ${WASM_LINK_LIBS})
endif()

set_target_properties(C_HUD_Runway PROPERTIES
    SUFFIX              ".wasm"
    LINKER_LANGUAGE     CXX
    LINK_SEARCH_START_STATIC  ON
    LINK_SEARCH_END_STATIC    ON
    RUNTIME_OUTPUT_DIRECTORY  "${CMAKE_BINARY_DIR}"
)

# ============================================================================
#  7.  Header dependency verification (post-config)
# ============================================================================
include(CMakeDependentOption)

# Verify that all referenced headers exist
foreach(_hdr ${GAUGE_HEADERS})
    if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/${_hdr}")
        message(FATAL_ERROR "Missing header: ${_hdr}")
    endif()
endforeach()

# Verify that all referenced source files exist
foreach(_src ${GAUGE_SOURCES})
    if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/${_src}")
        message(FATAL_ERROR "Missing source file: ${_src}")
    endif()
endforeach()
