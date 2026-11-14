# SPHEREx Blink Observatory Backend & AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic SPHEREx near-infrared blinking/astrometry/variability FastAPI backend, multi-agency astronomical archive integrations, caching/PostgreSQL+pgvector storage, and citation-validated Cosmic Narrator + Ask This Patch AI services.

**Architecture:** Strict "two brains" design behind narrow `Protocol` seams (`science/ports.py`): pure astrophysics modules (`science/`) have zero imports from `narrator/` or LLM packages and receive archive/catalog data via adapters (`archive/`), while `narrator/` reads only the compact `EvidenceStoreResponse` JSON and validates every claim deterministically via `ClaimValidator`.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, Astropy 8, Astroquery, Reproject, SEP (`sep>=1.4`), Photutils, SciPy, NumPy, LangGraph, LangChain, SQLAlchemy[asyncio], Alembic, PostgreSQL 16 + pgvector, Redis, HTTPX, Pytest, Ruff, Mypy.

**Spec:** [design_draft.md](../../../docs/design_draft.md), [VERIFICATION.md](../../../backend/docs/VERIFICATION.md), [DECISIONS.md](../../../backend/docs/DECISIONS.md)

## Global Constraints

- "Two brains" separation: `backend/app/science/` MUST have zero imports from `backend/app/narrator/` or `langchain*`/`langgraph*`.
- Never compare fluxes across different wavelengths in `variability.py` or `comparisons.py` without `cross_band=True`; use true `WCS(header, fobj=hdul, key="W")` (`sip=None`), NEVER linear `y/2040`.
- `FLAGS` bitmask (`V-06`): cast to `uint32`; reject defect bits `{0,1,2,6,9,10,11,15,17,19,25,26,27}`; NEVER reject `12` (`FULLSAMPLE`) or `21` (`SOURCE`).
- Convert FITS arrays via `np.ascontiguousarray(arr, dtype=np.float32)` before calling `sep` (`sep` rejects big-endian `>f4`).
- Parse `EPSF` BinTableHDU row count dynamically (`441` in `barnards_star_sample.fits`, `451` in `wise_0855_sample.fits`).
- Never claim discovery of Planet Nine, Planet X, "confirmed discovery", or "first detection"; every claim cites a verified `ev_*` ID.
- Offline CI & zero-key parity: all non-`@pytest.mark.live` tests pass with zero network, zero Redis, zero Postgres, and `LLM_PROVIDER=template`/`fake`.
- Commit cleanly after every completed task/slice so work is easy to rewind.

## Review Focus

