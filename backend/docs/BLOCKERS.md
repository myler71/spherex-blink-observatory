# Blockers & Environment Constraints (`docs/BLOCKERS.md`)

1. **Docker Daemon Socket Permissions (Gate G4 live container startup)**
   - **Observed:** `permission denied while trying to connect to the docker API at unix:///var/run/docker.sock`.
   - **Verified:** `docker compose -f backend/docker-compose.yml config -q` passes syntax/schema validation, and `backend/Dockerfile` + `backend/docker-compose.yml` are ready.
   - **Fallback Applied:** Ran all API, integration, and `uvicorn` smoke tests directly against the local `.venv` with automatic Redis-absent disk cache and Postgres-absent graceful degradation (`D-09`).
   - **Owner Action:** Add user to `docker` group or run `sudo docker compose -f backend/docker-compose.yml up --build`.

2. **Optional External Credentials Absent (`NASA_ADS_API_TOKEN`, `LLM_API_KEY`)**
   - **Observed:** Neither `NASA_ADS_API_TOKEN` nor `LLM_API_KEY` is set in the environment.
   - **Fallback Applied:** `AdsAdapter` returns `status="not_configured"` and local SQLite FTS5 `CORPUS_CHUNKS` supplies target literature; `NarratorOrchestrator` uses `TemplateLlmProvider` (`generator="template"`, validated by `ClaimValidator`) and is verified with `FakeLlmProvider`.
   - **Owner Action:** Set `NASA_ADS_API_TOKEN` and `LLM_PROVIDER=openai_compatible` + `LLM_API_KEY` + `LLM_MODEL` in `.env` when ready.

3. **CDS Primary SIMBAD/VizieR Mirror 404 (`V-11`)**
   - **Observed:** `https://simbad.cds.unistra.fr/simbad/sim-tap/capabilities` and `https://vizier.cds.unistra.fr/viz-bin/votable` returned HTTP 404 during Phase 0 checks.
   - **Fallback Applied:** Configured Harvard CFA mirrors (`simbad.harvard.edu`, `vizier.cfa.harvard.edu`) first in `Settings` with fast non-backoff failover (`D-05`).
