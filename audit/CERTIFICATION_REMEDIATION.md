# CERTIFICATION REMEDIATION — Phase 3, Task 6

**Date:** 2026-05-29  
**Scope:** Replace hardcoded/fabricated certification test scores with real measured values.

---

## 1. Hardcoded Values Identified

From `audit/CERTIFICATION_AUDIT.md`:

| Constant | Old Value | Issue |
|---|---|---|
| Default pass rate | 0.95 | 🔴 **Hardcoded** — never ran pytest |
| Empty cache pass rate | 0.98 | 🔴 **Hardcoded** — assumed no failures = 98% |
| Fallback pass rate | 0.90 | 🔴 **Hardcoded** — default guess |
| Test pass rate in matrix | 0.95 | 🔴 **Hardcoded** — same fabricated value |

## 2. Changes Made

### New method: `_run_pytest_and_get_results()`
- Runs `python -m pytest --junitxml <path> tests/` as a subprocess
- Parses JUnit XML output using `xml.etree.ElementTree`
- Returns `(pass_rate, total, passed, failed)` tuple
- Rolls back to estimated rate with explanation if pytest unavailable

### Recursion Guard
- Checks `PYTEST_CURRENT_TEST` environment variable to avoid recursive pytest invocation when certification tests run inside pytest
- Falls back to estimated rates when detected

### Measured vs Estimated Tracking
- Stores `_last_test_total` and `_last_test_passed` on `CertificationEngine` instance
- Modifies `compute_readiness_score()` to label test score as `"measured"` or `"estimated"` in the details output

## 3. Preserved Design Elements

| Aspect | Status |
|---|---|
| Scoring weights unchanged | ✅ (40 test / 30 coverage / 20 compat / 10 stability) |
| Report format unchanged | ✅ (JSON/Markdown output same structure) |
| Category thresholds unchanged | ✅ (90/75/60 for production_ready/release_candidate/beta/development) |
| Graceful fallback when pytest missing | ✅ Clear logging and estimated rate used |

## 4. Test Evidence

All 16 tests in `tests/test_certification.py` pass:
- `test_compute_readiness_score` — validates score range and categories
- `test_readiness_breakdown` — validates component scores
- `test_release_readiness_score_range` — validates 0..100 range with weights
- All report generation tests — validate unchanged output formats

## 5. Success Criteria

| Criterion | Status |
|---|---|
| Replace fabricated values with measured values | ✅ (runs pytest, parses JUnit XML) |
| Execute pytest | ✅ (via subprocess) |
| Read actual results | ✅ (parses JUnit XML test suite attributes) |
| Gracefully handle missing pytest | ✅ (clear warning, estimated fallback) |
| Clearly distinguish measured vs estimated | ✅ (detail string annotation) |
| Scoring weights unchanged | ✅ |
| Report format unchanged | ✅ |