1. **LVF gradient under FOV rotation:** Wide/rotated cutouts (`0.5°` FOV) shift wavelength across the detector; evaluating `WCS-WAVE` at each detected source's native `(x, y)` (mapped via inverse WCS) rather than frame center prevents false variability on sloped-spectrum stars.
2. **High-PM J2000 -> 2026 drift & polar singularities:** Targets like Barnard's Star drift `~4.5'` from J2000 to 2026; epoch propagation (`SkyCoord.apply_space_motion()`), `|Dec| <= 89.9°` pole guards, and `cos(Dec)` handling in $(\mu_{\alpha*}, \mu_\delta)$ prevent clipped cutouts and polar divide-by-zero.
3. **Resampling variance & `NaN` bleed:** Pre-zeroing masked pixels before `reproject_interp` + analytical variance scaling + conservative mask footprint prevents `NaN` holes from destroying stars or biasing $\chi^2_\nu$ downward.
4. **LLM / prompt-injection & numeric hallucination:** Untrusted user questions and retrieved abstracts wrapped in delimiters + full-prose numeric checking + `ClaimValidator` verification eliminate fabricated DOIs, wrong markers, and banned claims.
5. **Compute/cache/archive degradation:** Singleflight coalescing, strict `a.uri` regex + `follow_redirects=False`, SHA-256 disk cache keys including `provenance_version` and provider mode, and rate limiting (`429`) protect `/observe`, `/narrative`, and `/ask`.

---

### Task 1: Config, Schemas, Ports, and Synthetic SPHEREx MEF Generator
**Files:**
- Create: `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/schemas/*.py`, `backend/app/science/ports.py`, `backend/tests/synthetic/__init__.py`, `backend/tests/synthetic/fits_generator.py`
- Test: `backend/tests/unit/test_config_schemas.py`
- Interfaces: `Settings`, `EncodedArray`, `ObserveResponse`, `TargetPreset`, `CosmicNarratorResponse`, `EvidenceStoreResponse`, `AskResponse`, `BenchmarkRunResponse`, `CandidateRecord`, `SyntheticScenario`, `generate_synthetic_dataset()`

- [ ] **Step 1:** Write failing tests in `backend/tests/unit/test_config_schemas.py` checking `Settings` defaults (`V-01`, `V-06`), coordinate bounds (`allow_inf_nan=False`), `EncodedArray` little-endian base64 round-trip, and `generate_synthetic_dataset` HDU layout (`PRIMARY`, `IMAGE`, `FLAGS`, `VARIANCE`, `ZODI`, `EPSF`, `WCS-WAVE`) + ground truth.
- [ ] **Step 2:** Run `.venv/bin/pytest backend/tests/unit/test_config_schemas.py -v` -> verify FAIL.
- [ ] **Step 3:** Implement `config.py`, all Pydantic v2 models under `schemas/`, `science/ports.py`, and `tests/synthetic/fits_generator.py` (producing multi-visit rotated FITS cutouts with movers, variables, sloped-spectrum static stars, cosmic rays, and `FLAGS` bits 12 & 21).
- [ ] **Step 4:** Run pytest -> PASS, then commit `feat(M1): config, Pydantic v2 schemas, science ports, and synthetic FITS generator`.

---

### Task 2: Calibration, Flags, Wavelength, Coordinates & Selection (`FR-02`, `FR-04`, `FR-05`, `FR-06`, `FR-15`)
**Files:**
- Create: `backend/app/science/__init__.py`, `backend/app/science/targets.py`, `backend/app/science/coords.py`, `backend/app/science/select.py`, `backend/app/science/flags.py`, `backend/app/science/calibrate.py`, `backend/app/science/wavelength.py`
- Test: `backend/tests/unit/test_select_coords.py`, `backend/tests/unit/test_calibrate_flags_wavelength.py`
- Interfaces: `PRESET_TARGETS`, `parse_ra_dec`, `propagate_skycoord`, `select_observations`, `build_flag_summary`, `calibrate_cutout`, `compute_wavelength_at_pixels`

- [ ] **Step 1:** Write failing unit tests for: sexagesimal/decimal parsing, Barnard's Star J2016->2026 propagation (`< 1"` accuracy), visit clustering & wavelength-matched selection across 180d baseline, exact `FLAGS` mask preserving bits 12 & 21, `ZODI` subtraction + missing-extension warning, and `WCS-WAVE` wavelength on both synthetic FITS and real `backend/tests/fixtures/*.fits` (including `wise_0855_sample.fits` 451-row `EPSF`).
- [ ] **Step 2:** Run pytest -> FAIL.
- [ ] **Step 3:** Implement `targets.py`, `coords.py`, `select.py`, `flags.py`, `calibrate.py`, `wavelength.py`.
- [ ] **Step 4:** Run pytest -> PASS, then commit `feat(M2): target presets, epoch propagation, selection, flags, calibration, and WCS-WAVE`.

---

### Task 3: Alignment, Source Detection, Linking, Proper Motion & Variability (`FR-07`–`FR-11`)
**Files:**
- Create: `backend/app/science/align.py`, `backend/app/science/detect.py`, `backend/app/science/link.py`, `backend/app/science/motion.py`, `backend/app/science/variability.py`
- Test: `backend/tests/unit/test_align_detect_link.py`, `backend/tests/unit/test_motion_variability.py`
- Interfaces: `build_reference_wcs`, `align_frame`, `extract_sources`, `link_detections`, `fit_motion`, `compute_variability`

- [ ] **Step 1:** Write failing tests covering all numeric ACs: rotated static stars aligned to `<= 0.1 px` RMS; native-endian `sep` extraction at `SNR >= 20` (`<= 0.1 px` centroid error) + `contaminated` aperture flag; `0.65 px` synthetic mover detected and flagged; 50-star static field yields 0 false movers; `Dec = 60°` `cos(Dec)` test; single-visit null motion with reason; sloped-spectrum constant star NOT flagged variable; `30%` same-band change flagged variable.
- [ ] **Step 2:** Run pytest -> FAIL.
- [ ] **Step 3:** Implement `align.py`, `detect.py`, `link.py`, `motion.py`, `variability.py`.
- [ ] **Step 4:** Run pytest -> PASS, then commit `feat(M2): alignment, SEP extraction, spherical linking, weighted PM, and band-matched variability`.

---

### Task 4: Comparisons, Co-adds, Spectra, Display & Pipeline Coordinator (`FR-11`–`FR-15`, `FR-20`, `FR-21`)
**Files:**
- Create: `backend/app/science/comparisons.py`, `backend/app/science/stack.py`, `backend/app/science/spectrum.py`, `backend/app/science/display.py`, `backend/app/science/pipeline.py`
- Test: `backend/tests/unit/test_comparisons_stack_spectrum_display.py`, `backend/tests/integration/test_observe_pipeline.py`
- Interfaces: `build_comparisons`, `coadd_by_detector_visit`, `extract_spectrum`, `render_wiseview`, `encode_array`/`decode_array`, `ObservePipeline.run`

- [ ] **Step 1:** Write failing tests: mover dipole in difference image, omitted mismatched-band difference with reason, `√N` SNR improvement within 15% on N-frame co-add, wavelength-sorted spectrum with non-simultaneity note, hash-stable `AsinhStretch` display, and full end-to-end `ObservePipeline` on synthetic mover+variable dataset with mocked archive ports.
- [ ] **Step 2:** Run pytest -> FAIL.
- [ ] **Step 3:** Implement `comparisons.py`, `stack.py`, `spectrum.py`, `display.py`, `pipeline.py`.
- [ ] **Step 4:** Run pytest -> PASS, then commit `feat(M2): comparisons, co-adds, spectra, WiseView display, and ObservePipeline`.

---

### Task 5: Archive & Multi-Agency Catalog Adapters (`FR-01`, `FR-03`, `FR-16`–`FR-18`)
**Files:**
- Create: `backend/app/archive/__init__.py`, `backend/app/archive/http_client.py`, `backend/app/archive/irsa.py`, `backend/app/archive/gaia.py`, `backend/app/archive/wise.py`, `backend/app/archive/simbad.py`, `backend/app/archive/vizier.py`, `backend/app/archive/ned.py`, `backend/app/archive/cadc.py`, `backend/app/archive/horizons.py`, `backend/app/archive/ads.py`
- Test: `backend/tests/unit/test_archive_irsa.py`, `backend/tests/unit/test_archive_catalogs.py`, `backend/tests/live/test_live_archives.py`

- [ ] **Step 1:** Write failing tests (mocked HTTP transport) for: IRSA TAP search + SIA fallback, cutout concurrency/retries/0-download cache hit/single-frame skip/all-fail error, strict `a.uri` SSRF path validation, Gaia DR3 truncation guard & three-valued dropout (`has_counterpart`/`no_counterpart`/`unknown`), SIMBAD Harvard mirror failover on 404, AllWISE, VizieR, NED, CADC NEOSSat, Horizons ephemeris check, and ADS `not_configured` fallback.
- [ ] **Step 2:** Run pytest -> FAIL.
- [ ] **Step 3:** Implement all `archive/*.py` adapters with bounded timeouts, retries, and normalized schemas.
- [ ] **Step 4:** Run pytest -> PASS, then commit `feat(M3): IRSA SPHEREx and multi-agency archive adapters with mirror failover`.

---

### Task 6: CacheStore, PostgreSQL + pgvector Store & Alembic Migrations (`FR-22`, `FR-23`)
**Files:**
- Create: `backend/alembic.ini`, `backend/app/store/__init__.py`, `backend/app/store/cache.py`, `backend/app/store/db.py`, `backend/app/store/models.py`, `backend/app/store/migrations/env.py`, `backend/app/store/migrations/script.py.mako`, `backend/app/store/migrations/versions/0001_initial_schema.py`
- Test: `backend/tests/unit/test_cache_db.py`

- [ ] **Step 1:** Write failing tests for: Redis-absent atomic disk fallback (`served_from="cache"`), pipeline-version cache invalidation, deterministic `observation_id`, LRU disk pruning, local SQLite/in-memory lexical document fallback when Postgres absent, and `DatabaseStore` graceful `unavailable` mode.
- [ ] **Step 2:** Run pytest -> FAIL.
- [ ] **Step 3:** Implement `cache.py`, `db.py`, `models.py`, and reversible Alembic migration `0001_initial_schema.py`.
- [ ] **Step 4:** Run pytest -> PASS, then commit `feat(M3): Redis+disk CacheStore, SQLAlchemy+pgvector models, and Alembic migration`.

---

### Task 7: Evidence Store, Claim Validator, LangGraph Cosmic Narrator & Ask This Patch (`FR-26`–`FR-33`)
**Files:**
- Create: `backend/app/narrator/__init__.py`, `backend/app/narrator/llm.py`, `backend/app/narrator/evidence.py`, `backend/app/narrator/validator.py`, `backend/app/narrator/templates.py`, `backend/app/narrator/nodes/*.py`, `backend/app/narrator/graph.py`, `backend/app/narrator/ask.py`
- Test: `backend/tests/unit/test_validator.py`, `backend/tests/unit/test_narrator_graph.py`, `backend/tests/unit/test_ask.py`

- [ ] **Step 1:** Write failing tests for: `EvidenceBuilder` `ev_*` stability; `ClaimValidator` rejecting **14 adversarial drafts** (invented DOI, wrong marker ID, altered number in `quoted_values`, altered unindexed number in prose, upgraded `"Confirmed Catalog Object"` badge without catalog match, `"Planet Nine"`/`"Planet 9"`/`"ninth planet"`/`"Planet X"`/`"confirmed discovery"`, missing citation, fabricated URL, wrong chapter count, etc.); bounded retry -> `partial` -> `template` fallback; 5-node LangGraph run with `FakeLlmProvider`; and `AskThisPatchService` deterministic `"fastest"`/`"brightest"` ranking, out-of-scope refusal, and prompt-injection neutralization.
- [ ] **Step 2:** Run pytest -> FAIL.
- [ ] **Step 3:** Implement `llm.py`, `evidence.py`, `validator.py`, `templates.py`, `nodes/*`, `graph.py`, `ask.py`.
- [ ] **Step 4:** Run pytest -> PASS, then commit `feat(M4): EvidenceBuilder, ClaimValidator, 5-node LangGraph Narrator, and Ask This Patch`.

---

### Task 8: FastAPI Routers, Rate Limiting, Jobs (`precache`, `ingest_docs`, `run_benchmarks`) & Contract Tests (`FR-19`–`FR-25`)
**Files:**
- Create: `backend/app/api/__init__.py`, `backend/app/api/deps.py`, `backend/app/api/health.py`, `backend/app/api/targets.py`, `backend/app/api/observe.py`, `backend/app/api/narrative.py`, `backend/app/api/benchmarks.py`, `backend/app/api/candidates.py`, `backend/app/main.py`, `backend/app/jobs/*.py`, `backend/docs/API.md`
- Test: `backend/tests/unit/test_rate_limit.py`, `backend/tests/integration/test_api_endpoints.py`, `backend/tests/integration/test_jobs.py`, `backend/tests/contract/test_openapi_contract.py`

- [ ] **Step 1:** Write failing integration & contract tests: all endpoints under `/api/v1`, uniform error shape `{error:{code,message,details}}`, `422` invalid RA/Dec/FOV, `404` no coverage, `502` all cutouts failed, `< 2 MB` compressed 12-frame `0.08°` response, narrative decoupled from 10s-delayed fake LLM, `< 200 ms` p95 over 50 warm-cache preset requests, `429` rate limiting, candidate create + duplicate-fingerprint vote handling, `precache` / `ingest_docs` / `run_benchmarks` jobs, and OpenAPI schema agreement with `docs/API.md`.
- [ ] **Step 2:** Run pytest -> FAIL.
- [ ] **Step 3:** Implement `deps.py`, all routers, `main.py`, `jobs/*`, and generate `backend/docs/API.md`.
- [ ] **Step 4:** Run full `make test && make coverage && make lint && make typecheck` -> PASS, then commit `feat(M5-M7): FastAPI routers, rate limiter, jobs, and contract tests`.

---

### Task 9: Live 5-Target Run (when reachable), Final Reviews (`@deep`), and `FINAL_REPORT.md` (`M8`)
**Files:**
- Create: `FINAL_REPORT.md`
- Run: `@pytest.mark.live` benchmark probe on the 5 mandatory targets + negative control, `make coverage` (`>= 85%` on `science/` + `validator.py`), `make lint`, `make typecheck`, `reviewer` + `security-reviewer` passes (`@deep` medium hydrogen), update vault run (`vault action=review` + `action=done`).

- [ ] **Step 1:** Execute live benchmark run (`run_benchmarks.py`) if network/IRSA reachable and save results honestly (marking `inconclusive` with exact reason if insufficient/saturated).
- [ ] **Step 2:** Run `make test && make coverage && make lint && make typecheck`.
- [ ] **Step 3:** Dispatch fresh `@deep` `reviewer` and `security-reviewer` subagents; fix any blockers/concerns.
- [ ] **Step 4:** Write `FINAL_REPORT.md` (exact 9 sections of B9), commit & push to private GitHub repo, and update AI Vault status.

---

## Self-Review

- **Spec coverage:** Every requirement `FR-01`–`FR-33`, `NFR-01`–`NFR-10`, and `V-01`–`V-12` maps explicitly to Tasks 1–9.
- **Type & name consistency:** Reconciled `ObservePipeline`, `stack.py`, `EvidenceStoreResponse`, `NarrativeJobResponse`, `sep>=1.4`, `sqlalchemy[asyncio]`, and `Protocol` ports across `design_draft.md` and all tasks.
- **No placeholders:** Every task specifies exact files, signatures/interfaces, tests, and commit milestones.
