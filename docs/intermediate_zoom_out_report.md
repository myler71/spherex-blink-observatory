# Stage 8: Intermediate Zoom-Out Report (`egm-zoom-out`)

**Target:** `docs/design_draft.md` (updated after Stage 5/7/9 resolution)
**Status:** Passed with zero blockers.

## Summary

- Zero Blockers remain; `science/` is cleanly isolated behind `ArchivePort` / `CatalogOverlayPort` (`science/ports.py`) with zero LLM or HTTP wire imports.
- Accepted 3 Major refinements into implementation:
  1. Route raw cutout byte caching and LRU pruning through `store/cache.py` (`CacheStore`) injected into `IrsaArchiveAdapter`.
  2. Keep PostgreSQL `tsvector` + `pgvector` and offline SQLite/in-memory lexical corpus lookup inside `store/` (`db.py` / `documents.py`), keeping `narrator/nodes/retriever.py` thin.
  3. Declare `"langgraph>=0.2.53"` explicitly in `pyproject.toml`.
- Accepted Nits: keep `EncodedArray` base64 encoding in `schemas/`/`api/`, avoid redundant dual photometry calls inside `detect.py`, and keep transient `pending` / `60s` fallback narrative entries in `CacheStore`.
