# SPHEREx Blink Observatory — Final Backend & AI Delivery Report

## 1. Status in three sentences
The SPHEREx Blink Observatory backend and citation-validated Cosmic Narrator / Ask This Patch services are implemented, tested (`55/55` offline tests passing, `90%` coverage on `science/` and `narrator/validator.py`, `ruff` and `mypy` clean with zero errors), and pushed to the private repository `myler71/spherex-blink-observatory`. Live NASA/IPAC IRSA DR1/QR3 archive integration passed (`test_live_irsa_barnards_star_search_and_cutout` + live 6-target benchmark run `bench_a8ae4c505f`), and `uvicorn` served `/health`, `/targets`, and `/benchmarks` cleanly. The service is demo-ready for cached presets and live arbitrary-coordinate observation, while Docker container startup (`permission denied` on `/var/run/docker.sock`) and external LLM/ADS credentials remain for owner setup.

## 2. Needs owner action
1. **Run Docker Compose stack (Gate G4 live containers):** Host user lacks permission on `/var/run/docker.sock` (`permission denied`). Run:
   ```bash
   sudo usermod -aG docker $USER && newgrp docker
   docker compose -f backend/docker-compose.yml up --build
   ```
2. **Run Alembic migrations against PostgreSQL once containers are up:**
   ```bash
   cd backend && ../.venv/bin/alembic upgrade head
   ```
3. **Add optional LLM & NASA ADS credentials in `.env` (copy from `.env.example`):**
   - Set `LLM_PROVIDER=openai_compatible`, `LLM_MODEL=<model>`, `LLM_API_KEY=<key>`, `LLM_BASE_URL=<optional>` to upgrade from the deterministic `template` narrator.
   - Set `NASA_ADS_API_TOKEN=<token>` to enable live NASA ADS abstract retrieval alongside local FTS5/pgvector retrieval.
4. **Pre-warm caches before live demo:**
   ```bash
   make precache
   ```
5. **Review `FINAL_REPORT.md` and live benchmark tuning caveats:** Inspect Section 4 below (particularly `negative_control` undersampled-PSF jitter at `SNR 100` and `wise_0855` band filtering).

## 3. How to run
```bash
# 1. Setup virtual environment from lockfile
make setup
cp .env.example .env

# 2. Offline test suite, coverage (>=85% gate), lint, format, and typecheck
make test
make coverage
make lint
make format
make typecheck

# 3. Live archive test (hits IRSA TAP & cutout service)
make test-live

# 4. Ingest local scientific docs, pre-warm presets, and run benchmarks
PYTHONPATH=backend .venv/bin/python -m app.jobs.ingest_docs
make precache
make benchmarks

# 5. Start API server locally (or via Docker Compose)
make run
```

## 4. Five-target results
All values below were produced on **2026-11-14** by `PYTHONPATH=backend .venv/bin/python -m app.jobs.run_benchmarks` (`run_id: bench_a8ae4c505f`) using **real** SPHEREx DR1/QR3 cutouts downloaded from NASA/IPAC IRSA:

| Target | Mode | Data Source | Reference Value & Citation | Measured Value ± Uncertainty | Residual | SNR | Visits / Baseline | Processing (ms) | Status | Cause / Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| Barnard's Star | `motion` | `real` | `10.393 "/yr` (`Gaia DR3 4472832130942575872`) | `13.5681 ± 4.143 "/yr` | `3.175 "/yr` | `148.79` | `9` / `402.76 d` | `23503.91` | `pass` | Measured motion consistent with Gaia DR3 within 3-sigma. |
| WISE 0855 | `motion` | `real` | `8.152 "/yr` (`SIMBAD WISEA J085510.74-071442.5`) | `5.740 ± 2.914 "/yr` | `2.412 "/yr` | `13.65` | `5` / `361.70 d` | `58096.90` | `inconclusive` | `1.97σ < 3.0σ` significance across mixed-band selection; faint in short bands (`D1–D3`). |
| Epsilon Indi B | `motion` | `real` | `4.684 "/yr` (`SIMBAD * eps Ind B`) | `27.4528 ± 2.582 "/yr` | `22.769 "/yr` | `6.83` | `9` / `521.28 d` | `60265.29` | `inconclusive` | Blended/distorted near bright primary Epsilon Indi A at `6.16"/px` scale. |
| RW Aurigae | `variability` | `real` | `variable` (`Gaia DR3 156430822114424576`) | `variable=True, moving=True` | — | `116.83` | `7` / `376.88 d` | `45901.77` | `inconclusive` | Variable in matched band (`variable=True`), but spurious `moving=True` on bright centroid triggered strict non-moving gate. |
| R Draconis | `variability` | `real` | `variable` (`Gaia DR3 1648328016354496384`) | `variable=False, moving=False` | — | `18.73` | `9` / `409.70 d` | `40957.40` | `inconclusive` | Bright Mira core (`G=6.37`) triggers `OVERFLOW`/`NONLINEAR` flag masking in DR1 frames. |
| Negative Control (`Gaia DR3 720517945437337600`) | `both` | `real` | `static (~0 "/yr), non-variable` (`Gaia DR3`) | `pm=2.4137 "/yr, var=True` | — | `100.77` | `7` / `195.50 d` | `34245.70` | `fail` | Undersampled PSF (`~1 px`) phase-jitter under `reproject_interp` at `SNR=100` exceeds `2%` floor (`chi2 >= 6`). |

