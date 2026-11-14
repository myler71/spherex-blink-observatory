# Stage 9: Implementation Readiness & Codebase Details Report

**Target:** `docs/design_draft.md` (`83-150`)

## Implementation Readiness Findings (`egm-implementation-readiness`)

- **Blockers 1–10:**
  1. Add ordered implementation phases, checkpoints, and per-file actionable steps.
  2. Specify complete HTTP API endpoint table (methods, paths under `/api/v1`, query/body schemas, status codes, rate-limit window/headers).
  3. Define field-level Pydantic v2 schemas for all `schemas/*.py` models.
  4. Define SQL DDL / ORM columns, PK/FK constraints, GIN & pgvector indexes, `CREATE EXTENSION IF NOT EXISTS vector`, and reversible Alembic migrations.
  5. Enumerate all 5 mandatory targets + `Gaia DR3 720517945437337600` negative control with exact coords, PMs, tolerances, and citations.
  6. Specify exact science formulas, thresholds, parameters, and edge-case fallbacks across `select.py`, `calibrate.py`, `align.py`, `detect.py`, `link.py`, `motion.py`, `variability.py`, `comparisons.py`, `stack.py`, `spectrum.py`, `display.py`.
  7. Provide full `Settings` env-var table and canonical `error.code` catalog.
  8. Fix `HorizonsAdapter` (query curated bright/known moving SSO target IDs or SkyBoT/MPC cone check with Horizons ephemeris verification rather than blind Horizons cone search) and specify all archive ADQL/REST templates.
  9. Specify `ClaimValidator` rules, `GraphState`, hybrid retrieval RRF fusion + offline SQLite/in-memory fallback, and `AskThisPatchService` intent/ranking rules.
  10. Enumerate exact test file paths (`backend/tests/unit/*`, `integration/*`, `contract/*`, `live/*`) and `fits_generator.py` ground-truth contract.
- **Majors 1–6:** Specify `ObservePipeline` DAG & failure isolation, `CacheStore` key/TTL/atomic write contract, `coords.py`/`flags.py`/`wavelength.py` edge contracts, background job CLIs, middleware/lifespan options, and `LlmProvider` protocol.

## Codebase Details Findings (`egm-codebase-details`)

- **Blocker 1:** `sqlalchemy.ext.asyncio` requires `greenlet` (`sqlalchemy[asyncio]>=2.0`).
- **Blocker 2:** `sep-pjw` is deprecated in favor of `sep>=1.4`; FITS `IMAGE` arrays are big-endian `>f4` and MUST be converted via `np.ascontiguousarray(arr, dtype=np.float32)` before calling `sep`.
- **Blocker 3:** Add `backend/alembic.ini`, `script.py.mako`, `CREATE EXTENSION IF NOT EXISTS vector`, and full column/index DDL.
- **Blocker 4:** Enumerate all test files, `__init__.py` files, and doc files (`API.md`, `SCIENCE.md`, etc.).
- **Major 5–8:** Map exact roles for `photutils`, `astroquery`, and `pyvo` (or remove unused ones); add `SPHEREX_REJECT_FLAG_BITS` to `.env.example`; fix `AsinhStretch(a=...)` float parameter and `SkyCoord.apply_space_motion()` missing-PM/parallax guards; reconcile seam `Protocol` ports; handle `reproject_interp` `NaN` pre-zeroing/float32 output; parse `EPSF` row counts dynamically (verified `451` rows in `wise_0855_sample.fits` vs `441` in `barnards_star_sample.fits`).
- **Nit 9–11:** Suppress `astropy.wcs` SIP INFO log around `WCS(..., key="W")` and unpack `[wl, bw]`; clarify `retriever.py` node count; ensure `tap_summary.json` is committed in fixtures.
