"""
CRONOS — SHA-256 tamper-evident trace chain.
Adapted from the CORVUS AuditChain (VIGÍA AI Collective, Apache 2.0).

Each closed trace appends one entry whose SHA-256 hash incorporates:
  - all trace metadata (agent_id, objective, decision, confidence)
  - the hash of the preceding entry

Any retroactive modification of a trace breaks every subsequent hash.
The chain can be exported and verified independently of the running process.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def _compute_entry_hash(
    timestamp: str,
    trace_id: str,
    agent_id: str,
    objective: str,
    decision: str,
    confidence: str,
    prev_hash: str,
) -> str:
    canonical: dict[str, Any] = {
        "timestamp":  timestamp,
        "trace_id":   trace_id,
        "agent_id":   agent_id,
        "objective":  objective,
        "decision":   decision,
        "confidence": confidence,
        "prev_hash":  prev_hash,
    }
    raw = (
        json.dumps(canonical, sort_keys=True, ensure_ascii=False) + prev_hash
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class TraceChain:
    """
    Append-only SHA-256 hash chain backed by SQLite.
    One row per closed Trace. Callers own the transaction and must commit.
    """

    _GENESIS_HASH = "0" * 64

    def __init__(self, db_conn) -> None:
        self._conn = db_conn
        self._ensure_table()

    def _ensure_table(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS trace_chain (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                trace_id    TEXT    NOT NULL UNIQUE,
                agent_id    TEXT    NOT NULL,
                objective   TEXT    NOT NULL,
                decision    TEXT    NOT NULL,
                confidence  TEXT    NOT NULL,
                prev_hash   TEXT    NOT NULL,
                entry_hash  TEXT    NOT NULL UNIQUE
            )
        """)
        self._conn.commit()

    def _get_last_hash(self) -> str:
        row = self._conn.execute(
            "SELECT entry_hash FROM trace_chain ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else self._GENESIS_HASH

    def append(
        self,
        trace_id: str,
        agent_id: str,
        objective: str,
        decision: str,
        confidence: str,   # fraction string "p/q"
    ) -> str:
        """
        Append a new trace to the chain.
        Returns the SHA-256 hash of the new entry.
        NOTE: does NOT commit — caller owns the transaction.
        """
        timestamp = datetime.now(tz=timezone.utc).isoformat()
        prev_hash = self._get_last_hash()
        entry_hash = _compute_entry_hash(
            timestamp, trace_id, agent_id, objective, decision, confidence, prev_hash
        )
        self._conn.execute("""
            INSERT INTO trace_chain
                (timestamp, trace_id, agent_id, objective, decision,
                 confidence, prev_hash, entry_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, trace_id, agent_id, objective, decision,
              confidence, prev_hash, entry_hash))
        return entry_hash

    def verify(self) -> tuple[bool, list[str]]:
        """
        Recompute all hashes and verify chain linkage.
        Returns (True, []) if intact; (False, [error…]) otherwise.
        """
        rows = self._conn.execute("""
            SELECT id, timestamp, trace_id, agent_id, objective,
                   decision, confidence, prev_hash, entry_hash
            FROM trace_chain ORDER BY id ASC
        """).fetchall()

        errors: list[str] = []
        expected_prev = self._GENESIS_HASH

        for row in rows:
            (id_, ts, trace_id, agent_id, obj,
             dec, conf, prev_hash, stored_hash) = row

            if prev_hash != expected_prev:
                errors.append(
                    f"Entry {id_} ({trace_id[:8]}…): "
                    f"prev_hash mismatch — chain is broken here"
                )

            computed = _compute_entry_hash(
                ts, trace_id, agent_id, obj, dec, conf, prev_hash
            )
            if computed != stored_hash:
                errors.append(
                    f"Entry {id_} ({trace_id[:8]}…): "
                    f"hash mismatch — entry may have been tampered with. "
                    f"Stored: {stored_hash[:16]}…, Computed: {computed[:16]}…"
                )
            expected_prev = stored_hash

        return len(errors) == 0, errors

    def export(self) -> list[dict]:
        """Export all chain entries in chronological order."""
        rows = self._conn.execute("""
            SELECT id, timestamp, trace_id, agent_id, objective,
                   decision, confidence, prev_hash, entry_hash
            FROM trace_chain ORDER BY id ASC
        """).fetchall()
        keys = [
            "id", "timestamp", "trace_id", "agent_id", "objective",
            "decision", "confidence", "prev_hash", "entry_hash",
        ]
        return [dict(zip(keys, row)) for row in rows]
