# CERTIFICATION SYSTEM AUDIT

**Generated:** 2026-05-29  
**Target:** `installer/certification.py`

---

## 1. How Readiness Scores Are Computed

The `CertificationEngine.compute_readiness_score()` method computes a score from 0–100 using 4 weighted components:

### Component Breakdown

| Component | Max Points | Source | Computation |
|---|---|---|---|
| **Test Score** | 40 | `_get_test_pass_rate()` | `min(40.0, test_pass_rate * 40.0)` — assumes 0.95 default |
| **Coverage Score** | 30 | `len(self.compat_map)` | `min(1.0, aircraft_supported / 8.0) * 30.0` |
| **Compatibility Score** | 20 | `compat_map` version entries | `versioned_aircraft / max(aircraft_supported, 1) * 20.0` |
| **Stability Score** | 10 | `__version__` string | Major >= 2 → 10.0, Major >= 1 → 7.0 + minor * 0.5 |

### Category Thresholds

| Total Score | Category |
|---|---|
| >= 90 | production_ready |
| >= 75 | release_candidate |
| >= 60 | beta |
| < 60 | development |

---

## 2. Every Hardcoded Metric and Constant

### 2.1 Hardcoded Parameters in `compute_readiness_score()`

| Constant | Value | Location | Purpose | Risk |
|---|---|---|---|---|
| Test max weight | `40.0` | compute_readiness_score() | Maximum test score | OK — design parameter |
| Coverage max weight | `30.0` | compute_readiness_score() | Maximum coverage score | OK — design parameter |
| Compatibility max weight | `20.0` | compute_readiness_score() | Maximum compatibility score | OK — design parameter |
| Stability max weight | `10.0` | compute_readiness_score() | Maximum stability score | OK — design parameter |
| Full coverage target | `8` | compute_readiness_score() | "Perfect score if we support 8 aircraft types" | 🔶 **HARDCODED** — should be `len(compat_map)` or a project constant |
| Score thresholds | `90, 75, 60` | compute_readiness_score() | Category boundaries | 🔶 **HARDCODED** — should be configurable or derived |
| Stability major≥2 | `10.0` | compute_readiness_score() | v2.x+ = full stability | 🔶 **HARDCODED** — arbitrary maturity assumption |
| Stability major≥1 | `7.0` | compute_readiness_score() | v1.x base score | 🔶 **HARDCODED** |
| Stability minor weight | `0.5` | compute_readiness_score() | Per-minor bonus | 🔶 **HARDCODED** |
| Stability max bonus | `3.0` | compute_readiness_score() | Cap on minor version bonus | 🔶 **HARDCODED** |

### 2.2 Hardcoded Parameters in `_get_test_pass_rate()`

| Constant | Value | Location | Purpose | Risk |
|---|---|---|---|---|
| Default pass rate | `0.95` | _get_test_pass_rate() | Assumed test pass rate | 🔴 **SIMULATED** — Not reading actual pytest results |
| Empty cache rate | `0.98` | _get_test_pass_rate() | When `lastfailed` is empty | 🔴 **SIMULATED** — Assumes no failures = 98% |
| Fallback rate | `0.90` | _get_test_pass_rate() | When cache cannot be read | 🔴 **SIMULATED** — Default guess |

### 2.3 Hardcoded Values in `generate_certification_matrix()`

| Constant | Value | Location | Purpose | Risk |
|---|---|---|---|---|
| Certification status | `CERTIFIED` | generate_certification_matrix() | All aircraft get CERTIFIED | 🔴 **FALSE** — All aircraft marked as certified regardless of actual testing |
| Test pass rate | `0.95` | generate_certification_matrix() | Assumed rate | 🔴 **SIMULATED** — Not from actual test run |
| Coverage percent | `0.85` | generate_certification_matrix() | Assumed coverage | 🔴 **SIMULATED** — Not measured |
| MSFS version | `"both"` | generate_certification_matrix() | All aircraft claim both MSFS 2020 & 2024 | 🔶 **UNVERIFIED** — May not be true for all |
| Known issues | static dict | `_get_known_issues()` | Hand-crafted per aircraft | ⚠️ **MAINTENANCE BURDEN** — duplicates C++ registry |

---

## 3. Data Flow Diagram

```
__version__ ("2.6.0")
    │
    ├──→ CertificationMatrix.installer_version
    │
    └──→ compute_readiness_score()
              │
              ├── Stability Score = major≥2 → 10.0
              │                       (hardcoded maturity rule)
              │
              ├── Coverage Score  = min(1.0, aircraft_count / 8.0) * 30
              │                       (hardcoded target of 8 aircraft)
              │
              ├── Compat Score    = versioned/total * 20
              │
              └── Test Score      = _get_test_pass_rate() * 40
                                      │
                                      └──→ Reads .pytest_cache/lastfailed
                                            (never actually runs pytest)
```

---

## 4. Identified Issues

### 🔴 Issue 1: Test Pass Rate Is Simulated, Not Measured
The scoring system never actually runs pytest. It reads a stale cache file and falls back to hardcoded assumptions (0.95). This means:
- The "test score" component is fictional
- CI/CD cannot trust the score
- A failing test suite would still report 90%+ pass rate

### 🔴 Issue 2: All Aircraft Are Automatically "CERTIFIED"
`generate_certification_matrix()` assigns `CertificationStatus.CERTIFIED` to every aircraft without any actual certification test. The status is meaningless.

### 🔴 Issue 3: Score Thresholds Are Hardcoded
The 90/75/60 thresholds for production_ready/release_candidate/beta/development are hardcoded magic numbers with no justification.

### 🟡 Issue 4: Data Duplication
The known_issues and notes dictionaries in `_get_known_issues()` and `_get_cert_notes()` duplicate aircraft metadata that exists in the C++ registry (`aircraft_detector.cpp`) and Python scanner (`aircraft_scanner.py`). Any change requires updates in 3+ places.

### 🟡 Issue 5: Coverage Target Hardcoded to 8 Aircraft
The formula `min(1.0, aircraft_supported / 8.0)` assumes 8 is the perfect number of supported aircraft. If new aircraft are added, this stays at 8.

### ⚠️ Issue 6: Imports of Non-Existent Functions
`certification.py` imports `check_version_compatibility`, `get_aircraft_compatibility_map`, `is_title_supported` from `aircraft_scanner.py`. These exist, but the code never validates that the Python compatibility map matches the C++ `AircraftCompatibilitySignature` struct in `module.h`.

---

## 5. Recommendations

1. **Make certification real** — Integrate actual pytest execution (or at least read `--junitxml` output)
2. **Replace hardcoded constants** with project-level configuration
3. **Derive aircraft count** from a single registry, not a magic number
4. **Add cross-validation** between Python compatibility map and C++ signatures
5. **Remove fictional scoring** until it reflects actual test results
