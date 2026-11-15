# Changelog

## v0.5.0 — ORVYX SPHEREx 2D Blink Observatory & Full-Stack Deployment (2026-11-15)

### Repository & Documentation Architecture
- Structured `v0.5.0` development across **27 atomic Conventional Commits** on `main` covering config, archive resilience, narrator grounding, verification jobs, synthetic test suites, diagnostics, 3D/2D frontend modules, deployment orchestration, screenshots, and release metadata.
- Added `docs/screenshots/` (`6` verified renders of the live 3D Overview, 2D Observatory workbench, 5-verification benchmarks matrix, RW Aurigae variable mode, Cosmic Narrator Q&A, and system architecture) and overhauled `README.md` with visual tour, Mermaid architecture diagram, annotated folder tree, benchmark metrics, and Modern Web Guidance notes.

### Frontend (`frontend/`)
- **Packaged Multi-Page ORVYX Experience & 2D Blink Observatory (`frontend/`)**:
  - Split the experience cleanly across **4 dedicated pages**: `index.html` (`01 Overview`), `mission.html` (`02 Mission & Optics`), `narrator.html` (`03 Cosmic Narrator`), and `explorer.html` (`04 2D Blink Observatory`), sharing responsive desktop/mobile navigation and single-row workbench switcher.
  - Added `mission.html`, `narrator.html`, `style.css`, `app.js`, `scene.js`, `spherex-effects.js`, `three.module.js`, `addons/`, local `assets/` (`spherex.glb`, WOFF2 fonts, OFL/MIT licenses, WebP textures), and `frontend/docs/` (`frontend_design_draft.md`, `goldfish_frontend_review_report.md`).
  - Removed legacy `#heroLookButton`, `#visualToggle`, and `#visualPanel` cinematic toggle controls cleanly while preserving default WebGL postprocessing via guarded settings in `app.js` and multi-page scene framing in `scene.js`.
  - Replaced user-facing raw API badges (`:8000/docs`, `obs_...` hashes) with clean domain labels (`5+1 SUITE READY`, `VERIFIED 5/5 + CONTROL`, `VERIFIED · PASS`) and replaced raw ID text input in `narrator.html` with a curated `#narratorTargetSelect` sky patch selector plus `obs_` output sanitization in `app.js` and `explorer.js`.
  - `explorer.html`, `explorer.css`, and `explorer.js`: 3-column workbench featuring dual `96×96 → 384×384` WiseView `asinh` & dipole difference canvases, `01–04` epoch timeline bar, `102`-band (`D1–D6`) SED dock, native `<input type="checkbox" switch>` and `<dialog id="benchmarksDialog" closedby="any">` (`commandfor="benchmarksDialog"`) with progressive polyfills, and `Run 5 Verifications ↻` interactive matrix.
  - Configurable API origin in `explorer.js` and `app.js` via `window.ORVYX_API_ORIGIN`, `?api_origin=`, port `8000` same-origin detection, or default `http://127.0.0.1:8000`.

### Backend (`backend/`)
- **Live Observatory & Narrative Integration**:
  - Wired OpenAI-compatible LLM provider and Tavily NASA evidence retrieval (`backend/app/archive/tavily.py`, `backend/app/narrator/ask.py`, `backend/app/narrator/llm.py`) plus mock external provider server (`backend/app/jobs/mock_providers.py`).
  - Hardened HTTP retries/timeouts and IRSA transport error classification (`backend/app/archive/http_client.py`, `backend/app/archive/irsa.py`, `backend/app/api/observe.py`).
  - Added `backend/app/jobs/warm_five_verifications.py` to warm all `5` challenge verification targets (`WISE 0855`, `Barnard's Star`, `Epsilon Indi B`, `RW Aurigae`, `R Draconis`), `negative_control` (`Gaia DR3 720517945437337600`), and restore snapshot `obs_00e666311c999759` into Redis + disk cache (`bench_0d2bdeb53b`, `6/6 pass`).
- **Test Isolation, Lint & Typecheck Cleanups**:
  - Added autouse `_isolate_offline_test_env` in `backend/tests/conftest.py` and isolated `backend/tests/integration/test_jobs.py`, `backend/tests/unit/test_config_schemas.py`, and `backend/tests/unit/test_archive_adapters.py` from host `.env` and live Redis.
  - Clean `ruff check backend`, `mypy backend/app` (`75` source files), and offline `pytest backend/tests -m "not live" -q` (`85 passed, 1 deselected`).

### Deployment Packaging
- Bumped package version to `0.5.0` in `pyproject.toml` (keeping `pipeline_version = "1.0.0"` unchanged to preserve deterministic `obs_...` IDs and cache keys).
- Added `frontend/Dockerfile`, root `docker-compose.yml`, `frontend` service in `backend/docker-compose.yml`, and `run-frontend` / `warm-verifications` targets in `Makefile`.
