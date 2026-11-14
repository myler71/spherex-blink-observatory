# Stage 6: Comprehension Report (`egm-comprehension`)

**Target:** `docs/design_draft.md` (`1-82`, `83-150`)

## What this proposes

This document proposes a Python/FastAPI backend architecture for the SPHEREx Blink Observatory that cleanly separates deterministic scientific image processing from AI-generated narrative explanations using a "two brains" design. The deterministic science layer fetches SPHEREx near-infrared cutouts and external astronomy catalogs, calibrates and aligns multi-epoch frames onto a common tangent-plane grid, extracts sources, and computes proper motions, wavelength-matched light curves/variability, spectra, and comparison images without importing any LLM code. The narrative layer reads only a structured evidence bundle produced by the science layer, runs a 5-node LangGraph workflow with local search and NASA ADS lookups to generate a 5-chapter story and answer patch-scoped questions, and validates every claim deterministically (falling back to a static template when no LLM key is configured or retries fail). The plan delivers this system through FastAPI routers, Redis and disk caching (`< 200 ms` p95 for pre-warmed targets), optional PostgreSQL+pgvector persistence, pre-caching/ingestion jobs, and synthetic plus live test suites.

## How the existing system works, per this document

The document does not describe the architecture, modules, or end-to-end behavior of an existing working system. Instead, it refers only to "existing draft code in the hackathon guide" with "24 documented defects" and lists eight specific flaws (such as linear `y/2040` wavelength estimation, cross-wavelength variability mixing, `FLAGS > 0` masking valid stars, 15 MB+ JSON pixel lists, synchronous LLM calls inside `/observe`, and an ungrounded Claim Validator). Beyond inferring that a prior draft had an `/observe` endpoint returning large JSON pixel lists and calling an LLM synchronously without strict grounding, a new reader cannot tell how the existing system works.

---

## Findings

### 1. Severity: Blocker
* **Affected Scope:** Unexplained Subsystems & Persistence/Job Flow (`candidates`, `benchmarks`, `/narrative` job flow, and `ObserveResponse` persistence; lines 44, 62, 97–99, 129–131, 143, 147)
* **Discrepancy Description & Rationale:** Several major components in the Detailed Implementation Plan are completely absent from the Overview, Goals, Architecture Diagram, and Data Flow (candidates/voting, benchmarks, async vs sync narrative job flow, and `ObserveResponse` persistence).

### 2. Severity: Blocker
* **Affected Scope:** Unlinked/Undefined Project Specifications, Targets, and Verification IDs (`B0`, `5 mandatory targets`, `Gaia DR3 negative control`, `V-ID`, `V-04`, `V-06`, `FR`, `NFR`; lines 3, 5, 21, 91, 112, 115, 145, 147, 149–150)

### 3. Severity: Major
* **Affected Scope:** Naming & Module-Boundary Drift Between Overview/Architecture and Detailed Plan (`ObserveOrchestrator`/`ObservePipeline`, `ScienceEngine`, `NarratorService`, `RetrievalStore`, `EvidenceBundle`, and "5-node" LangGraph count; lines 16, 40–49, 61–62, 97, 123–124, 127, 135, 138–139)

### 4. Severity: Major
* **Affected Scope:** Underspecified Deterministic Science Pipeline Mechanics (`coords.py`/`select.py`/`wavelength.py`/`align.py`/`link.py`/`motion.py`; lines 53–60, 113–121)

### 5. Severity: Major
* **Affected Scope:** Undefined `ClaimValidator` Rules & Schema Concepts (`visual_marker_id`, confidence badges, banned phrases, injection patterns; lines 24, 78, 136)

### 6. Severity: Major
* **Affected Scope:** Unexplained SPHEREx FITS, WCS, and External Archive Concepts (lines 15, 22, 54, 56–57, 66, 75, 102–110, 115–117)

### 7. Severity: Major
* **Affected Scope:** Missing Context for Existing Draft System ("hackathon guide", "24 documented defects"; line 9)

### 8. Severity: Nit
* **Affected Scope:** Undefined Abbreviations, Tool Names, and Unclear Qualifiers (lines 9, 15–16, 22, 35, 57, 61, 69, 76, 79, 118, 121, 126, 129, 138, 146)
