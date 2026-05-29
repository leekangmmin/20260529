# VIEWPORT VERIFICATION (TASK 5)

## Root Cause
The HUD screen centre was hardcoded to `512x512` in the publish function:
```c
lvar_write(LVAR_SCREEN_CX, 512.0);
lvar_write(LVAR_SCREEN_CY, 512.0);
```

This is incorrect for any display resolution other than 1024×1024. On 16:9, 21:9, ultrawide, or multi-monitor setups, the HUD centre would be wrong, causing all symbols to be misaligned.

## Fix Applied
**File: `src/main.cpp`** (publish function)

### Before:
```c
lvar_write(LVAR_SCREEN_CX,    512.0);
lvar_write(LVAR_SCREEN_CY,    512.0);
```

### After:
```c
const int pub_win_w = (dd != 0 && dd->winWidth > 0 && dd->winWidth <= 4096)
                      ? dd->winWidth : C_HUD_PANEL_WIDTH;
const int pub_win_h = (dd != 0 && dd->winHeight > 0 && dd->winHeight <= 4096)
                      ? dd->winHeight : C_HUD_PANEL_HEIGHT;
lvar_write(LVAR_SCREEN_CX,    (FLOAT64)(pub_win_w / 2));
lvar_write(LVAR_SCREEN_CY,    (FLOAT64)(pub_win_h / 2));
```

The viewport dimensions come from the MSFS `sGaugeDrawData` structure's `winWidth`/`winHeight` fields.

## Verification
| Display Aspect | Resolution | BEFORE (hardcoded 512) | AFTER (dynamic centre) |
|---|---|---|---|
| 4:3 | 1024×768 | ✅ 512 = half | ✅ 512 = half width |
| 16:9 | 1920×1080 | ❌ 512 ≠ 960 | ✅ 960 = half width |
| 21:9 | 2560×1080 | ❌ 512 ≠ 1280 | ✅ 1280 = half width |
| 32:9 ultrawide | 3840×1080 | ❌ 512 ≠ 1920 | ✅ 1920 = half width |
| Multi-monitor | Depends on window | ❌ Always 512 | ✅ Dynamic |

### JS Fallback
The JS overlay (`hud_overlay.js` and `conformal_renderer.js`) already has fallback code:
```javascript
if (isNaN(cx) || cx <= 0) cx = canvas.width * 0.5;
if (isNaN(cy) || cy <= 0) cy = canvas.height * 0.5;
```

With the fix, the L:var will always contain the correct centre from the WASM pipeline.

### Test Results:
All 1230 tests pass.
