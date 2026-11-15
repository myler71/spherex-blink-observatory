# Reproducible synthetic observations

These fixtures exercise the real science pipeline without IRSA, Gaia or SIMBAD.
They are **not real sky observations**. Observation IDs use `synthetic_obs_`,
warnings explicitly identify synthetic data, and frames use `synthetic-dr1`.
Do not use their measurements as scientific evidence about the named stars.

## Inputs

All six presets use seed 42, three visits with two exposures each,
365.25-day visit spacing, detector 2, five static stars and Gaussian noise
sigma 0.08. The generated FITS use `MJy / sr`; source amplitude parameters
are generator inputs, not calibrated integrated source fluxes.

| Preset | Injected RA motion (arcsec/year) | Fractional variable-source amplitude |
|---|---:|---:|
| barnards_star | 10.393 | 0 |
| wise_0855 | 8.152 | 0 |
| epsilon_indi_b | 4.684 | 0 |
| rw_aurigae | 0.028 | 0.65 |
| r_draconis | 0.022 | 0.65 |
| negative_control | 0 | 0 |

These are controlled injections using preset reference magnitudes, not
catalog-validated detections. The variable source alternates flux by
`1 ± amplitude`; 0.65 is **not** a magnitude amplitude.

## Restore or benchmark

Run from the project root with the project's Python environment:

```bash
PYTHONPATH=backend python -m tests.synthetic.restorable_observation \
  --cache-dir /tmp/spherex-synthetic-cache --target all
PYTHONPATH=backend python -m tests.synthetic.run_use_case_benchmarks \
  --output docs/test-results/synthetic-benchmark.json
PYTHONPATH=backend python -m pytest \
  backend/tests/integration/test_observation_cache_expiry.py \
  backend/tests/unit/test_synthetic_restoration.py -q
```

The restore utility defaults to the template provider, disables API keys,
ignores `.env` and uses loopback port 1 for database/Redis isolation.
Redis failure falls back to disk. Explicit cache paths remain the caller's
responsibility; use a separate directory, not the production cache.

Tests construct their own API and cache with the same isolated settings.
They expire the cache envelope, verify 404 responses, restore the observation
and verify observation, evidence, narrative and ask endpoints recover.
The live external model is not part of this deterministic recovery proof.

For Python callers, use `create_isolated_test_settings(cache_dir)`,
`CacheStore(settings)` and `restore_synthetic_observation(cache, target,
tmp_dir=staging, settings=settings)` from
`tests.synthetic.restorable_observation`. A restored fixture must be served
by an API configured with that **same cache**, not an unrelated test client.
