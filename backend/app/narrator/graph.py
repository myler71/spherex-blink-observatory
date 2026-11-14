from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.archive.ads import AdsAdapter
from app.config import Settings
from app.narrator.llm import LlmProvider, build_llm_provider
from app.narrator.nodes.analyzer import patch_analyzer_node
from app.narrator.nodes.generator import story_generator_node
from app.narrator.nodes.planner import research_planner_node
from app.narrator.nodes.retriever import retriever_node
from app.narrator.nodes.validate_node import claim_validator_node
from app.schemas.narrative import CosmicNarratorResponse, EvidenceStoreResponse
from app.schemas.observe import ObserveResponse


class NarratorGraphState(TypedDict, total=False):
    observe: ObserveResponse
    evidence: EvidenceStoreResponse
    docs_store: Any
    ads_adapter: AdsAdapter | None
    llm_provider: LlmProvider
    compact_summary: dict[str, Any]
    matched_names: list[str]
    research_query: str
    object_identifiers: list[str]
    retrieved_docs: list[dict[str, Any]]
    ads_papers: list[dict[str, Any]]
    draft: CosmicNarratorResponse
    final_story: CosmicNarratorResponse
    validation_feedback: list[str]
    retries: int
    max_retries: int
    should_retry: bool
    node_timings_ms: dict[str, float]


def _route_after_validation(state: NarratorGraphState) -> str:
    return "story_generator" if state.get("should_retry") else END


class NarratorOrchestrator:
    """5-node LangGraph Cosmic Narrator workflow (FR-27..FR-30)."""

    def __init__(
        self,
        settings: Settings,
        docs_store: Any,
        ads_adapter: AdsAdapter | None = None,
        llm_provider: LlmProvider | None = None,
    ) -> None:
        self.settings = settings
        self.docs_store = docs_store
        self.ads_adapter = ads_adapter
        self.llm_provider = llm_provider or build_llm_provider(settings)
        self._graph = self._compile_graph()

    def _compile_graph(self) -> Any:
        builder: StateGraph[NarratorGraphState] = StateGraph(NarratorGraphState)
        builder.add_node("patch_analyzer", patch_analyzer_node)  # type: ignore[type-var]
        builder.add_node("research_planner", research_planner_node)  # type: ignore[type-var]
        builder.add_node("retriever", retriever_node)  # type: ignore[type-var]
        builder.add_node("story_generator", story_generator_node)  # type: ignore[type-var]
        builder.add_node("claim_validator", claim_validator_node)  # type: ignore[type-var]
        builder.add_edge(START, "patch_analyzer")
        builder.add_edge("patch_analyzer", "research_planner")
        builder.add_edge("research_planner", "retriever")
        builder.add_edge("retriever", "story_generator")
        builder.add_edge("story_generator", "claim_validator")
        builder.add_conditional_edges(
            "claim_validator",
            _route_after_validation,
            {"story_generator": "story_generator", END: END},
        )
        return builder.compile()

    async def run(
        self,
        observe: ObserveResponse,
        evidence: EvidenceStoreResponse,
    ) -> CosmicNarratorResponse:
        initial: NarratorGraphState = {
            "observe": observe,
            "evidence": evidence,
            "docs_store": self.docs_store,
            "ads_adapter": self.ads_adapter,
            "llm_provider": self.llm_provider,
            "retries": 0,
            "max_retries": 2,
            "validation_feedback": [],
            "node_timings_ms": {},
        }
        out = await self._graph.ainvoke(initial)
        return out["final_story"]  # type: ignore[no-any-return]
