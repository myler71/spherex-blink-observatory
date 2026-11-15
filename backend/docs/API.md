# SPHEREx Blink Observatory — HTTP API Reference (`docs/API.md`)

All routes are served under `/api/v1` and match the generated OpenAPI specification at `/openapi.json`.

## Uniform Error Envelope

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable summary",
    "details": {}
  }
}
```

## Endpoints

| Method & Path | Purpose | Status Codes |
|---|---|---|
| `GET /api/v1/health` | Liveness & dependency status (`archive`, `redis`, `postgres`, `llm`, `ads`) | `200` |
| `GET /api/v1/targets` | List the 5 mandatory targets and Gaia DR3 static negative control | `200` |
| `GET /api/v1/observe` | Run or serve cached deterministic SPHEREx pipeline (`ra`, `dec`, `fov`, `release`, `mode`, `detector`, `wave_min`, `wave_max`, `max_frames`, `propagate`, `target`, `include_overlays`, `include_csa_neossat`, `include_horizons`, `include_variance`, `linear`, `min_pct`, `max_pct`, `invert`) | `200`, `404`, `422`, `429`, `502` |
| `GET /api/v1/observe/{observation_id}` | Fetch stored `ObserveResponse` from cache | `200`, `404` |
| `GET /api/v1/observe/{observation_id}/spectrum` | On-the-fly wavelength-sorted spectrum (`object_id` or `ra`/`dec`) | `200`, `404` |
| `GET /api/v1/observe/{observation_id}/narrative` | Fetch or start 5-chapter Cosmic Narrator job (`pending` / `ready` / `failed`) | `200`, `404`, `429` |
| `GET /api/v1/observe/{observation_id}/evidence` | Retrieve deterministic `EvidenceStoreResponse` | `200`, `404` |
| `POST /api/v1/observe/{observation_id}/ask` | Ask This Patch evidence-scoped Q&A (`{ "question": "..." }`) | `200`, `404`, `422`, `429` |
| `GET /api/v1/benchmarks` | Latest 5-target + negative-control benchmark run | `200` |
| `GET /api/v1/candidates` | List citizen-flagged candidate detections | `200` |
| `POST /api/v1/candidates` | Create a candidate from an observation + object | `201`, `422` |
| `POST /api/v1/candidates/{candidate_id}/votes` | Vote `Real Motion` / `Variable Star` / `Artifact` (1 vote per `client_fingerprint`) | `200`, `404`, `409`, `422` |

## NASA web search for questions

Set `TAVILY_API_KEY` in the backend environment to enable Tavily for general
in-scope questions. Search is restricted to `nasa.gov` and `ipac.caltech.edu`;
returned snippets are untrusted external context, and `sources` lists retrieved
pages, not independently verified citations for each statement. Existing
observation evidence remains available if Tavily is unavailable. Queries are
sent to Tavily and consume API credits. Restart the backend after changing the key.

Example using a cached observation:

```sh
curl -X POST http://127.0.0.1:8000/api/v1/observe/OBSERVATION_ID/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"What does the SPHEREx spectrum tell us about this patch?"}'
```
