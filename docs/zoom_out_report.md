# Stage 5: Initial Zoom-Out & Inventive Catalyst Report (`egm-zoom-out` + `egm-inventive-catalyst`)

**Target:** `docs/design_draft.md` (`1-150`)

## Zoom-Out Findings (`egm-zoom-out`)

- **Blocker — Contradictory layer placement and `ObserveResponse` persistence ownership (`lines 44, 54, 62, 76, 102-105, 114, 116, 126, 129`):**
  `archive/irsa.py` overlaps `science/select.py`, `store/cache.py`, and `science/calibrate.py`; `archive/gaia.py` and `archive/simbad.py` overlap `science/coords.py` and `science/link.py`; `science/display.py` owns HTTP base64 wire encoding; and `CacheStore` is nested inside `ObserveOrchestrator` rather than injected at the API/store seam.
- **Major — Triple-layer persistence & hybrid RAG complexity (`lines 25, 44, 48, 69, 128-132, 146`):**
  Need clean offline/non-DB parity (`RetrievalStore` fallback) and strict separation so Postgres/Redis absence never degrades core flows.
- **Major — Custom `httpx` TAP/VOTable parsing vs `astroquery`/`pyvo` (`lines 42, 100-109`):**
  Reuse `astroquery` / `pyvo` wrapped in `asyncio.to_thread` where appropriate, keeping `httpx` for concurrent cutout downloads and REST APIs (ADS, Horizons, TAP direct).
- **Major — Over-engineered LangGraph & duplicate LLM abstraction (`lines 16, 47, 134-140`):**
  Keep the 5-node LangGraph graph required by FR-27 cleanly thin without duplicating LangChain interfaces, and short-circuit `template` mode deterministically.
- **Major — Reinventing `astropy`/`reproject`/`photutils` utilities (`lines 58, 60, 68, 113, 118-120, 125-126`):**
  Use `SkyCoord`, `search_around_sky`, `reproject_interp(..., return_footprint=True)`, `PercentileInterval` + `ImageNormalize`, and `photutils.aperture`.
- **Major — Altitude drops in `lines 1-82`:**
  Keep `FeatureRange` (`1-82`) at component/invariant altitude; move filenames, SQL joins, magic numbers, and bit literals into `Detailed Implementation Plan`.
- **Nit — `NarrativeJobResponse` vs inline async semantics; dangling relative links to `VERIFICATION.md` and `DECISIONS.md`.**

## Inventive Catalyst TRIZ Findings (`egm-inventive-catalyst`)

- **Major 1 — Measurement vs Visualization Coupling (`reproject_interp` variance & undersampled PSF):**
  Measure per-source `WCS-WAVE` wavelength in native frame coordinates (via inverse WCS from aligned coordinates) and propagate resampling variance properly ($\sum w_i^2 V_i$ / analytical weighting + undersampling error floor) rather than naive bilinear variance interpolation.
- **Major 2 — Intra-FOV LVF Gradient vs Frame-Level Binning (`0.5°` FOV & rotations):**
  Evaluate `WCS-WAVE` per source `(x, y)` in each native frame before `variability.py` grouping; mask high-$|\Delta\lambda|$ pixels in `comparisons.py`.
- **Major 3 — Synchronous Coupling of 7 Catalogs in `/observe`:**
  Reorder/race SIMBAD/VizieR mirrors (`simbad.harvard.edu` first or concurrent) and run catalog enrichment concurrently with bounded timeout so slow third-party catalogs never block core SPHEREx frames.
- **Major 4 — Thread-Pool Contention & Cache-Key Rigidity:**
  Add singleflight request coalescing keyed by quantized patch + `provenance_version`; isolate CPU-bound science into a bounded executor; separate `cutout_key` (`provenance_version`) from `science_key` (`pipeline_version`).
- **Major 5 — Inline Base64 Payload Scaling at `0.5°` FOV:**
  Cap/adapt inline `VARIANCE` inclusion or frame cap (`MAX_FRAMES`) so `0.08°` 12-frame responses stay `< 2 MB` compressed and `0.5°` remains bounded.
- **Major 6 — `local_rag` Offline Fallback Coupled to Optional PostgreSQL:**
  Provide an in-memory / SQLite FTS5 lexical fallback behind `RetrievalStore` when PostgreSQL is `unavailable`.
- **Major 7 — Generative Numeric Quoting & Cache-Key Blindness in `narrator/`:**
  Key narrative cache by `(observation_id, pipeline_version, llm_provider, llm_model, ads_configured)` and avoid caching transient fallback failures at full TTL.
- **Nit 8 — Multi-pass `link.py` Matching for High-PM Crowded Fields:**
  Progressive matching (tight stationary lock + Gaia PM prior, then tracklet association for unmatched movers).
