# SPHEREx Blink Observatory — Backend & AI Services

Deterministic astrophysics pipeline, multi-agency archive integrations, and citation-validated AI narrative service for the NASA Space Apps 2026 **Planet X and SPHEREx** challenge.

## Quick Start

```bash
make setup
cp .env.example .env
make test
make run
```

With Docker Compose (API + PostgreSQL/pgvector + Redis):

```bash
docker compose -f backend/docker-compose.yml up --build
```

## Documentation

- `backend/docs/VERIFICATION.md` — Phase 0 live archive verification (`V-01`–`V-12`)
- `backend/docs/DECISIONS.md` — Architectural decisions and trade-offs
- `backend/docs/API.md` — HTTP API reference (matches `/openapi.json`)
- `backend/docs/SCIENCE.md` — Calibration, WCS-WAVE, linking, motion, and variability methods
- `backend/docs/ATTRIBUTION.md` — Required NASA/IPAC IRSA, ESA Gaia, CSA CADC, SIMBAD, AllWISE, and library acknowledgements
