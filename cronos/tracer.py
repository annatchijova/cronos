"""
CRONOS — CronosTracer
Context-manager SDK for instrumenting agent decision cycles.

The tracer records steps *while* the agent runs — not as a post-hoc
rationalization. Every recall, tool call, hypothesis, discard, and piece
of evidence is timestamped as it happens. When the context exits, the
full trace is sealed with a SHA-256 chain entry and written atomically.

Usage
-----
    from fractions import Fraction
    from cronos import CronosTracer, TraceStore

    store = TraceStore("cronos.db")

    with CronosTracer(store, agent_id="ticket-resolver",
                      channel_id="C123", user_id="U456",
                      objective="Resolve ticket #842") as t:

        t.record_recall("M-22",  "Auth timeout in service A", score=Fraction(91, 100))
        t.record_recall("M-81",  "Failed login cascade",      score=Fraction(74, 100))
        t.call_tool("jira",   "ticket #842 → Open / Auth / High")
        t.call_tool("github", "2 commits in auth-service match pattern")
        t.add_hypothesis("auth_bug",   "Authentication token expired")
        t.add_hypothesis("cache_bug",  "Cache invalidation failure")
        t.add_evidence("Jira confirms Auth category",          supports="auth_bug")
        t.add_evidence("No cache errors in Jira log",         refutes="cache_bug")
        t.discard_hypothesis("cache_bug", "No cache errors in Jira log")
        t.decide("Apply auth token reset", confidence=Fraction(74, 100))

The trace is accessible via store.get_latest_trace() and via /cronos explain.
"""

from datetime import datetime, timezone
from fractions import Fraction
from typing import Optional
from uuid import uuid4

from .models import Trace, TraceStep, StepKind
from .store import TraceStore


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class CronosTracer:
    """
    Records the decision trace of a single agent action cycle.
    Must be used as a context manager.
    The trace is sealed and stored atomically on __exit__.
    """

    def __init__(
        self,
        store: TraceStore,
        agent_id: str,
        channel_id: str,
        user_id: str,
        objective: str,
    ) -> None:
        self._store = store
        self.trace = Trace(
            trace_id=str(uuid4()),
            agent_id=agent_id,
            channel_id=channel_id,
            user_id=user_id,
            objective=objective,
            started_at=_now(),
        )
        # Objective is always the first step — recorded immediately
        self.trace.steps.append(TraceStep(
            kind=StepKind.OBJECTIVE,
            payload={"objective": objective},
            timestamp=self.trace.started_at,
        ))

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "CronosTracer":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.trace.closed_at = _now()
        self.trace.closed = True
        if not self.trace.decision:
            # Implicit "no decision" if the context exited without decide()
            self.trace.decision = "(no decision recorded)"
            self.trace.confidence = Fraction(0)
        self._store.save_trace(self.trace)
        return False  # never suppress exceptions

    # ── Recording API ─────────────────────────────────────────────────────────

    def record_recall(
        self,
        memory_id: str,
        summary: str,
        score: Optional[Fraction] = None,
    ) -> None:
        """Record a memory retrieval from the episodic/semantic store."""
        payload: dict = {"memory_id": memory_id, "summary": summary}
        if score is not None:
            payload["score"] = f"{score.numerator}/{score.denominator}"
        self.trace.steps.append(TraceStep(StepKind.RECALL, payload, _now()))

    def call_tool(self, tool_name: str, result_summary: str) -> None:
        """Record an external tool call and its result summary."""
        self.trace.steps.append(TraceStep(
            StepKind.TOOL,
            {"tool": tool_name, "result": result_summary},
            _now(),
        ))

    def add_hypothesis(self, label: str, description: str) -> None:
        """Register a hypothesis under active consideration."""
        self.trace.steps.append(TraceStep(
            StepKind.HYPOTHESIS,
            {"label": label, "description": description},
            _now(),
        ))

    def discard_hypothesis(self, label: str, reason: str) -> None:
        """Mark a hypothesis as discarded and record the reason."""
        self.trace.steps.append(TraceStep(
            StepKind.DISCARD,
            {"label": label, "reason": reason},
            _now(),
        ))

    def add_evidence(
        self,
        text: str,
        supports: Optional[str] = None,
        refutes: Optional[str] = None,
    ) -> None:
        """
        Record a piece of evidence.

        Parameters
        ----------
        text:     human-readable fact
        supports: label of the hypothesis this evidence supports (optional)
        refutes:  label of the hypothesis this evidence refutes (optional)
        """
        payload: dict = {"text": text}
        if supports:
            payload["supports"] = supports
        if refutes:
            payload["refutes"] = refutes
        self.trace.steps.append(TraceStep(StepKind.EVIDENCE, payload, _now()))

    def decide(self, decision: str, confidence: Fraction) -> None:
        """
        Record the final decision and confidence score.
        confidence must be a fractions.Fraction in [0, 1].
        """
        if not isinstance(confidence, Fraction):
            raise TypeError(
                "confidence must be fractions.Fraction — "
                f"got {type(confidence).__name__}. CRONOS uses no floats."
            )
        self.trace.decision = decision
        self.trace.confidence = confidence
        self.trace.steps.append(TraceStep(
            StepKind.DECISION,
            {
                "decision":   decision,
                "confidence": f"{confidence.numerator}/{confidence.denominator}",
            },
            _now(),
        ))