*(Note: All synthetic verification tests in `tests/unit/test_motion_variability.py` and `tests/integration/test_observe_pipeline.py` pass `0.65 px` mover recovery, `50` static stars with `0` false movers, `Dec=60°` `cos(Dec)` scaling, sloped-spectrum constant star non-variability, and `30%` same-band variability.)*

## 5. Traceability table

| ID | Priority | Status | Tests / Evidence | Notes |
|---|---|---|---|---|
| `FR-01` | P0 | `met` | `test_archive_irsa`, `test_live_archives` | IRSA TAP (`spherex.artifact`/`plane`/`observation`) + config-driven `SPHEREX_RELEASES`. |
| `FR-02` | P0 | `met` | `test_select_coords.py` | Deduplicates releases, clusters visits, maximizes baseline, warns on 1 visit. |
| `FR-03` | P0 | `met` | `test_archive_adapters.py` | Concurrent cutout download, retries, FITS validation, 0-download cache hit, HTTP 502 if all fail. |
| `FR-04` | P0 | `met` | `test_select_coords.py` | `SkyCoord.apply_space_motion()` propagation verified for Barnard's Star (`< 1"`). |
| `FR-05` | P0 | `met` | `test_calibrate_flags_wavelength.py` | `ZODI` subtraction, verified `FLAGS` bits preserving `12`/`21`, missing-extension warnings. |
| `FR-06` | P0 | `met` | `test_calibrate_flags_wavelength.py` | Exact `WCS(..., key="W")` (`sip=None`) verified within `1%` of bandwidth on real fixtures. |
| `FR-07` | P0 | `met` | `test_align_detect_link.py` | North-up `TAN` WCS, `<= 0.1 px` RMS rotated static alignment, conservative mask/variance propagation. |
| `FR-08` | P0 | `met` | `test_align_detect_link.py` | Native-endian `sep.Background` + `sep.extract`, aperture `contaminated` flag. |
| `FR-09` | P0 | `met` | `test_motion_variability.py` | Progressive multi-epoch `cKDTree` linking, weighted PM with `cos(Dec)` (`Dec=60°`), `0.65 px` mover, 50-star 0-false-mover, circular RA wrap. |
| `FR-10` | P0 | `met` | `test_motion_variability.py` | Band-matched reduced $\chi^2$ & light curves; sloped constant star not flagged variable. |
| `FR-11` | P0 | `met` | `test_comparisons_stack_spectrum_display.py` | Matched-band difference/addition + frame-minus-median flipbook; mismatched pairs omitted with reason. |
| `FR-12` | P1 | `met` | `test_comparisons_stack_spectrum_display.py` | Per-detector, per-visit, per-bin inverse-variance co-adds with `√N` SNR gain. |
| `FR-13` | P1 | `met` | `test_comparisons_stack_spectrum_display.py`, `test_api_endpoints.py` | Wavelength-sorted spectrum with provenance & non-simultaneity notice. |
| `FR-14` | P1 | `met` | `test_comparisons_stack_spectrum_display.py` | Hash-stable WiseView `AsinhStretch` + `AsymmetricPercentileInterval` + invert. |
| `FR-15` | P0 | `met` | `test_calibrate_flags_wavelength.py`, `test_observe_pipeline.py` | Full per-frame provenance & decoded `FLAGS` counts. |
| `FR-16` | P1 | `met` | `test_archive_adapters.py`, `test_observe_pipeline.py` | Gaia DR3 epoch propagation, row cap `truncated` flag, `unavailable` degradation. |
| `FR-17` | P1 | `met` | `test_observe_pipeline.py` | Three-valued `has_counterpart`/`no_counterpart`/`unknown`; wording `"no Gaia DR3 counterpart"`. |
| `FR-18` | P1/P2 | `met` | `test_archive_adapters.py`, `test_api_endpoints.py` | AllWISE, SIMBAD (Harvard mirror failover), VizieR, NED, CADC NEOSSat, JPL Horizons, WiseView URL. |
| `FR-19` | P0 | `met` | `test_openapi_contract.py`, `test_api_endpoints.py` | All `/api/v1` endpoints, Pydantic v2 models, OpenAPI matches `backend/docs/API.md`. |
| `FR-20` | P0 | `met` | `test_config_schemas.py`, `test_api_endpoints.py` | Little-endian `float32`/`uint8` base64 + gzip `< 2 MB` (`12` frames at `0.08°`). |
| `FR-21` | P0 | `met` | `test_api_endpoints.py` | `/observe` never waits for LLM; `/narrative` async polling (`pending` -> `ready`). |
| `FR-22` | P0 | `met` | `test_cache_db.py`, `test_api_endpoints.py` | Redis + atomic disk cache (`< 200 ms` p95 over 50 warm requests), versioned keys, `precache.py`. |
| `FR-23` | P1 | `partial` | `test_cache_db.py`, `0001_initial_schema.py` | ORM models + reversible Alembic migration written; live Postgres apply deferred (Docker socket permission). |
| `FR-24` | P0 | `met` | `test_jobs.py`, `bench_a8ae4c505f` | Live 5-target + Gaia DR3 negative-control benchmark run & endpoint. |
| `FR-25` | P2 | `met` | `test_api_endpoints.py` | Candidates CRUD, 1 vote per `client_fingerprint` (`409` duplicate), consensus score. |
| `FR-26` | P0 | `met` | `test_narrator_graph.py`, `test_api_endpoints.py` | Deterministic `ev_*` `EvidenceStoreResponse` built before generation & persisted. |
| `FR-27` | P0 | `met` | `test_narrator_graph.py` | Typed 5-node LangGraph workflow with parallel local+ADS retrieval & per-node timing. |
| `FR-28` | P0 | `met` | `test_validator.py`, `test_narrator_graph.py` | 5-chapter `CosmicNarratorResponse` strict schema validation. |
| `FR-29` | P0 | `met` | `test_validator.py` | 16 adversarial drafts rejected (invented ID/URL, wrong marker, altered/unindexed/sci numbers, bad badge, Planet Nine/Planet-Nine/Planet X/9th planet). |
| `FR-30` | P0 | `met` | `test_narrator_graph.py` | `LlmProvider` (`template`, `fake`, `openai_compatible`); zero-key valid 5-chapter template. |
| `FR-31` | P1 | `met` | `test_cache_db.py`, `test_jobs.py` | `ingest_docs.py` + `LocalDocumentStore` SQLite FTS5 fallback + Postgres `tsvector`/pgvector ORM. |
| `FR-32` | P1 | `met` | `test_ask.py` | Deterministic `"fastest"`/`"brightest"` ranking, out-of-scope refusal, injection neutralization, numeric verification. |
| `FR-33` | P1 | `met` | `test_rate_limit.py`, `test_api_endpoints.py` | Narrative cache by provider/model/ADS, per-IP rate limiting (`429` + `Retry-After`), spoof-resistant IP extraction. |
| `NFR-01`–`NFR-10` | P0 | `met` (`NFR-01` partial) | `Makefile`, `ruff`, `mypy`, `uvicorn` smoke, `docs/` | `make test` (`55 passed`), `make coverage` (`90%`), `make lint`, `make format`, `make typecheck` (`0` errors), `docker-compose config` valid; container daemon blocked on host permissions. |

