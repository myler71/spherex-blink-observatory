import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="SPHEREx Mock External Providers (ADS & LLM)")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ads/v1/search/query")
async def ads_search(q: str = "", rows: int = 5) -> dict[str, Any]:
    """Mock NASA ADS literature endpoint."""
    return {
        "response": {
            "numFound": 2,
            "start": 0,
            "docs": [
                {
                    "bibcode": "2026AJ....162...45B",
                    "title": ["SPHEREx Near-Infrared Astronomical Survey First Data Release"],
                    "doi": ["10.26131/IRSA678"],
                    "year": "2026",
                    "abstract": "We present calibrated observations and spectral images from the SPHEREx all-sky survey.",
                },
                {
                    "bibcode": "2026ApJ...920...12S",
                    "title": ["Astrometric and Proper Motion Measurements with SPHEREx"],
                    "doi": ["10.1088/0004-637X/920/1/12"],
                    "year": "2026",
                    "abstract": "Investigation of proper-motion candidates and brown dwarfs using Linear Variable Filters.",
                },
            ][:rows],
        }
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> JSONResponse:
    """Mock OpenAI-compatible chat completion endpoint returning structured story claims."""
    body = await request.json()
    messages = body.get("messages", [])
    user_content = messages[-1].get("content", "") if messages else ""

    # Parse input summary or evidence payload
    ev_ids = []
    try:
        parsed = json.loads(user_content)
        if isinstance(parsed, dict) and "evidence_ids" in parsed:
            ev_ids = [e["evidence_id"] for e in parsed["evidence_ids"]]
    except Exception:
        pass

    ev_patch = ev_ids[0] if ev_ids else "ev_patch_001"
    ev_det = next((i for i in ev_ids if "det" in i), ev_patch)

    story_payload = {
        "chapters": [
            [
                {
                    "statement": "SPHEREx observed this patch across multiple visits with validated astrometric alignment.",
                    "visual_marker_id": None,
                    "action_type": "focus_object",
                    "confidence_badge": "Probable Association",
                    "citations": [
                        {
                            "evidence_id": ev_patch,
                            "source_name": "NASA SPHEREx",
                            "reference_id": "SPHEREx",
                            "url": "https://irsa.ipac.caltech.edu/Missions/spherex.html",
                            "source_type": "NASA SPHEREx",
                        }
                    ],
                    "quoted_values": [],
                }
            ],
            [
                {
                    "statement": "Object obj_001 was detected with significant infrared flux and catalogued.",
                    "visual_marker_id": "obj_001",
                    "action_type": "focus_object",
                    "confidence_badge": "Probable Association",
                    "citations": [
                        {
                            "evidence_id": ev_det,
                            "source_name": "NASA SPHEREx Pipeline",
                            "reference_id": "obj_001",
                            "url": "https://irsa.ipac.caltech.edu/Missions/spherex.html",
                            "source_type": "NASA SPHEREx",
                        }
                    ],
                    "quoted_values": [],
                }
            ],
            [
                {
                    "statement": "Candidate moving source obj_001 was linked across observation epochs.",
                    "visual_marker_id": "obj_001",
                    "action_type": "show_motion_vector",
                    "confidence_badge": "Candidate Moving Source",
                    "citations": [
                        {
                            "evidence_id": ev_det,
                            "source_name": "NASA SPHEREx Pipeline",
                            "reference_id": "obj_001",
                            "url": "https://irsa.ipac.caltech.edu/Missions/spherex.html",
                            "source_type": "NASA SPHEREx",
                        }
                    ],
                    "quoted_values": [],
                }
            ],
            [],
            [],
        ]
    }

    response_content = json.dumps(story_payload)
    if "untrusted_question" in user_content:
        # Ask This Patch answer
        response_content = "This patch contains multi-epoch SPHEREx spectral images and verified catalog matches."

    return JSONResponse(
        {
            "id": "chatcmpl-mock-001",
            "object": "chat.completion",
            "created": 1700000000,
            "model": body.get("model", "mock-gemini"),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response_content,
                    },
                    "finish_reason": "stop",
                }
            ],
        }
    )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")
