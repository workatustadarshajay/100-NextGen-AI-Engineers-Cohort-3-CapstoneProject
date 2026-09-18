from functools import lru_cache

from langgraph.errors import NodeError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, RetryPolicy

from app.services.agents.state import ClinicalWorkflowState
from app.services.ai.client import MissingGeminiKeyError
from app.services.extract_from_pdf import extract_from_pdf
from app.services.recommend_follow_ups import recommend_follow_ups
from app.services.retrieve_the_docs import retrieve_the_docs
from app.services.summarise_and_generate_test import summarise_and_generate_test


def _is_retryable(error: BaseException) -> bool:
    """A missing key or an unreadable PDF will never succeed on a retry."""
    return not isinstance(error, (MissingGeminiKeyError, ValueError))


RETRY_POLICY = RetryPolicy(max_attempts=3, retry_on=_is_retryable)


def analyze_report(state: ClinicalWorkflowState) -> dict:
    analysis = extract_from_pdf(state["file_path"])
    return {"analysis": analysis, "agent_events": ["report_analysis"]}


def retrieve_guidelines(state: ClinicalWorkflowState) -> dict:
    analysis = state["analysis"]
    abnormal = ", ".join(
        f"{finding.test_name} {finding.flag}" for finding in analysis.abnormal_findings
    )
    query = f"{analysis.presenting_concern}. {abnormal}".strip()
    citations = retrieve_the_docs(query)
    return {"citations": citations, "agent_events": ["guideline_retrieval"]}


def summarise(state: ClinicalWorkflowState) -> dict:
    summary = summarise_and_generate_test(state["analysis"], state.get("citations", []))
    return {"summary": summary, "agent_events": ["summary"]}


def recommend(state: ClinicalWorkflowState) -> dict:
    recommendations = recommend_follow_ups(
        state["analysis"], state.get("citations", []), state.get("summary")
    )
    return {"recommendations": recommendations, "agent_events": ["recommendation"]}


def handle_failure(state: ClinicalWorkflowState, error: NodeError) -> Command:
    """Runs only once a node has exhausted its retry budget."""
    return Command(
        update={
            "failure": f"{error.node}: {error.error}",
            "agent_events": [f"{error.node}:failed"],
        },
        goto=END,
    )


@lru_cache(maxsize=1)
def get_clinical_graph():
    """Build the sequential Report Analysis -> RAG -> Summary -> Recommendation graph."""
    builder = StateGraph(ClinicalWorkflowState)
    for name, node in (
        ("analyze_report", analyze_report),
        ("retrieve_guidelines", retrieve_guidelines),
        ("summarise", summarise),
        ("recommend", recommend),
    ):
        builder.add_node(
            name, node, retry_policy=RETRY_POLICY, error_handler=handle_failure
        )

    builder.add_edge(START, "analyze_report")
    builder.add_edge("analyze_report", "retrieve_guidelines")
    builder.add_edge("retrieve_guidelines", "summarise")
    builder.add_edge("summarise", "recommend")
    builder.add_edge("recommend", END)
    return builder.compile()


async def run_clinical_workflow(document_id: int, file_path: str) -> ClinicalWorkflowState:
    """Run the full agent workflow for one uploaded document."""
    graph = get_clinical_graph()
    return await graph.ainvoke(
        {
            "document_id": document_id,
            "file_path": file_path,
            "agent_events": [],
            "citations": [],
            "recommendations": [],
            "failure": None,
        }
    )
