# CRONOS — Changelog

All notable changes documented here.

---

## [0.1.0] — 2026-06-20

Initial implementation of CRONOS, built for the Slack Agent Builder Challenge.

### Architecture

- **CronosTracer** — Context-manager SDK. Records steps *while the agent runs*: objective, recalls, tool calls, hypotheses, discards, evidence, decision.
- **TraceStore** — SQLite WAL persistence. Steps + header + chain entry in a single atomic commit.
- **TraceChain** — SHA-256 tamper-evident hash chain. Each entry chains to the previous; any retroactive modification breaks downstream hashes.
- **Narrator** — Rule-based NLG. Produces short card (for inline posting), full breakdown (for `/cronos explain`), and natural language prose — no LLM.
- **Slack layer** — Bolt async app. `/cronos explain | trace | audit | status`. Block Kit formatters with `_escape()` on all user-supplied text.
- **Demo agent** — `DemoAgent` wraps a deterministic support ticket resolver using the SDK. Demonstrates the full cycle: recall → tool → hypothesis → evidence → discard → decide → post trace card.
- **Confidence** — `fractions.Fraction` throughout; zero floats in the scoring path.
- **Tests** — 104 tests across 5 files: tracer, chain, store, narrator, output.

### Design decisions

- `decide()` raises `TypeError` if passed a float — enforces Fraction discipline at the API boundary.
- `TraceChain.append()` never calls `conn.commit()` — callers own the transaction (engine.py issues the single commit that covers chain + header + steps).
- `_escape()` applied to all user-supplied text in Block Kit payloads (XSS via Slack mrkdwn).
- `CronosTracer.__exit__` stores the trace even when the agent code raises — the partial trace is forensically valuable.
- `Fraction(74, 100)` auto-reduces to `37/50`; the store round-trips `p/q` string and reconstructs the exact Fraction — equality holds.