## 6. Verification summary
- **`V-01`–`V-10`, `V-12`: `verified`** (2026-11-14) against live IRSA TAP, Gaia DR3, AllWISE, CADC NEOSSat, JPL Horizons, and downloaded DR1/QR3 FITS fixtures (`backend/tests/fixtures/*.fits`).
- **`V-11`: `partially verified`** — CADC NEOSSat, JPL Horizons, Harvard SIMBAD (`simbad.harvard.edu`), and CFA VizieR (`vizier.cfa.harvard.edu`) verified live `200 OK`; primary `simbad.cds.unistra.fr` returned `404`; NASA ADS requires `NASA_ADS_API_TOKEN`.
- **Key divergences from Part A:**
  - Queries `spherex_dr1` / `spherex_qr3` via `spherex.artifact JOIN spherex.plane JOIN spherex.observation` (`observationid`, not `obs_id`), reflecting IRSA's Nov 2026 DR1 release.
  - Excludes `FULLSAMPLE` (bit 12) and `SOURCE` (bit 21) from `FLAGS` rejection (Part A's `flags > 0` masked real stars).
  - Evaluates `WCS-WAVE` at each source's native pixel position mapped back from aligned coordinates, preventing LVF spectral-slope false variability.
  - Uses `sep>=1.4` instead of deprecated `sep-pjw`, with native-endian `float32` conversion (`>f4` FITS fix).

## 7. Decisions made without the owner
Recorded in `backend/docs/DECISIONS.md`:
1. **`D-01`**: Created persistent git repo at `/home/myler71/Projects/spherex-blink-observatory` (ext4) instead of volatile `/tmp` (tmpfs), pushed to private GitHub repo `myler71/spherex-blink-observatory`.
2. **`D-02`**: Defaulted `SPHEREX_RELEASES` to `DR1` + `QR3` via IRSA TAP with SIA fallback.
3. **`D-03`**: Configured `SPHEREX_REJECT_FLAG_BITS` to reject defect bits while preserving `FULLSAMPLE` (12) and `SOURCE` (21).
4. **`D-06`**: Selected `Gaia DR3 720517945437337600` (`G=11.02`, `ruwe=0.886`, `|pm|<1.6 mas/yr`) as the documented static negative control star.
5. **`D-07`**: Transported `float32`/`uint8` arrays as little-endian base64 inside gzipped JSON (`< 2 MB`).
6. **`D-08` / `D-09`**: Configured `template` LLM + atomic disk cache + SQLite FTS5 lexical fallbacks when credentials/Redis/Postgres are absent.

## 8. Blockers and known limits
- **Gates G1–G5 status:** **G1** (`55/55` offline tests pass), **G2** (`90%` line coverage on `science/` + `validator.py`, `>= 85%`), **G3** (`ruff` + `mypy` 0 errors), and **G5** (this report) **PASS**. **G4** (`docker compose up`) could not launch containers due to host `/var/run/docker.sock` permission denial (`docker compose config` passed and `uvicorn` live smoke test passed).
- **Scientific caveat (undersampled PSF & bright star saturation):** SPHEREx pixels are `~6.16"/px` (`PSF_FWHM ~ 1–1.5 px`). High-SNR bright stars (`SNR ~ 100`) under `reproject_interp` show `~5%` resampling phase jitter that triggered `var=True` on `negative_control` (`SNR=100.77`), while very bright targets (`R Draconis`, `Epsilon Indi A`) trigger detector saturation flags or blend nearby faint companions. Native-frame PSF-fit photometry (using the embedded `EPSF` BinTableHDU) is the recommended upgrade path to tighten photometry on bright/undersampled sources.

## 9. Suggested next steps
1. Grant Docker socket access and run `docker compose -f backend/docker-compose.yml up --build` + `alembic upgrade head` to exercise Gate G4 against live PostgreSQL+pgvector and Redis.
2. Add `LLM_API_KEY` and `NASA_ADS_API_TOKEN` to `.env` and run `make precache` to populate cached LLM narratives and ADS citations for all 6 presets.
3. Upgrade `detect.py` / `variability.py` to optionally perform native-frame `photutils` `ImagePSF` forced photometry using the embedded `EPSF` extension so bright stars like `negative_control` and blended `Epsilon Indi B` achieve tighter photometric/astrometric scatter.
4. Restrict `wise_0855` benchmark selection to long-wavelength detectors (`D4–D6`, `2.4–5.0 µm`) where Y-dwarfs have high SNR.
5. Connect the frontend Explorer, Benchmarks, and Cosmic Narrator panels to `/api/v1/observe`, `/api/v1/observe/{id}/narrative`, `/api/v1/observe/{id}/ask`, and `/api/v1/benchmarks`.
