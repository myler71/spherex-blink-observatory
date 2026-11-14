# Stage 7: Critic Report (`egm-design` + `egm-structural`)

**Target:** `docs/design_draft.md` (`1-82`, `83-150`)

## Design Critic Findings (`egm-design`)

- **Blocker 1 — `reproject_interp` variance, undersampled PSF, 2D LVF gradient, and `NaN` bleed (`lines 15, 22, 54, 57-61, 77`):**
  Evaluate per-source `WCS-WAVE` at each source's native coordinates (mapped from aligned `(x,y)` via inverse WCS or measured in native space), mask/zero bad pixels before `reproject_interp`, propagate variance conservatively with undersampling error floor, and gate difference pairs on per-pixel $|\Delta\lambda(x,y)|$.
- **Blocker 2 — Coordinate epoch propagation & polar/wrap singularities (`lines 21, 53-54, 58, 60`):**
  Anchor fetch center at propagated target epoch, expand fetch FOV (clamped to `0.5°`), support optional `(pmra, pmdec, epoch)` or Gaia pre-lookup when `propagate=true`, guard `|Dec| <= 89.9°` for north-up WCS, and keep motion fits in $(\mu_{\alpha*}, \mu_\delta)$.
- **Blocker 3 — Unthrottled compute/egress DoS & payload budget at `0.5°` FOV (`lines 21, 23, 53-55, 67, 79`):**
  Rate-limit `/observe` alongside LLM routes, add singleflight request coalescing, cap `max_frames`, enforce LRU disk cache quota, and omit/downsample bulky optional planes above payload budget.
- **Blocker 4 — Cache keys & multi-worker split-brain (`lines 21, 44, 54, 62, 66, 76, 79`, `D-09`):**
  Quantize `(ra, dec, fov)` in cache keys, include `provenance_version` in cutout keys, derive deterministic `observation_id`, scope narrative cache key by `(observation_id, pipeline_version, llm_provider, llm_model, ads_configured)`, never cache transient fallback errors at full TTL, and store shared cache metadata on disk/Redis rather than process-local dicts.
- **Major 5–10:** Expand `Alternatives Considered` (resampling, sync-vs-async, LangGraph vs single call), require `>= 180` days + condition-number check for 5-param parallax, validate `a.uri` strictly + disable cross-host redirects + SHA-256 disk keys + `allow_inf_nan=False`, scan full narrative prose for numeric grounding + wrap untrusted snippets, define explicit `uint8` mask bit-packing, and set explicit per-adapter timeouts (`3s`–`5s`) with immediate mirror failover on 4xx.
- **Nit 11–12:** Separate `spherex_obs_id` from `observe_request_id`; use `sep` (not `sep-pjw`); document single-endpoint catalog degradation.

## Structural Findings (`egm-structural`)

- **Blocker 1 (`lines 64-69`):** Remove unlinked `"by author"` attributions in `Alternatives Considered`.
- **Major 1–5:** Reconcile `ObserveOrchestrator`/`ObservePipeline`, `stack.py`/`coadd`, `NarratorService`, `RetrievalStore`, `EvidenceBundle`; document `/health`, `/benchmarks`, `/candidates`, `/spectrum`, `/evidence`, and async `/narrative`; raise `FeatureRange` altitude and add complete specs to `Detailed Implementation Plan`; enumerate all test/doc/migration/config files; add inline links to `VERIFICATION.md` and `DECISIONS.md`.
- **Nit 1–5:** Consistent list markers, heading blank lines, code fence info strings, LaTeX/units consistency, and clarify 5-node LangGraph grouping (`retriever.py` runs local + ADS branches in parallel).
