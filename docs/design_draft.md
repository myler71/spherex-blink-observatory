# SPHEREx Blink Observatory — Backend & AI Architecture Design

* **Author:** Marwan Ammar (autonomous session)
* **Date:** 2026-11-14
* **Predecessor Brief:** [concepts_brief.md](./concepts_brief.md)
* **Verification & Decisions:** [VERIFICATION.md](../backend/docs/VERIFICATION.md), [DECISIONS.md](../backend/docs/DECISIONS.md)

## The Problem

Astronomers and citizen scientists inspecting SPHEREx (Spectro-Photometer for the History of the Universe, Epoch of Reionization and Ices Explorer) 0.75–5.0 µm near-infrared time-series images need to spot sub-pixel moving objects (brown dwarfs, high-proper-motion stars, minor planets) and variable stars without falling into Linear Variable Filter (LVF) spectral-slope traps, archive latency timeouts, or LLM hallucinations. Earlier hackathon draft code suffered from 24 documented scientific and engineering defects, including linear `y/2040` wavelength estimation, cross-wavelength variability mixing, unpropagated J2000 target coordinates, unweighted proper-motion fits ignoring `cos(Dec)`, `FLAGS > 0` masking valid source pixels, oversized JSON pixel lists, synchronous LLM calls inside `/observe`, and an ungrounded Claim Validator.

## Overview

The backend implements a strict "two brains" architecture inside `backend/app/`:

