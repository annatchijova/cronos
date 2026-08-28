"""
CRONOS — test_web.py
Tests for the read-only web dashboard API (web/app.py).

The web layer is an optional extra; the core suite must pass without it.
"""

import sqlite3
from fractions import Fraction

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from cronos import CronosTracer, TraceStore  # noqa: E402
from web.app import create_app  # noqa: E402


def _seed(db_path: str) -> list[str]:
    """Three traces across two agents; returns trace_ids oldest-first."""
    store = TraceStore(db_path)
    ids = []

    # FULL trace: recall + tool + hypotheses/evidence, one discard.
    with CronosTracer(store, "support-resolver", "C1", "U1", "Fix ticket #842") as t:
        t.record_recall("M-22", "similar auth outage in 2025", score=Fraction(4, 5))
        t.call_tool("jira", "Open / Auth / High")
        t.add_hypothesis("auth_bug", "Expired auth tokens")
        t.add_hypothesis("cache_bug", "Stale cache entries")
        t.add_evidence("Jira confirms Auth category", supports="auth_bug")
        t.discard_hypothesis("cache_bug", "no cache errors in log")
        t.decide("apply auth token reset", Fraction(74, 100))
    ids.append(store.get_latest_trace().trace_id)

    # MINIMAL trace with over-confident decision → clamp warnings.
    with CronosTracer(store, "deploy-guard", "C1", "U1", "Approve deploy?") as t:
        t.add_hypothesis("safe", "Deploy looks safe")
        t.decide("approve", Fraction(95, 100))
    ids.append(store.get_latest_trace().trace_id)

    # Contradictory trace (Type A: evidence both supports and refutes).
    with CronosTracer(store, "deploy-guard", "C1", "U1", "Rollback needed?") as t:
        t.record_recall("M-7", "previous rollback")
        t.call_tool("grep", "errors found")
        t.add_hypothesis("bad_release", "Release caused errors")
        t.add_evidence("Error rate spiked", supports="bad_release")
        t.add_evidence("Errors predate release", refutes="bad_release")
        t.decide("rollback", Fraction(1, 2))
    ids.append(store.get_latest_trace().trace_id)
    return ids


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "web_test.db")


@pytest.fixture
def seeded(db_path):
    return _seed(db_path)


@pytest.fixture
def client(db_path, seeded):
    return TestClient(create_app(db_path))


class TestTraceList:
    def test_lists_all_traces(self, client):
        body = client.get("/api/traces").json()
        assert body["total"] == 3
        assert body["count"] == 3
        row = body["traces"][0]
        for key in ["trace_id", "agent_id", "objective", "decision", "confidence",
                    "closed_at", "entry_hash", "chain_ok", "quality", "diversity",
                    "contradiction_count"]:
            assert key in row

    def test_fractions_are_strings_not_floats(self, client, seeded):
        rows = client.get("/api/traces").json()["traces"]
        full = next(r for r in rows if r["trace_id"] == seeded[0])
        assert full["confidence"] == "37/50"  # Fraction(74,100) normalized
        assert full["quality"] == "FULL"
        assert full["diversity"] == "1/1"
        assert isinstance(full["chain_ok"], bool)

    def test_contradiction_count(self, client, seeded):
        rows = client.get("/api/traces").json()["traces"]
        contradictory = next(r for r in rows if r["trace_id"] == seeded[2])
        assert contradictory["contradiction_count"] >= 1

    def test_agent_filter(self, client):
        body = client.get("/api/traces", params={"agent_id": "deploy-guard"}).json()
        assert body["total"] == 2
        assert all(r["agent_id"] == "deploy-guard" for r in body["traces"])

    def test_unknown_agent_is_empty(self, client):
        body = client.get("/api/traces", params={"agent_id": "nope"}).json()
        assert body["total"] == 0
        assert body["traces"] == []

    def test_pagination(self, client):
        all_rows = client.get("/api/traces").json()["traces"]
        page = client.get("/api/traces", params={"limit": 1, "offset": 1}).json()
        assert page["count"] == 1
        assert page["traces"][0]["trace_id"] == all_rows[1]["trace_id"]

    def test_limit_is_clamped(self, client):
        assert client.get("/api/traces", params={"limit": 0}).status_code == 422
        assert client.get("/api/traces", params={"limit": 101}).status_code == 422


