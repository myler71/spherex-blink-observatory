# Architectural & Implementation Decisions (`docs/DECISIONS.md`)

Decisions made autonomously under B0 (owner away from PC), ordered most consequential first.

## D-01: Repository Location (`/home/myler71/Projects/spherex-blink-observatory`)
- **What:** Created the git repository on persistent ext4 storage under `/home/myler71/Projects/spherex-blink-observatory` rather than `/tmp`.
- **Why:** `/tmp` on this workstation is `tmpfs` (volatile RAM); persistent storage ensures work survives reboots while the owner is away.
- **Alternatives:** `/tmp/spherex-blink-observatory` (volatile).
- **Reversible:** Standard git repo; can be moved or pushed to any GitHub remote.

## D-02: SPHEREx Data Releases & Query Interface (`DR1` + `QR3` via IRSA TAP)
- **What:** Default `SPHEREX_RELEASES` to `["spherex_dr1", "spherex_dr1_deep", "spherex_qr3", "spherex_qr3_deep"]` queried via IRSA TAP (`spherex.artifact` + `spherex.plane` + `spherex.observation`), deduplicated by `observationid`/`planeid`.
- **Why:** Verified in Phase 0 (`V-01`, `V-02`) that DR1 (Nov 2026) reprocessed QR2, IRSA searches no longer return QR2, and TAP avoids SIA's ~1 day ingestion lag.
- **Alternatives:** SIA-only (`Irsa.query_sia`) or hardcoded `qr2` table names from unverified sample code.
- **Reversible:** All collection names and TAP URLs live in `Settings` (`backend/app/config.py`) / `.env`.

## D-03: `FLAGS` Bitmask Rejection Policy (Exclude `FULLSAMPLE` and `SOURCE`)
- **What:** Reject pixels with bits `{0, 1, 2, 6, 9, 10, 11, 15, 17, 19, 25, 26, 27}` while preserving bits `12` (`FULLSAMPLE`) and `21` (`SOURCE`) as valid science pixels, plus informational flags `7` (`DICHROIC`), `14` (`PHANMISS`), `20` (`CROSSTALK`), `22-24` (`GHOST*`), `28` (`HALO`) in provenance summaries.
- **Why:** Verified from live `barnards_star_sample.fits` (`V-06`) that `FLAGS > 0` masks out real target stars because `SOURCE` (bit 21) and `FULLSAMPLE` (bit 12) are set on valid source pixels.
- **Alternatives:** Rejecting `flags > 0` (catastrophic data loss) or rejecting zero flags (admits cosmic rays and dead pixels).
- **Reversible:** Controlled via `SPHEREX_REJECT_FLAG_BITS` in `Settings`.

## D-04: True Spectral WCS (`WCS-WAVE`, `key="W"`, `sip=None`)
- **What:** Compute central wavelength and bandwidth per pixel using `astropy.wcs.WCS(header, fobj=hdul, key="W")` with `sip = None`, never linear `y / 2040`.
- **Why:** Matches official IRSA tutorial (`V-05`) and handles cutout pixel offsets and curved LVF transmission contours accurately.
- **Alternatives:** Linear `y/2040` interpolation (scientifically invalid on cutouts).
- **Reversible:** Isolated inside `backend/app/science/wavelength.py`.

## D-05: Dual-Mirror Strategy for SIMBAD & VizieR
- **What:** Configure `SIMBAD_TAP_URLS` and `VIZIER_URLS` as ordered lists (`cds.unistra.fr` then `harvard.edu` CFA mirrors) with per-client timeout and fallback.
- **Why:** During Phase 0 verification (`V-11`), `simbad.cds.unistra.fr` returned HTTP 404 while `simbad.harvard.edu/simbad/sim-tap/sync` and `vizier.cfa.harvard.edu` succeeded (`200 OK`).
- **Alternatives:** Single hardcoded CDS URL (fails when primary mirror has downtime).
- **Reversible:** Configurable via env vars.

## D-06: Negative Control Star (`Gaia DR3 720517945437337600`)
- **What:** Selected `Gaia DR3 720517945437337600` (`ra=134.84581545`, `dec=40.99469683`, `G=11.02`, `pmra=-1.263`, `pmdec=-0.863 mas/yr`, `parallax=0.741 mas`, `ruwe=0.886`, `phot_variable_flag='NOT_AVAILABLE'`, `|b|>30°`).
- **Why:** Satisfies FR-24 acceptance criterion (bright, isolated, low proper motion, non-variable, verified in Gaia DR3, and covered by SPHEREx DR1/QR3).
- **Reversible:** Target preset list is data-driven in `backend/app/science/targets.py`.

## D-07: Pixel Transport Encoding (`float32` base64 + `GZipMiddleware`)
- **What:** Encode aligned float32 pixel arrays, variance/display planes, and uint8 flag masks as little-endian base64 strings alongside `(shape, dtype)` metadata, served with FastAPI `GZipMiddleware`.
- **Why:** Keeps a 12-frame 0.08° `observe` payload well under 2 MB compressed (vs >15 MB JSON number lists) while keeping the JSON contract single-request and easily decodable by TypeScript/JavaScript (`Uint8Array` -> `Float32Array`).
- **Alternatives:** Separate binary blob endpoint per frame (12+ extra HTTP round-trips) or raw JSON float arrays (too large/slow).
- **Reversible:** Encapsulated in `backend/app/schemas/observe.py` and `backend/app/science/display.py`.

## D-08: Default LLM Provider (`template` fallback, `openai_compatible` pluggable)
- **What:** Default `LLM_PROVIDER=template` when no `LLM_API_KEY` is configured, backed by an `LlmProvider` protocol supporting `template`, `fake`, and `openai_compatible` (via `langchain_openai.ChatOpenAI`).
- **Why:** Ensures offline CI, zero-key local startup, and deterministic FR-29 validation while allowing one-env-var switch to any OpenAI-compatible or Gemini endpoint.
- **Reversible:** Set `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL` in `.env`.

## D-09: Local Disk + In-Memory Fallback When Redis/PostgreSQL Absent
- **What:** `CacheStore` tries Redis when `REDIS_URL` is reachable and transparently falls back to atomic filesystem cache (`CACHE_DIR`) + in-memory index; `DatabaseStore` checks PostgreSQL connectivity at startup and degrades DB-backed endpoints cleanly (`status="unavailable"` or in-memory test store for candidates when configured) without crashing `/observe`.
- **Why:** Meets FR-22 and FR-23 acceptance criteria in environments without running containers (including CI and unit tests, plus Docker socket permission restrictions observed on host).
- **Reversible:** Bring up `docker compose up` with `.env` pointing to Postgres + Redis.