1. **Deterministic Astrophysics Brain (`science/`, `archive/`, `store/`):** Has zero import paths to `narrator/` or any LLM library. Fetches SPHEREx Data Release 1 (DR1) and Quick Release 3 (QR3) Multi-Extension FITS (MEF) cutouts from NASA/IPAC IRSA, calibrates frames using zodiacal background (`ZODI`) subtraction and verified quality bitmasks (`FLAGS`), computes per-pixel and per-source wavelengths via `WCS-WAVE`, aligns frames onto a north-up tangent-plane (`TAN`) grid, extracts sub-pixel centroids and fluxes, links multi-epoch detections on the celestial sphere, fits inverse-variance weighted proper motion and wavelength-matched variability, builds co-adds and on-the-fly spectra, and enriches detections with Gaia DR3, AllWISE, SIMBAD, VizieR, NED, CADC NEOSSat, and JPL Horizons.
2. **Citation-Validated Narrative Brain (`narrator/`):** Consumes only a compact, evidence-indexed JSON bundle produced by the deterministic brain. A 5-node LangGraph workflow (`patch_analyzer` -> `research_planner` -> parallel `retriever` [local hybrid lexical/vector + NASA ADS] -> `story_generator` -> deterministic `claim_validator` with up to 2 retries) produces a 5-chapter `CosmicNarratorResponse` and powers patch-scoped Q&A ("Ask This Patch"), falling back to a deterministic evidence-only template when no LLM key is configured or validation exhausts retries.
3. **Benchmarks & Citizen Review (`jobs/`, `api/`):** Evaluates the 5 mandatory targets (Barnard's Star, WISE 0855, Epsilon Indi B, RW Aurigae, R Draconis) plus a Gaia DR3 static negative control (`Gaia DR3 720517945437337600`) against catalog references, pre-warms caches for sub-200 ms p95 demo latency, and supports candidate flagging and community voting (`Real Motion`, `Variable Star`, `Artifact`).

## Goals vs. Non-Goals

### Goals
- Serve `GET /api/v1/observe` for arbitrary sky coordinates `(ra, dec, fov)` using live IRSA DR1/QR3 cutouts, and serve pre-warmed mandatory targets from cache in `< 200 ms` p95.
- Guarantee scientific correctness: true `WCS-WAVE` wavelengths (`key="W"`, `sip=None`) evaluated at native pixel positions, band-matched light curves/variability/difference images, inverse-variance weighted proper motion in `(\mu_{\alpha*}, \mu_\delta)` with uncertainties, and verified `FLAGS` handling preserving `FULLSAMPLE` (bit 12) and `SOURCE` (bit 21).
- Transport aligned `float32` frames and `uint8` quality masks as compact little-endian base64 arrays under HTTP gzip (`< 2 MB` for 12 frames at `0.08°` FOV).
- Decouple `/api/v1/observe` completely from LLM execution and guarantee zero hallucinated citations, numbers, or banned discovery claims ("Planet Nine", "Planet X", "confirmed discovery") via deterministic `ClaimValidator` rules.
- Degrade cleanly when network, PostgreSQL+pgvector, Redis, NASA ADS token, or LLM API keys are absent.

### Non-Goals
- Frontend UI, 3D landing page, visual assets, cloud deployment, and pitch materials.
- Claiming discovery of Planet Nine / Planet X or replacing deterministic measurements with LLM inference.

## Technical Plan

### Deep-Module Architecture & Seams

Complexity is concentrated into deep modules behind narrow `Protocol` seams (`science/ports.py`), keeping `archive/` as pure I/O adapters, `science/` free of HTTP wire encoding and LLM dependencies, and `store/cache.py` injected at the API/orchestrator boundary:

```text
HTTP Routers & Wire Encoding (backend/app/api/)
  │  (validates inputs, rate-limits, encodes base64 arrays, dispatches background jobs)
  ├──► CacheStore (backend/app/store/cache.py — Redis + atomic disk fallback)
  ├──► DatabaseStore (backend/app/store/db.py — Postgres + pgvector/tsvector; optional)
  │
  ├──► ObservePipeline (backend/app/science/pipeline.py)
  │       ├── Port: ArchivePort ◄── IrsaArchiveAdapter (backend/app/archive/irsa.py)
  │       ├── Port: CatalogPorts ◄── Gaia, AllWISE, SIMBAD, VizieR, NED, CADC, Horizons
  │       └── Deep Science Modules (select, coords, flags, calibrate, wavelength,
  │                                 align, detect, link, motion, variability,
  │                                 comparisons, stack, spectrum, display)
  │
  └──► NarratorGraph & AskThisPatchService (backend/app/narrator/)
          ├── EvidenceBuilder (evidence.py) + RetrievalStore (retriever.py + db.py + ads.py)
          ├── LlmProvider (llm.py — template | fake | openai_compatible)
          └── ClaimValidator (validator.py — deterministic claim/number/badge/policy gate)
```

### Data Flow

1. **Coordinate Normalization, Propagation & Coalescing:** Requests accept decimal degrees or sexagesimal strings (`allow_inf_nan=False`, pole guard `|Dec| <= 89.9°` for north-up tangent projection). Presets or `propagate=true` requests propagate coordinates to observation epochs via `SkyCoord.apply_space_motion()` (using preset astrometry, explicit query PM params, or pre-fetch Gaia DR3 lookup). Concurrent identical cold `/observe` requests coalesce via singleflight keyed by quantized `(ra, dec, fov, params)` and `pipeline_version`.
2. **Archive Search & Cutout Retrieval:** `IrsaArchiveAdapter` queries `spherex.artifact JOIN spherex.plane JOIN spherex.observation` across configured releases (`spherex_dr1`, `spherex_dr1_deep`, `spherex_qr3`, `spherex_qr3_deep`) with SIA fallback. `select.py` deduplicates exposures, clusters visits by time gaps, and picks a bounded (`<= max_frames`) baseline-maximizing, wavelength-matched subset. Raw cutouts download concurrently (strict path validation, `follow_redirects=False`, bounded retries) and cache on disk by `(obs_id, quantized_patch, provenance_version)`.
3. **Deterministic Calibration, Alignment, Extraction & Measurement:**
   - `calibrate.py` + `flags.py` read MEF extensions dynamically (handling `DR1`/`QR3` `EPSF` of any grid size and legacy `< 7.0` `PSF`), subtract `ZODI` when present, cast arrays to native-endian `float32`, and mask only verified defect bits (`V-06`) plus non-finite pixels.
   - `align.py` pre-zeros masked pixels before `reproject_interp` onto a north-up `TAN` grid at native `~6.16"/px` scale, computes analytical resampling variance with an undersampling error floor, and propagates a bit-packed `uint8` mask (`OUT_OF_BOUNDS` vs `REJECTED` vs `SOURCE`/`INFO`).
   - `detect.py` runs `sep.Background` + `sep.extract` (plus `photutils.aperture` forced/aperture photometry checks), tagging apertures overlapping bad pixels as `contaminated`.
   - `wavelength.py` evaluates `WCS(header, fobj=hdul, key="W")` (`sip=None`) at each source's exact native cutout pixel (mapped via inverse spatial WCS from aligned `(x, y)`), preventing intra-FOV LVF spectral gradients from causing false variability on rotated/wide fields.
   - `link.py` performs progressive spherical sky matching (`SkyCoord.search_around_sky` / `cKDTree`), `motion.py` fits inverse-variance weighted $(\mu_{\alpha*}, \mu_\delta)$ (and 5-parameter parallax only when baseline $\ge 180$ days and design-matrix condition number passes), and `variability.py` computes per-wavelength-bin weighted mean flux and reduced $\chi^2_\nu$.
   - `comparisons.py`, `stack.py`, `spectrum.py`, and `display.py` produce wavelength-gated (`|\Delta\lambda| \le \epsilon_\lambda`) difference/addition pairs, frame-minus-median flipbook cubes, per-detector per-visit inverse-variance co-adds, sorted on-the-fly spectra, and WiseView `AsinhStretch` + `PercentileInterval` previews.
4. **Decoupled Narrator, Retrieval & Validation:** `GET /api/v1/observe/{observation_id}/narrative` loads the stored `ObserveResponse` from `CacheStore`/DB, builds deterministic `ev_*` evidence records, checks the narrative cache keyed by `(observation_id, pipeline_version, llm_provider, llm_model, ads_configured)`, and returns `pending`/`ready`/`failed` (`NarrativeJobResponse`) while running the 5-node LangGraph workflow off the event loop. `retriever.py` runs PostgreSQL `tsvector` + `pgvector` hybrid RRF (falling back to an in-memory/SQLite FTS5 lexical corpus when Postgres is absent) in parallel with NASA ADS. `ClaimValidator` scans both structured `quoted_values` and full prose numbers against `EvidenceItem` payloads, verifies `visual_marker_id`s, badge preconditions, server-built URLs, and banned discovery/injection patterns.

## Alternatives Considered

1. **IRSA TAP (`spherex.artifact` + `spherex.plane` + `spherex.observation`) vs. SIA-only:** Rejected SIA-only because IRSA documentation confirms SIA lags weekly ingestions by ~1 day and lacks `provenance_version` in one query; SIA remains a fallback.
2. **Native-position `WCS-WAVE` lookup + `reproject_interp` analytical variance vs. `reproject_exact` everywhere or naive variance interpolation:** Naive variance interpolation biases $\chi^2_\nu$ downward and blurs LVF gradients at `0.5°` FOV. Pre-masking + analytical variance propagation + inverse-WCS native `WCS-WAVE` lookup preserves aligned `x, y` markers (`A13`) while eliminating LVF slope artifacts without `reproject_exact`'s runtime cost on 24 cutouts.
3. **Decoupled `GET /observe` + async/cached `GET /observe/{id}/narrative` vs. single synchronous LLM+pixel endpoint:** Rejected synchronous coupling because multi-node LangGraph/ADS execution adds 2–10s latency and would block blink rendering.
4. **Base64 little-endian `float32` inside gzipped JSON vs. separate per-frame binary endpoints:** At `0.08°` (`47x47` px), 12 frames total ~106 KB raw and `< 300 KB` gzipped in JSON, avoiding 12 extra HTTP round-trips; for `fov > 0.2°`, optional `include_variance=false` / `max_frames` keeps payloads bounded under 2 MB.
5. **5-node LangGraph with deterministic `template` short-circuit vs. pure single-shot LLM call:** Preserves FR-27's required 5-node typed workflow (parallel local+ADS retrieval + bounded validator retry) while letting `LLM_PROVIDER=template` bypass LLM latency entirely.
6. **PostgreSQL `tsvector` + `pgvector` hybrid RRF with local lexical fallback vs. standalone vector DB:** Single Postgres 16 + pgvector container satisfies relational + FTS + vector requirements while local lexical indexing preserves offline CI/no-DB parity.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| IRSA / Gaia / SIMBAD / CADC transient 404/503 or timeout | Live request stalls or fails | Per-adapter timeout (`5s`), fast failover on 4xx (no backoff on 404), exponential backoff on 5xx/429, Harvard CFA mirrors first for SIMBAD/VizieR, per-service `status` field, and synthetic/disk cache fallbacks. |
| Missing `LLM_API_KEY`, `NASA_ADS_API_TOKEN`, Redis, or PostgreSQL | Startup or narrative failure | Automatic `template` narrator, local lexical retrieval fallback, atomic disk cache fallback, and graceful DB `unavailable` status. |
| Compute/egress/disk DoS on `/observe` | Worker OOM, disk exhaustion, upstream IP ban | Per-IP rate limits on `/observe`, `/narrative`, `/ask`; `max_frames` cap (`<= 24`); singleflight coalescing; bounded threadpool; LRU disk cache pruning; strict `a.uri` path regex + `follow_redirects=False`. |
| LLM prompt injection or fabricated numbers/Planet Nine claims | Scientific misinformation | Untrusted delimiters around user questions & ADS abstracts; deterministic `ClaimValidator` checking all prose numbers, `ev_*` IDs, marker IDs, badges, server-built URLs, and expanded banned-discovery patterns. |
| Narrative cache poisoning by transient fallback | Template story masks real LLM permanently | Cache key includes `(observation_id, pipeline_version, llm_provider, llm_model, ads_configured)`; degraded error fallbacks use short TTL (`60s`) or skip caching. |

---

## Detailed Implementation Plan

### Phasing & Checkpoints

- **Phase 1 (Config, Schemas, Store & Synthetic Fixture Gen):** `config.py`, `schemas/*`, `store/*`, `tests/synthetic/fits_generator.py`. Exit: `pytest backend/tests/unit/test_schemas.py backend/tests/unit/test_cache.py` green.
- **Phase 2 (Archive Adapters & Science Pipeline):** `archive/*`, `science/*`. Exit: `pytest backend/tests/unit/test_science_*.py backend/tests/unit/test_archive_*.py` green.
- **Phase 3 (Narrator, Validator & Ask This Patch):** `narrator/*`. Exit: `pytest backend/tests/unit/test_narrator_*.py backend/tests/unit/test_validator.py` green (12+ adversarial tests).
- **Phase 4 (API Routers, Jobs, Integration & Contract Tests):** `api/*`, `jobs/*`, `main.py`, `tests/integration/*`, `tests/contract/*`. Exit: `make test && make coverage && make lint && make typecheck`.

### Complete Target File Boundary

- **Root & Infra:** `pyproject.toml`, `Makefile`, `.gitignore`, `.env.example`, `README.md`, `FINAL_REPORT.md`, `backend/Dockerfile`, `backend/docker-compose.yml`, `backend/alembic.ini`, `backend/requirements.lock.txt`
- **Docs (`backend/docs/`):** `VERIFICATION.md`, `DECISIONS.md`, `API.md`, `SCIENCE.md`, `ATTRIBUTION.md`
- **App Core (`backend/app/`):** `__init__.py`, `config.py`, `main.py`
- **Schemas (`backend/app/schemas/`):** `__init__.py`, `common.py`, `targets.py`, `observe.py`, `narrative.py`, `benchmarks.py`, `candidates.py`
- **Archive Adapters (`backend/app/archive/`):** `__init__.py`, `http_client.py`, `irsa.py`, `gaia.py`, `wise.py`, `simbad.py`, `vizier.py`, `ned.py`, `cadc.py`, `horizons.py`, `ads.py`
- **Science Engine (`backend/app/science/`):** `__init__.py`, `ports.py`, `targets.py`, `coords.py`, `select.py`, `flags.py`, `calibrate.py`, `wavelength.py`, `align.py`, `detect.py`, `link.py`, `motion.py`, `variability.py`, `comparisons.py`, `stack.py`, `spectrum.py`, `display.py`, `pipeline.py`
- **Store & Migrations (`backend/app/store/`):** `__init__.py`, `cache.py`, `db.py`, `models.py`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/0001_initial_schema.py`
- **Narrator (`backend/app/narrator/`):** `__init__.py`, `llm.py`, `evidence.py`, `validator.py`, `templates.py`, `graph.py`, `ask.py`, `nodes/__init__.py`, `nodes/analyzer.py`, `nodes/planner.py`, `nodes/retriever.py`, `nodes/generator.py`, `nodes/validate_node.py`
- **API (`backend/app/api/`):** `__init__.py`, `deps.py`, `health.py`, `targets.py`, `observe.py`, `narrative.py`, `benchmarks.py`, `candidates.py`
- **Jobs (`backend/app/jobs/`):** `__init__.py`, `precache.py`, `ingest_docs.py`, `run_benchmarks.py`
- **Tests (`backend/tests/`):**
  - `conftest.py`, `synthetic/__init__.py`, `synthetic/fits_generator.py`
  - `fixtures/`: `tap_summary.json`, `barnards_star_sample.fits`, `wise_0855_sample.fits`, `epsilon_indi_b_sample.fits`, `rw_aurigae_sample.fits`, `r_draconis_sample.fits`
  - `unit/`: `test_config_schemas.py`, `test_archive_irsa.py`, `test_archive_catalogs.py`, `test_select_coords.py`, `test_calibrate_flags_wavelength.py`, `test_align_detect_link.py`, `test_motion_variability.py`, `test_comparisons_stack_spectrum_display.py`, `test_cache_db.py`, `test_validator.py`, `test_narrator_graph.py`, `test_ask.py`, `test_rate_limit.py`
  - `integration/`: `test_observe_pipeline.py`, `test_api_endpoints.py`, `test_jobs.py`
  - `contract/`: `test_openapi_contract.py`
  - `live/`: `test_live_archives.py` (`@pytest.mark.live`)

### Key Specifications & Contracts

#### 1. Mandatory Targets + Negative Control (`backend/app/science/targets.py`)
| ID | Name | RA (deg) | Dec (deg) | Ref Epoch | `pmra` (mas/yr) | `pmdec` (mas/yr) | Parallax (mas) | Mode | Reference / Citation |
|---|---|---|---|---|---|---|---|---|---|
| `barnards_star` | Barnard's Star | 269.4485025 | 4.7394201 | J2016.0 | -801.551 | 10362.394 | 546.976 | `motion` | Gaia DR3 `4472832130942575872` |
| `wise_0855` | WISE 0855 | 133.8189083 | -7.2470480 | J2016.0 | -8123.700 | 673.200 | 439.000 | `motion` | SIMBAD `WISEA J085510.74-071442.5` (Luhman & Esplin 2016) |
| `epsilon_indi_b` | Epsilon Indi B | 331.0441466 | -56.7828442 | J2016.0 | 3981.977 | -2466.832 | 270.658 | `motion` | SIMBAD `* eps Ind B` (McCaughrean et al. 2004) |
| `rw_aurigae` | RW Aurigae | 76.9560812 | 30.4012046 | J2016.0 | 2.641 | -27.398 | 6.406 | `variability` | Gaia DR3 `156430822114424576` / SIMBAD `V* RW Aur` |
| `r_draconis` | R Draconis | 248.1673784 | 66.7550067 | J2016.0 | -20.643 | 6.149 | 1.251 | `variability` | Gaia DR3 `1648328016354496384` (`phot_variable_flag=VARIABLE`) |
| `negative_control` | Gaia DR3 720517945437337600 | 134.8458155 | 40.9946968 | J2016.0 | -1.263 | -0.863 | 0.741 | `both` | Gaia DR3 `720517945437337600` (`G=11.02`, `ruwe=0.886`, `NOT_AVAILABLE`) |

#### 2. HTTP Endpoints (`/api/v1`) & Error Catalog
- Uniform error payload: `{ "error": { "code": str, "message": str, "details": dict | list | None } }`.
- Canonical codes: `VALIDATION_ERROR` (422), `NO_COVERAGE` (404), `NOT_FOUND` (404), `UPSTREAM_CUTOUT_FAILURE` (502), `RATE_LIMIT_EXCEEDED` (429 + `Retry-After`), `DATABASE_UNAVAILABLE` (503), `INTERNAL_ERROR` (500).
- Routes:
  - `GET /api/v1/health` -> `200` (`ServiceStatus` map for `archive`, `redis`, `postgres`, `llm`, `ads`).
  - `GET /api/v1/targets` -> `200` (`TargetsResponse` with 6 presets).
  - `GET /api/v1/observe` -> `200` (`ObserveResponse`) | `404` (`NO_COVERAGE`) | `422` (`VALIDATION_ERROR`) | `429` | `502` (`UPSTREAM_CUTOUT_FAILURE`). Rate-limited (30 req/min/IP).
  - `GET /api/v1/observe/{observation_id}` -> `200` (`ObserveResponse`) | `404`.
  - `GET /api/v1/observe/{observation_id}/spectrum` (query `object_id` or `ra, dec`) -> `200` (`SpectrumResponse`) | `404`.
  - `GET /api/v1/observe/{observation_id}/narrative` -> `200` (`NarrativeJobResponse`: `status` in `pending|ready|failed`, `narrative` when `ready`) | `404` | `429`.
  - `GET /api/v1/observe/{observation_id}/evidence` -> `200` (`EvidenceStoreResponse`) | `404`.
  - `POST /api/v1/observe/{observation_id}/ask` (body `AskRequest { question }`) -> `200` (`AskResponse`) | `404` | `422` | `429`.
  - `GET /api/v1/benchmarks` -> `200` (`BenchmarkRunResponse`).
  - `GET /api/v1/candidates`, `POST /api/v1/candidates` -> `200`/`201` (`CandidatesListResponse` / `CandidateRecord`); `POST /api/v1/candidates/{candidate_id}/votes` -> `200`/`201` (`409` on duplicate fingerprint vote or upsert-by-fingerprint).

#### 3. Exact Science Equations & Pixel Transport
- **Flags (`flags.py`, `V-06`):** Cast `FLAGS` to `np.uint32`. Reject mask `bad = (flags & reject_mask) != 0` where `reject_mask = sum(1 << b for b in settings.spherex_reject_flag_bits)` (default `{0,1,2,6,9,10,11,15,17,19,25,26,27}`; NEVER includes `12: FULLSAMPLE` or `21: SOURCE`). `uint8` wire mask bit-packing: `bit 0` = `REJECTED`, `bit 1` = `OUT_OF_BOUNDS` (reprojection footprint == 0), `bit 2` = `SOURCE`, `bit 3` = `GHOST_OR_HALO` (`22,23,24,28`), `bit 4` = `DICHROIC_OR_CROSSTALK` (`7,14,20`).
- **Wavelength (`wavelength.py`, `V-05`):** Suppress `astropy.wcs` SIP INFO log, load `swcs = WCS(header=hdul["IMAGE"].header, fobj=hdul, key="W")`, set `swcs.sip = None`, call `wl, bw = swcs.pixel_to_world(x_native, y_native)`, convert to `u.micrometer` floats.
- **Alignment & Variance (`align.py`):** Pre-zero `bad | ~np.isfinite(img)` pixels, track finite weight plane `valid = (~bad & np.isfinite(img) & np.isfinite(var) & (var > 0)).astype(np.float32)`. Reproject `img`, `var`, `valid`, and `bad.astype(np.float32)` via `reproject_interp(..., return_footprint=True)` onto north-up `TAN` WCS (`|Dec| <= 89.9°`, `pixel_scale = 6.16"/px`). Output `out_bad = (footprint < 0.99) | (reproj_bad > 0.0) | ~np.isfinite(reproj_img)`. Scale variance by `1.0 / np.maximum(reproj_valid, 0.25)` plus undersampling floor `(0.02 * abs(reproj_img))**2` and clamp `> 0`.
- **Detection (`detect.py`):** Convert arrays via `np.ascontiguousarray(arr, dtype=np.float32)` (eliminating FITS big-endian `>f4` `ValueError`). Run `sep.Background(data, mask=out_bad, bw=16, bh=16, fw=3, fh=3)` (clamped to image size for small cutouts) and `sep.extract(..., thresh=detection_sigma, err=np.sqrt(var), mask=out_bad, minarea=3)`. Compute flux & flux_err via `sep.sum_circle(..., r=2.0, err=np.sqrt(var), mask=out_bad)`. Compute `centroid_err_px = np.hypot(xerr, yerr)` with floor `0.02` px (and `photutils.aperture.CircularAperture` verification helper).
- **Linking & Motion (`link.py`, `motion.py`):** Match across all frames via `SkyCoord.search_around_sky` / 3D unit-vector `cKDTree` within `match_radius_arcsec` (default `12.0"`). Fit weighted linear regression in tangent-plane offsets $(\Delta\alpha^* = (\alpha - \alpha_0)\cos\delta_0,\ \Delta\delta = \delta - \delta_0)$ vs. $(t - t_{\text{ref}})/\text{yr}$ weighted by $w_i = 1 / \sigma_{\text{pos},i}^2$. Flag `is_candidate_moving` when `pm_significance >= pm_significance_sigma` (`3.0`) and `num_visits >= 2`. Fit 5-parameter parallax only when `num_visits >= 3` and `baseline_days >= 180.0` and design-matrix condition number `< 100`.
- **Variability (`variability.py`):** Group object fluxes strictly by native-position wavelength bin (`|λ_i - λ_center| <= band_match_fraction * Δλ_i`). Compute $\bar{F}_w = \sum w_i F_i / \sum w_i$, $w_i = 1/\sigma_{F,i}^2$, $\chi^2_\nu = \frac{1}{N-1}\sum w_i (F_i - \bar{F}_w)^2$, `dof = N - 1`. Flag `is_variable` when `dof >= 1` and `reduced_chi2 >= variability_reduced_chi2` (`6.0`).
- **Base64 Wire Encoding (`api/` + `display.py`):** Little-endian `<f4` and `<u1` bytes base64-encoded (`EncodedArray`). `display.py` uses `PercentileInterval` + `AsinhStretch(a=linear)` (`linear` float in `[0.001, 1.0]`, default `0.15`).

#### 4. Database Schema (`store/models.py` & `migrations/versions/0001_initial_schema.py`)
`upgrade()` runs `CREATE EXTENSION IF NOT EXISTS vector;` then creates tables:
- `sky_patches(patch_id PK UUID, target_name, ra_deg, dec_deg, fov_deg, constellation, pipeline_version, pipeline_payload JSONB, created_at)` + idx `(ra_deg, dec_deg)`
- `observations(observation_id PK str, patch_id FK -> sky_patches ON DELETE CASCADE, query_hash UNIQUE str, payload_json JSONB, created_at)`
- `detected_objects(id PK str, observation_id FK -> observations ON DELETE CASCADE, name, ra_deg, dec_deg, pm_total_mas_yr, is_moving bool, is_variable bool, gaia_status str, payload JSONB)`
- `scientific_documents(doc_id PK str, title, bibcode_or_doi, source_url, object_identifiers TEXT[], topic_category, chunk_text, tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', coalesce(title,'') || ' ' || chunk_text)) STORED, embedding VECTOR(384))` + GIN(`tsv`), GIN(`object_identifiers`), HNSW(`embedding vector_cosine_ops`)
- `narratives(cache_key PK str, observation_id, pipeline_version, provider_mode, status, payload JSONB, created_at)`
- `benchmarks(run_id PK str, created_at, summary JSONB)`
- `candidates(candidate_id PK str, observation_id, object_id, ra_deg, dec_deg, reason, created_at)`
- `candidate_votes(vote_id PK str, candidate_id FK -> candidates ON DELETE CASCADE, client_fingerprint, vote_label, created_at, UNIQUE(candidate_id, client_fingerprint))`

#### 5. Claim Validator & Narrator Rules (`narrator/validator.py`)
- Exact 5 chapters in order: `(1) Where are we looking?`, `(2) Who lives here?`, `(3) A universe in motion.`, `(4) What does SPHEREx see?`, `(5) The science behind this region.`
- Rejects any claim if: cited `evidence_id` missing from run's `EvidenceStoreResponse`; non-null `visual_marker_id` missing from `ObserveResponse.detected_objects`; any `quoted_values` entry OR numeric literal in `statement` fails to match its cited `EvidenceItem` within `max(0.05 * |v|, 3 * sigma, 0.01)`; `"Confirmed Catalog Object"` badge lacks a catalog `EvidenceItem` linked to that detection; any banned discovery phrase (`planet nine`, `planet 9`, `planet x`, `ninth planet`, `confirmed discovery`, `first detection`, `discovered a new planet`) appears; URL differs from server-built evidence URL.
- Bounded retry (max 2 attempts). On retry exhaustion: strip invalid claims (`validation.status = "partial"`), or if zero valid claims remain, return `templates.py` deterministic narrative (`generator = "template"`).