class TestTraceDetail:
    def test_full_narrator_payload(self, client, seeded):
        body = client.get(f"/api/traces/{seeded[0]}").json()
        assert body["decision"] == "apply auth token reset"
        assert body["confidence_pct"] == "74%"
        assert body["confidence"] == "37/50"
        hyps = {h["label"]: h for h in body["hypotheses"]}
        assert hyps["cache_bug"]["status"] == "discarded"
        assert hyps["cache_bug"]["discard_reason"] == "no cache errors in log"
        assert hyps["auth_bug"]["status"] == "kept"
        assert body["evidence"][0]["supports"] == "auth_bug"
        assert body["memories"][0]["id"] == "M-22"
        assert body["tools"][0]["name"] == "jira"
        assert body["devils_advocate"]
        assert body["natural"].startswith("Because ")

    def test_raw_steps_timeline(self, client, seeded):
        body = client.get(f"/api/traces/{seeded[0]}").json()
        assert body["steps"][0]["kind"] == "objective"
        assert body["steps"][-1]["kind"] == "decision"
        assert all({"kind", "payload", "timestamp"} <= set(s) for s in body["steps"])

    def test_clamp_warnings_surface(self, client, seeded):
        body = client.get(f"/api/traces/{seeded[1]}").json()
        assert body["quality"] == "MINIMAL"
        assert body["confidence_warnings"]

    def test_contradictions_surface(self, client, seeded):
        body = client.get(f"/api/traces/{seeded[2]}").json()
        assert any(c.startswith("Type A") for c in body["contradictions"])

    def test_unknown_trace_is_404(self, client):
        resp = client.get("/api/traces/no-such-id")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "trace not found"


class TestVerify:
    def test_intact_chain_verifies(self, client):
        body = client.get("/api/verify").json()
        assert body["chain_ok"] is True
        assert body["entries"] == 3
        assert body["errors"] == []

    def test_tampered_chain_is_detected(self, client, db_path, seeded):
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE traces SET decision = 'FORGED' WHERE trace_id = ?", (seeded[0],)
        )
        conn.execute(
            "UPDATE trace_chain SET decision = 'FORGED' WHERE trace_id = ?", (seeded[0],)
        )
        conn.commit()
        conn.close()

        body = client.get("/api/verify").json()
        assert body["chain_ok"] is False
        assert body["errors"]


class TestStats:
    def test_stats_shape(self, client):
        body = client.get("/api/stats").json()
        assert body["total"] == 3
        assert body["chain_ok"] is True
        agents = {a["agent_id"]: a["count"] for a in body["agents"]}
        assert agents == {"support-resolver": 1, "deploy-guard": 2}
        assert body["quality_counts"]["FULL"] == 2
        assert body["quality_counts"]["MINIMAL"] == 1
        assert body["cronos_version"] == "0.1.0"


class TestAuditExport:
    def test_export_downloads_chain(self, client):
        resp = client.get("/api/audit/export")
        assert "attachment" in resp.headers["content-disposition"]
        body = resp.json()
        assert body["chain_ok"] is True
        assert len(body["entries"]) == 3
        for entry in body["entries"]:
            assert entry["prev_hash"]
            assert entry["entry_hash"]


class TestPages:
    def test_landing_serves(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_dashboard_serves(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_dashboard_js_serves(self, client):
        assert client.get("/static/dashboard.js").status_code == 200

    def test_architecture_svg_serves(self, client):
        resp = client.get("/cronos_architecture.svg")
        assert resp.status_code == 200
        assert "svg" in resp.headers["content-type"]
