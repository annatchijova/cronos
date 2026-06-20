"""
CRONOS — test_store.py
Tests for TraceStore persistence layer.
"""

import pytest
from fractions import Fraction

from cronos import CronosTracer, TraceStore
from cronos.models import Trace, StepKind


@pytest.fixture
def store(tmp_path):
    return TraceStore(str(tmp_path / "test.db"))


def _make_trace(store, agent_id="agent-A", channel="C1", user="U1",
                objective="Do X", decision="Done", confidence=Fraction(74, 100)):
    with CronosTracer(store, agent_id, channel, user, objective) as t:
        t.record_recall("M-1", "relevant memory", score=Fraction(80, 100))
        t.call_tool("jira", "Open / Auth / High")
        t.add_hypothesis("h1", "Auth bug")
        t.add_hypothesis("h2", "Cache bug")
        t.add_evidence("Jira says Auth", supports="h1")
        t.discard_hypothesis("h2", "No cache errors")
        t.decide(decision, confidence)
    return store.get_latest_trace()


class TestStoreBasic:
    def test_save_and_load_roundtrip(self, store):
        trace = _make_trace(store)
        loaded = store.load_trace(trace.trace_id)
        assert loaded is not None
        assert loaded.trace_id == trace.trace_id
        assert loaded.objective == "Do X"
        assert loaded.decision == "Done"
        assert loaded.confidence == Fraction(74, 100)

    def test_load_nonexistent_returns_none(self, store):
        assert store.load_trace("does-not-exist") is None

    def test_steps_round_trip(self, store):
        trace = _make_trace(store)
        loaded = store.load_trace(trace.trace_id)
        kinds = [s.kind for s in loaded.steps]
        assert StepKind.RECALL in kinds
        assert StepKind.TOOL in kinds
        assert StepKind.HYPOTHESIS in kinds
        assert StepKind.DISCARD in kinds
        assert StepKind.EVIDENCE in kinds
        assert StepKind.DECISION in kinds

    def test_step_order_preserved(self, store):
        trace = _make_trace(store)
        loaded = store.load_trace(trace.trace_id)
        kinds = [s.kind for s in loaded.steps]
        # OBJECTIVE always first
        assert kinds[0] == StepKind.OBJECTIVE
        # DECISION always last
        assert kinds[-1] == StepKind.DECISION

    def test_chain_ok_after_save(self, store):
        trace = _make_trace(store)
        loaded = store.load_trace(trace.trace_id)
        assert loaded.chain_ok is True
        assert loaded.entry_hash is not None

    def test_confidence_fraction_precision(self, store):
        """Fraction 74/100 must survive the p/q string round-trip exactly."""
        trace = _make_trace(store, confidence=Fraction(74, 100))
        loaded = store.load_trace(trace.trace_id)
        assert loaded.confidence == Fraction(74, 100)
        assert loaded.confidence.numerator == 37   # auto-reduced: 74/100 = 37/50
        assert loaded.confidence.denominator == 50

    def test_confidence_fraction_irreducible(self, store):
        """Fraction 71/100 is already irreducible."""
        trace = _make_trace(store, confidence=Fraction(71, 100))
        loaded = store.load_trace(trace.trace_id)
        assert loaded.confidence == Fraction(71, 100)


class TestStoreQueries:
    def test_get_latest_trace(self, store):
        _make_trace(store, objective="First")
        _make_trace(store, objective="Second")
        latest = store.get_latest_trace()
        assert latest.objective == "Second"

    def test_get_latest_trace_by_agent(self, store):
        _make_trace(store, agent_id="agent-A", objective="A1")
        _make_trace(store, agent_id="agent-B", objective="B1")
        _make_trace(store, agent_id="agent-A", objective="A2")
        latest_a = store.get_latest_trace(agent_id="agent-A")
        assert latest_a.objective == "A2"
        latest_b = store.get_latest_trace(agent_id="agent-B")
        assert latest_b.objective == "B1"

    def test_get_latest_trace_none_when_empty(self, store):
        assert store.get_latest_trace() is None

    def test_get_recent_traces_limit(self, store):
        for i in range(5):
            _make_trace(store, objective=f"Task {i}")
        recent = store.get_recent_traces(limit=3)
        assert len(recent) == 3

    def test_get_recent_traces_by_agent(self, store):
        _make_trace(store, agent_id="agent-A")
        _make_trace(store, agent_id="agent-B")
        _make_trace(store, agent_id="agent-A")
        recent = store.get_recent_traces(agent_id="agent-A")
        assert all(r["agent_id"] == "agent-A" for r in recent)
        assert len(recent) == 2

    def test_get_recent_traces_has_required_keys(self, store):
        _make_trace(store)
        recent = store.get_recent_traces()
        assert len(recent) == 1
        r = recent[0]
        for key in ["trace_id", "agent_id", "objective", "decision", "confidence",
                    "closed_at", "entry_hash", "chain_ok"]:
            assert key in r

    def test_count_traces(self, store):
        assert store.count_traces() == 0
        _make_trace(store, agent_id="a1")
        _make_trace(store, agent_id="a1")
        _make_trace(store, agent_id="a2")
        assert store.count_traces() == 3
        assert store.count_traces(agent_id="a1") == 2
        assert store.count_traces(agent_id="a2") == 1

    def test_chain_verification_passes_after_multiple_saves(self, store):
        for i in range(4):
            _make_trace(store, objective=f"Task {i}")
        ok, errors = store.chain.verify()
        assert ok is True
        assert errors == []
