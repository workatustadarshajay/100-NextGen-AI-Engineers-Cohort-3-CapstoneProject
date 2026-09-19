from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from functools import lru_cache
from time import perf_counter
from typing import Any

from langgraph.errors import NodeError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, RetryPolicy

from app.observability import log_workflow_event, make_workflow_event, safe_error_message
from app.services.agents.state import ClinicalWorkflowState
from app.services.ai.client import GeminiResponseError, MissingGeminiKeyError
from app.services.extract_from_pdf import extract_from_pdf
from app.services.recommend_follow_ups import recommend_follow_ups
from app.services.retrieve_the_docs import retrieve_the_docs
from app.services.summarise_and_generate_test import summarise_and_generate_test


_stage_attempts: ContextVar[dict[str, int] | None] = ContextVar(
    "workflow_stage_attempts", default=None
)


def _is_retryable(error: BaseException) -> bool:
    """Retry transient provider failures without thrashing on quota or input errors."""
    if isinstance(error, (MissingGeminiKeyError, GeminiResponseError, ValueError)):
        return False

    message = str(error).lower()
    if "quota" in message or "billing" in message or "resource exhausted" in message:
        return False

    for attribute in ("status_code", "code", "http_status"):
        status_code = getattr(error, attribute, None)
        if status_code is not None:
            try:
                return int(status_code) in {408, 409, 429, 500, 502, 503, 504}
            except (TypeError, ValueError):
                pass

    return isinstance(error, (ConnectionError, TimeoutError, OSError))


RETRY_POLICY = RetryPolicy(
    initial_interval=0.5,
    backoff_factor=2.0,
    max_interval=8.0,
    max_attempts=2,
    jitter=True,
    retry_on=_is_retryable,
)


def _next_attempt(stage: str) -> int:
    attempts = _stage_attempts.get()
    if attempts is None:
        attempts = {}
        _stage_attempts.set(attempts)
    attempts[stage] = attempts.get(stage, 0) + 1
    return attempts[stage]


def _run_stage(
    stage: str,
    state: ClinicalWorkflowState,
    operation: Callable[[], dict[str, Any]],
    *,
    tool: str | None = None,
    route: str | None = None,
) -> dict[str, Any]:
    attempt = _next_attempt(stage)
    started = perf_counter()
    document_id = state["document_id"]
    log_workflow_event(
        20,
        "stage_started",
        document_id=document_id,
        stage=stage,
        attempt=attempt,
        tool=tool,
        route=route,
    )
    try:
        update = operation()
    except Exception as error:
        duration_ms = (perf_counter() - started) * 1_000
        log_workflow_event(
            40,
            "stage_failed",
            document_id=document_id,
            stage=stage,
            attempt=attempt,
            duration_ms=duration_ms,
            tool=tool,
            route=route,
            error=error,
        )
        raise

    duration_ms = (perf_counter() - started) * 1_000
    log_workflow_event(
        20,
        "stage_completed",
        document_id=document_id,
        stage=stage,
        attempt=attempt,
        duration_ms=duration_ms,
        tool=tool,
        route=route,
    )
    update.setdefault("workflow_events", []).append(
        make_workflow_event(
            stage,
            "completed",
            duration_ms=duration_ms,
            attempt=attempt,
        )
    )
    return update


def analyze_report(state: ClinicalWorkflowState) -> dict:
    return _run_stage(
        "analyze_report",
        state,
        lambda: {
            "analysis": extract_from_pdf(state["file_path"]),
            "agent_events": ["report_analysis"],
        },
        tool="extract_from_pdf",
    )


def retrieve_guidelines(state: ClinicalWorkflowState) -> dict:
    def operation() -> dict[str, Any]:
        analysis = state["analysis"]
        abnormal = ", ".join(
            f"{finding.test_name} {finding.flag}" for finding in analysis.abnormal_findings
        )
        query = f"{analysis.presenting_concern}. {abnormal}".strip()
        return {
            "citations": retrieve_the_docs(query),
            "agent_events": ["guideline_retrieval"],
        }

    return _run_stage(
        "retrieve_guidelines",
        state,
        operation,
        tool="retrieve_the_docs",
    )


def _summarise_for_route(state: ClinicalWorkflowState, review_route: str) -> dict:
    return _run_stage(
        "summarise",
        state,
        lambda: {
            "summary": summarise_and_generate_test(
                state["analysis"],
                state.get("citations", []),
                review_route=review_route,
                feedback_context=state.get("feedback_context", ""),
            ),
            "agent_events": ["summary"],
        },
        tool="summarise_and_generate_test",
    )


def summarise(state: ClinicalWorkflowState) -> dict:
    return _summarise_for_route(
        state, state.get("review_route", "standard_review")
    )


def summarise_urgent(state: ClinicalWorkflowState) -> dict:
    return _summarise_for_route(state, "urgent_review")


def summarise_standard(state: ClinicalWorkflowState) -> dict:
    return _summarise_for_route(state, "standard_review")


