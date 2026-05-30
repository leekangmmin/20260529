@echo off
REM ============================================================================
REM  build_wasm.bat  --  C_HUD_Runway  WASM build script  (Windows)
REM
REM  Requires:
REM    - LLVM / Clang 17+ with wasm32-unknown-unknown target
REM    - MSFS SDK 0.23+ (set MSFS_SDK_ROOT env or pass --sdk-path)
REM
REM  Usage:
REM    build_wasm.bat                          REM uses MSFS_SDK_ROOT env
REM    build_wasm.bat --sdk-path C:\MSFS_SDK   REM explicit path
REM
REM  Output:  panel\C_HUD_Runway.wasm
REM ============================================================================
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set OUTPUT_DIR=%SCRIPT_DIR%panel
set OUTPUT_WASM=%OUTPUT_DIR%\C_HUD_Runway.wasm

REM -------------------------------------------------------------------------
REM  SDK discovery
REM -------------------------------------------------------------------------
if /I "%1"=="--sdk-path" (
    if not "%2"=="" (
        set MSFS_SDK_ROOT=%2
    )
)

if "%MSFS_SDK_ROOT%"=="" (
    echo ERROR: MSFS_SDK_ROOT not set. Provide --sdk-path or set the environment variable.
    echo   set MSFS_SDK_ROOT=C:\MSFS_SDK
    exit /b 1
)

set MSFS_WASM_INCLUDE=%MSFS_SDK_ROOT%\WASM\include
set MSFS_WASM_LIB=%MSFS_SDK_ROOT%\WASM\lib\wasm32

if not exist "%MSFS_WASM_INCLUDE%" (
    echo ERROR: MSFS SDK WASM include not found at: %MSFS_WASM_INCLUDE%
    exit /b 1
)

echo.==^> C_HUD_Runway WASM Build
echo.    SDK root: %MSFS_SDK_ROOT%
echo.    Output:   %OUTPUT_WASM%

REM -------------------------------------------------------------------------
REM  Source files
REM -------------------------------------------------------------------------
set SRC_ROOT=%SCRIPT_DIR%src
set INCLUDE_ROOT=%SCRIPT_DIR%include

set SRC_FILES=^
    "%SRC_ROOT%\main.cpp" ^
    "%SRC_ROOT%\module.cpp" ^
    "%SRC_ROOT%\lvar_table.cpp" ^
    "%SRC_ROOT%\hud\aircraft_profiles.cpp" ^
    "%SRC_ROOT%\hud\runway_projection.cpp" ^
    "%SRC_ROOT%\hud\fpv.cpp" ^
    "%SRC_ROOT%\hud\guidance.cpp" ^
    "%SRC_ROOT%\hud\symbology.cpp" ^
    "%SRC_ROOT%\hud\collimation.cpp" ^
    "%SRC_ROOT%\hud\flare.cpp" ^
    "%SRC_ROOT%\hud\evs.cpp" ^
    "%SRC_ROOT%\hud\stabilization.cpp" ^
    "%SRC_ROOT%\hud\advanced_symbology.cpp" ^
    "%SRC_ROOT%\hud\airport_database.cpp" ^
    "%SRC_ROOT%\hud\runway_cache.cpp" ^
    "%SRC_ROOT%\hud\calibration.cpp" ^
    "%SRC_ROOT%\hud\rollout.cpp" ^
    "%SRC_ROOT%\hud\visual_response.cpp" ^
    "%SRC_ROOT%\hud\declutter.cpp" ^
    "%SRC_ROOT%\hud\confidence.cpp" ^
    "%SRC_ROOT%\hud\depth_illusion.cpp" ^
    "%SRC_ROOT%\hud\aircraft\a350_profile.cpp" ^
    "%SRC_ROOT%\hud\aircraft\airbus_fpv.cpp" ^
    "%SRC_ROOT%\hud\aircraft\a350_flare_law.cpp" ^
    "%SRC_ROOT%\hud\aircraft\a350_rollout.cpp" ^
    "%SRC_ROOT%\hud\aircraft\a350_cat3.cpp" ^
    "%SRC_ROOT%\hud\aircraft\a350_symbology.cpp" ^
    "%SRC_ROOT%\hud\aircraft\a350_fpv_controller.cpp" ^
    "%SRC_ROOT%\hud\aircraft\a350_horizon.cpp" ^
    "%SRC_ROOT%\hud\aircraft\a350_autoland.cpp" ^
    "%SRC_ROOT%\hud\aircraft\a350_landing_energy.cpp" ^
    "%SRC_ROOT%\hud\aircraft\a350_runway_augmentation.cpp" ^
    "%SRC_ROOT%\hud\aircraft\boeing_hgs_behavior.cpp" ^
    "%SRC_ROOT%\hud\aircraft\airbus_hud_behavior.cpp" ^
    "%SRC_ROOT%\hud\aircraft_detector.cpp" ^
    "%SRC_ROOT%\hud\telemetry.cpp" ^
    "%SRC_ROOT%\hud\hud_deployment.cpp" ^
    "%SRC_ROOT%\hud\combiner_geometry.cpp"

REM -------------------------------------------------------------------------
REM  Compile and link
REM -------------------------------------------------------------------------
if "%CLANG%"=="" set CLANG=clang++

echo.    Compiler: %CLANG%

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

REM Compile flags
set CXXFLAGS=-std=c++17 -target wasm32-unknown-unknown -nostdlib -nostdinc -fno-exceptions -fno-rtti -mcpu=generic -mllvm -wasm-disable-explicit-locals -fno-strict-aliasing -Wall -Wextra -Wpedantic -Wno-unused-parameter -Wno-unused-private-field -Wno-c++11-narrowing -D_C_HUD_WASM_BUILD_=1 -O2 -I"%INCLUDE_ROOT%" -I"%MSFS_WASM_INCLUDE%"

REM Link flags
set LDFLAGS=-nostdlib -Wl,--no-entry -Wl,--allow-undefined -Wl,--stack-first -Wl,--initial-memory=16777216 -Wl,--max-memory=67108864 -Wl,--export=module_init -Wl,--export=module_deinit -Wl,--export=gauge_callback_post_install -Wl,--export=gauge_callback_pre_update -Wl,--export=gauge_callback_post_draw -Wl,--export=gauge_callback -Wl,--strip-all -Wl,--gc-sections -o "%OUTPUT_WASM%"

echo.==^> Compiling...

"%CLANG%" %CXXFLAGS% %SRC_FILES% %LDFLAGS%

if %ERRORLEVEL% neq 0 (
    echo.==^> COMPILATION FAILED with error level %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)

REM -------------------------------------------------------------------------
REM  Verify output
REM -------------------------------------------------------------------------
if exist "%OUTPUT_WASM%" (
    for %%A in ("%OUTPUT_WASM%") do set WASM_SIZE=%%~zA
    echo.==^> SUCCESS: %OUTPUT_WASM%  (!WASM_SIZE! bytes)
) else (
    echo.==^> FAILED: %OUTPUT_WASM% not generated
    exit /b 1
)

exit /b 0
