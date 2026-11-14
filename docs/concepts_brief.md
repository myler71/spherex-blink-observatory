# SPHEREx Blink Observatory — Concepts Brief (EGM Brainstorm)

* **Author:** Marwan Ammar (autonomous session per B0)
* **Date:** 2026-11-14

## Overview

SPHEREx Blink Observatory is a public-facing FastAPI backend and citation-validated AI explanation engine for NASA Space Apps 2026 ("Planet X and SPHEREx"). Given any sky coordinate (RA, Dec) and field of view, it retrieves multi-epoch SPHEREx Level-2 Spectral Image cutouts from NASA/IPAC IRSA, aligns and calibrates them onto a common tangent-plane grid, measures sub-pixel proper motion and wavelength-matched variability deterministically, enriches detections with external astronomical catalogs (Gaia DR3, AllWISE, SIMBAD, VizieR, NED, CADC NEOSSat, JPL Horizons), and generates a five-chapter, reference-checked interactive story ("Cosmic Narrator") plus patch-scoped Q&A ("Ask This Patch").

## Analysis

### Contradictions Resolved (TRIZ & Codebase Design)

1. **Speed vs. Archive Latency & Cutout Volume**: Downloading dozens of 70 MB full-detector MEFs synchronously inside `/observe` guarantees timeouts and blocks the FastAPI event loop. Resolution: query `spherex.artifact JOIN spherex.plane JOIN spherex.observation` via IRSA TAP for exact overlapping frames, select a maximal-baseline wavelength-matched subset across visits, fetch spatial cutouts (`?center=...&size=...`, ~3.9 MB MEF), cache raw FITS bytes on disk + processed payloads in Redis/disk, run blocking Astropy/SEP work in a thread pool, and decouple `/observe` from `/narrative` so pixel delivery never waits for LLM latency.
2. **LVF Wavelength Dispersion vs. Time-Series Variability**: SPHEREx's Linear Variable Filters mean a star's wavelength depends on detector pixel position. Comparing flux across arbitrary epochs mixes spectral slope with temporal variability. Resolution: compute true per-pixel central wavelength and bandwidth from the `WCS-WAVE` extension (`WCS(..., key="W")` with `sip = None`) and bin observations by wavelength tolerance before computing reduced $\chi^2$, light curves, or difference/addition pairs.
3. **LLM Richness vs. Scientific Hallucination**: An LLM reading FITS images or inventing coordinates/DOIs produces false discovery claims ("Planet Nine found"). Resolution: strict "two brains" separation — the `science/` package has zero LLM imports; the `narrator/` LangGraph workflow receives only a compact, evidence-indexed JSON summary and passes every claim through a deterministic `ClaimValidator` that verifies `evidence_id` existence, `visual_marker_id` existence, quoted numeric values within tolerance, badge consistency, and banned discovery phrasing, falling back to a deterministic evidence-only template if keys are absent or retries fail.
4. **Offline / Uncredentialed Execution vs. Full Multi-Agency Stack**: External archives, PostgreSQL+pgvector, Redis, NASA ADS, and LLM APIs may be unavailable in local CI or uncredentialed environments. Resolution: deep-module seam adapters (`ArchiveAdapter`, `CatalogAdapter`, `StorageBackend`, `LlmProvider`) with graceful fallbacks (`unavailable` status, disk cache, deterministic template narrator, synthetic FITS fixture generator) so every P0 test runs offline while live archives work identically when reachable.

## Goals vs. Non-Goals

* **In-Scope Goals:** Live SPHEREx archive search and cutout pipeline (DR1 + QR3, fallback QR2); deterministic calibration, WCS alignment, SEP source extraction, multi-epoch linking, inverse-variance weighted proper motion, wavelength-matched variability, difference/addition/flipbook images, per-detector co-adds, on-the-fly spectra, WiseView-style display products; external catalog overlays; efficient base64 float32 compressed pixel transport; Redis+disk cache and PostgreSQL+pgvector persistence with Alembic migrations; pre-cacher, 5-target + negative-control benchmarks, and Citizen Candidates API; decoupled LangGraph Cosmic Narrator + Claim Validator + Ask This Patch; Docker Compose + comprehensive test suite (>=85% coverage on `science/` and `narrator/validator.py`).
* **Out-of-Scope Non-Goals:** Frontend UI, 3D landing page, visual asset generation, cloud deployment, pitch deck/video, and claiming discovery of Planet Nine or Planet X.

## Alternatives Weighed

* **IRSA TAP (`spherex.artifact` + `spherex.plane` + `spherex.observation`) vs. SIA-only**: Rejected SIA-only because IRSA documentation states SIA lags weekly ingestions by ~1 day whereas TAP reflects newly ingested QR3/DR1 products immediately and exposes `provenance_version` and `collection` directly in one join; SIA remains supported as a secondary fallback adapter.
* **True `WCS-WAVE` lookup (`key="W"`, `sip=None`) vs. linear `y/2040` or HiPS-only cubes**: Rejected `y/2040` (scientifically wrong for curved LVF contours and cutouts) and HiPS-only (loses per-visit epoch timestamps, `FLAGS`, `VARIANCE`, and sub-pixel motion between individual exposures).
* **Base64 little-endian `float32` + gzip HTTP compression vs. JSON float lists**: Rejected JSON float lists (10x+ payload bloat and slow serialization violating FR-20's `<2 MB` budget for 12 frames).
* **Decoupled `/observe` + `/narrative` endpoints vs. single synchronous endpoint**: Rejected single synchronous endpoint so pixel blinking renders immediately without waiting on multi-node LangGraph/LLM execution.

## Key Decisions & Staging for Next Steps

1. Deep modules with clean seams (`backend/app/archive/`, `backend/app/science/`, `backend/app/store/`, `backend/app/narrator/`) — no LLM imports anywhere in `science/`.
2. `FLAGS` rejection excludes informational bits `12` (`FULLSAMPLE`) and `21` (`SOURCE`), rejecting only verified defect bits `{0, 1, 2, 6, 9, 10, 11, 15, 17, 19, 25, 26, 27}` by default via config.
3. Negative control star selected from Gaia DR3: `Gaia DR3 720517945437337600` (`ra=134.84581545`, `dec=40.99469683`, `G=11.02`, `|pm|<1.6 mas/yr`, `ruwe=0.886`, `phot_variable_flag='NOT_AVAILABLE'`).
4. Proceed directly to `design_draft.md`, 5-stage Goldfish review (`egm-review` uninterrupted), Elephant resolution, and `docs/superpowers/plans/2026-11-14-spherex-backend.md`.