def recommend(state: ClinicalWorkflowState) -> dict:
    return _run_stage(
        "recommend",
        state,
        lambda: {
            "recommendations": recommend_follow_ups(
                state["analysis"],
                state.get("citations", []),
                state.get("summary"),
                feedback_context=state.get("feedback_context", ""),
            ),
            "agent_events": ["recommendation"],
        },
        tool="recommend_follow_ups",
    )


def route_review(state: ClinicalWorkflowState) -> dict:
    analysis = state.get("analysis")
    if analysis is None:
        raise ValueError("Report analysis is required before review routing")
    route = "urgent_review" if analysis.has_critical_finding else "standard_review"
    return _run_stage(
        "route_review",
        state,
        lambda: {"review_route": route},
        route=route,
    )


def prepare_urgent_review(state: ClinicalWorkflowState) -> dict:
    return _run_stage(
        "prepare_urgent_review",
        state,
        lambda: {},
        route="urgent_review",
    )


def prepare_standard_review(state: ClinicalWorkflowState) -> dict:
    return _run_stage(
        "prepare_standard_review",
        state,
        lambda: {},
        route="standard_review",
    )


def select_review_lane(state: ClinicalWorkflowState) -> str:
    return state.get("review_route", "standard_review")


def handle_failure(state: ClinicalWorkflowState, error: NodeError) -> Command:
    """Runs only once a node has exhausted its retry budget."""
    failed_error = error.error
    message = safe_error_message(failed_error)
    log_workflow_event(
        40,
        "stage_failed_exhausted",
        document_id=state.get("document_id", 0),
        stage=error.node,
        error=failed_error,
    )
    return Command(
        update={
            "failure": f"{error.node}: {message}",
            "agent_events": [f"{error.node}:failed"],
            "workflow_events": [
                make_workflow_event(
                    error.node,
                    "failed",
                    message=message,
                    error_type=type(failed_error).__name__,
                )
            ],
        },
        goto=END,
    )


@lru_cache(maxsize=1)
def get_clinical_graph():
    """Build the fan-out, routed, and sequential clinical workflow graph."""
    builder = StateGraph(ClinicalWorkflowState)
    for name, node in (
        ("analyze_report", analyze_report),
        ("retrieve_guidelines", retrieve_guidelines),
        ("route_review", route_review),
        ("prepare_urgent_review", prepare_urgent_review),
        ("prepare_standard_review", prepare_standard_review),
        ("summarise_urgent", summarise_urgent),
        ("summarise_standard", summarise_standard),
        ("recommend", recommend),
    ):
        builder.add_node(
            name, node, retry_policy=RETRY_POLICY, error_handler=handle_failure
        )

    builder.add_edge(START, "analyze_report")
    builder.add_edge("analyze_report", "retrieve_guidelines")
    builder.add_edge("analyze_report", "route_review")
    builder.add_conditional_edges(
        "route_review",
        select_review_lane,
        {
            "urgent_review": "prepare_urgent_review",
            "standard_review": "prepare_standard_review",
        },
    )
    builder.add_edge(
        ["retrieve_guidelines", "prepare_urgent_review"], "summarise_urgent"
    )
    builder.add_edge(
        ["retrieve_guidelines", "prepare_standard_review"], "summarise_standard"
    )
    builder.add_edge("summarise_urgent", "recommend")
    builder.add_edge("summarise_standard", "recommend")
    builder.add_edge("recommend", END)
    return builder.compile()


WorkflowUpdateCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


async def run_clinical_workflow(
    document_id: int,
    file_path: str,
    on_update: WorkflowUpdateCallback | None = None,
    feedback_context: str = "",
) -> ClinicalWorkflowState:
    """Run the graph and expose node updates for persistence and monitoring."""
    graph = get_clinical_graph()
    initial_state: ClinicalWorkflowState = {
        "document_id": document_id,
        "file_path": file_path,
        "agent_events": [],
        "workflow_events": [],
        "citations": [],
        "recommendations": [],
        "feedback_context": feedback_context,
        "failure": None,
    }
    final_state = dict(initial_state)
    attempt_token = _stage_attempts.set({})
    try:
        trace_config = {
            "run_name": "clinical_document_workflow",
            "tags": ["clinical-workflow"],
            "metadata": {"document_id": document_id},
        }
        async for update in graph.astream(
            initial_state,
            config=trace_config,
            stream_mode="updates",
        ):
            if not isinstance(update, dict):
                continue
            for node_name, node_update in update.items():
                if not isinstance(node_update, dict):
                    continue
                if on_update is not None:
                    try:
                        await on_update(node_name, node_update)
                    except Exception as callback_error:
                        log_workflow_event(
                            30,
                            "telemetry_callback_failed",
                            document_id=document_id,
                            stage=node_name,
                            error=callback_error,
                        )
                for key, value in node_update.items():
                    if key in {"agent_events", "workflow_events"}:
                        final_state[key] = [*final_state.get(key, []), *value]
                    else:
                        final_state[key] = value
        return final_state
    finally:
        _stage_attempts.reset(attempt_token)
