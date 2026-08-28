"""
CRONOS — web dashboard API.

Read-only FastAPI layer over the same SQLite database the Slack bot and MCP
server write to.  Serialization follows the project contract: fractions cross
the API boundary as "p/q" strings (never floats), quality tiers as their
enum values ("FULL" | "PARTIAL" | "MINIMAL" | "EMPTY").

Endpoints are async so every store call runs serialized on the event loop:
the shared sqlite3 connection (WAL, check_same_thread=False) is never touched
from two threads at once, and this layer never writes.  TraceStore.__init__
does run CREATE TABLE / migrations, so the connection itself is read-write —
the read-only guarantee is by construction (no write method is ever called).
"""

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from cronos import TraceStore
from cronos.narrator import Narrator

_REPO_ROOT = Path(__file__).resolve().parent.parent
_STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(db_path: str | None = None) -> FastAPI:
    if db_path is None:
        db_path = os.environ.get("CRONOS_DB_PATH", "cronos.db")
    store = TraceStore(db_path)

    app = FastAPI(title="CRONOS dashboard", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.store = store

    # ── Pages and static assets ───────────────────────────────────────────────

    @app.get("/", include_in_schema=False)
    async def landing() -> FileResponse:
        return FileResponse(_REPO_ROOT / "index.html", media_type="text/html")

    @app.get("/dashboard", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(_STATIC_DIR / "dashboard.html", media_type="text/html")

    @app.get("/cronos_architecture.svg", include_in_schema=False)
    async def architecture_svg() -> FileResponse:
        return FileResponse(_REPO_ROOT / "cronos_architecture.svg", media_type="image/svg+xml")

    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    # ── JSON API ──────────────────────────────────────────────────────────────

    @app.get("/api/traces")
    async def list_traces(
        agent_id: str = "",
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ) -> dict:
        agent = agent_id or None
        traces = store.get_recent_traces(agent_id=agent, limit=limit, offset=offset)
        for t in traces:
            t["chain_ok"] = bool(t["chain_ok"])
        return {
            "total": store.count_traces(agent_id=agent),
            "count": len(traces),
            "limit": limit,
            "offset": offset,
            "traces": traces,
        }

    @app.get("/api/traces/{trace_id}")
    async def trace_detail(trace_id: str) -> dict:
        trace = store.load_trace(trace_id)
        if trace is None:
            raise HTTPException(status_code=404, detail="trace not found")
        narrator = Narrator(trace)
        body = narrator.full()
        body["confidence"] = (
            f"{trace.confidence.numerator}/{trace.confidence.denominator}"
            if trace.confidence is not None else None
        )
        # Raw step timeline, same shape as the MCP cronos_explain_trace tool.
        body["steps"] = [
            {"kind": s.kind.value, "payload": s.payload, "timestamp": s.timestamp}
            for s in trace.steps
        ]
        body["natural"] = narrator.natural()
        return body

    @app.get("/api/verify")
    async def verify_chain() -> dict:
        # Recomputes every entry and steps hash — O(n) over all traces; fine at
        # the scale this dashboard targets.
        ok, errors = store.chain.verify()
        return {"chain_ok": ok, "entries": store.count_traces(), "errors": errors}

    @app.get("/api/stats")
    async def stats() -> dict:
        s = store.stats()
        ok, _ = store.chain.verify()
        return {
            "total": s["total"],
            "chain_ok": ok,
            "agents": s["per_agent"],
            "quality_counts": s["per_quality"],
            "cronos_version": __import__("cronos").__version__,
        }

    @app.get("/api/audit/export")
    async def audit_export() -> JSONResponse:
        ok, errors = store.chain.verify()
        body = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "chain_ok": ok,
            "errors": errors,
            "entries": store.chain.export(),
        }
        return JSONResponse(
            body,
            headers={"Content-Disposition": "attachment; filename=cronos_audit_export.json"},
        )

    return app


# Lazy module attribute: `uvicorn web.app:app` gets a real app, but merely
# importing this module (e.g. from tests that call create_app themselves)
# does not open or create a database file.
_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
