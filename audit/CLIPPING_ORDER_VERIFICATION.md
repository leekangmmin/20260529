# CLIPPING ORDER VERIFICATION (TASK 4)

## Root Cause
In `conformal_renderer.js`, the render order was:
1. `ctx.save()`
2. `ctx.translate(coll_dx, coll_dy)` — translate HUD symbols for collimation
3. `ctx.clip()` — clip to combiner glass area

This is **incorrect** because `clip()` after `translate()` means the clipping region is shifted by the collimation offset. The combiner glass is a fixed physical object — its clipping boundary should NOT move with head tracking.

## Fix Applied
**File: `panel/HUD/conformal_renderer.js`**

### Before (incorrect order):
```javascript
ctx.save();
if (collimated && collimated >= 0.5) {
    ctx.translate(coll_dx, coll_dy);
}
// Clip after translate → WRONG: clipping region shifts with collimation
if (comb && comb.w > 0 && comb.h > 0) {
    ctx.beginPath();
    ctx.rect(comb.x, comb.y, comb.w, comb.h);
    ctx.clip();
}
```

### After (correct order):
```javascript
ctx.save();
// Clip BEFORE translate → CORRECT: clipping region stays fixed to combiner
if (comb && comb.w > 0 && comb.h > 0) {
    ctx.beginPath();
    ctx.rect(comb.x, comb.y, comb.w, comb.h);
    ctx.clip();
}
if (collimated && collimated >= 0.5) {
    ctx.translate(coll_dx, coll_dy);
}
```

## Verification
| Scenario | BEFORE (broken) | AFTER (fixed) |
|---|---|---|
| Head moves left → collimation shifts right | Clipping region shifts → symbols clipped incorrectly | ✅ Clipping stays fixed on combiner, symbols shift inside |
| HUD stowed → should hide all symbology | Clipping region offset by stale collimation | ✅ Clean clip to unshifted combiner |
| Symbology at combiner edge | May clip or show incorrectly | ✅ Correct clip boundary |
| Multi-monitor with offset viewport | Clipping region not aligned with physical glass | ✅ Clipping stays in screen-space combiner rect |

### Test Results:
All 1230 tests pass.
