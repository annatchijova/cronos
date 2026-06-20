# CRONOS

![Tests](https://img.shields.io/badge/tests-104%20passed-brightgreen) ![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![License](https://img.shields.io/badge/license-Apache%202.0-blue) ![Hackathon](https://img.shields.io/badge/Slack%20Agent%20Builder%20Challenge-2026-blueviolet)

**Black Box Recorder for AI Agents.**

Most agents say: *"I searched for relevant information and decided to respond X."*
That's rationalization after the fact — not traceability.

CRONOS records the decision process **while it happens**: which memories were retrieved, which tools were called, which hypotheses were generated, which were discarded and why, and what confidence score drove the final decision. Every trace is sealed with a SHA-256 hash chain. Any retroactive modification breaks the chain.

> Built for the [Slack Agent Builder Challenge](https://slackhack.devpost.com) · Track: New Slack Agent

---

## The Problem

Agents take actions. When they're wrong, nobody knows why.

```
Input → LLM → Output
```

That's a black box. You can ask it to explain itself, but the explanation is generated *after* the decision — it's not a record of what actually happened.

CRONOS instruments the decision cycle *from inside*, producing a forensic trace you can audit, export, and verify.

---

## Architecture

```
Agent Decision Cycle (any Slack agent)
        │
        ▼
┌────────────────────────────────────┐
│   CronosTracer (SDK)               │
│   context manager wrapping the     │
│   agent's reasoning loop           │
│                                    │
│   t.record_recall(memory_id, …)    │  ← what it remembered
│   t.call_tool(tool_name, result)   │  ← what it looked up
│   t.add_hypothesis(label, …)       │  ← what it considered
│   t.discard_hypothesis(label, …)   │  ← what it rejected
│   t.add_evidence(text, supports=…) │  ← what confirmed/denied
│   t.decide(decision, confidence)   │  ← what it chose
└─────────────┬──────────────────────┘
              │  Trace object
              ▼
┌─────────────────────────────────────┐
│   TraceStore (SQLite WAL)           │
│   + TraceChain (SHA-256)            │
│   Atomic commit: steps + header     │
│   + chain entry in one transaction  │
└─────────────┬───────────────────────┘
              │
      ┌───────┴───────────────────┐
      │                           │
      ▼                           ▼
[trace card]              [/cronos explain]
posted inline             full breakdown on demand
with agent reply          memories · tools · hypotheses
                          evidence · natural language prose
```

---

## What a CRONOS trace looks like

**Inline card** (posted after every agent action):

```
🔭 CRONOS TRACE · support-resolver
Decision: Rotate auth token and restart auth-service

Why?
✓ Retrieved 2 memories (M-22, M-81)
✓ Found matching incident — Auth timeout in service A — 2024-03 incident
✓ jira → ticket #442 → Open / Auth / High
✓ Jira confirms Auth category
✗ cache_bug discarded — No cache errors in Jira or GitHub

Confidence: [███████░░░] 74%  |  ✅ Chain verified · 7ab31fe
/cronos explain 7ab31fe
```

**`/cronos explain`** (full breakdown):

```
MEMORIES RECALLED
• M-22 — Auth timeout in service A — 2024-03 incident (score 91/100)
• M-81 — Failed login cascade — 2024-11 incident (score 74/100)

TOOL CALLS
• jira → ticket #442 → Open / Auth / High
• github → 3 commits in auth-service match pattern

HYPOTHESES
✓ auth_bug — Authentication token expired
✗ cache_bug — Cache invalidation failure (discarded: No cache errors in Jira)

IN PLAIN LANGUAGE
Because I retrieved 2 memories (M-22, M-81); jira returned: ticket #442 →
Open / Auth / High; evidence supported auth_bug: Jira confirms Auth category;
I discarded cache_bug because no cache errors in Jira or GitHub —
I decided to rotate auth token and restart auth-service (high confidence, 74%).
```

---

## SDK Usage

```python
from fractions import Fraction
from cronos import CronosTracer, TraceStore

store = TraceStore("cronos.db")

with CronosTracer(store, agent_id="my-agent",
                  channel_id=channel, user_id=user,
                  objective="Resolve ticket #442") as t:

    t.record_recall("M-22", "Auth timeout 2024", score=Fraction(91, 100))
    t.call_tool("jira", "ticket #442 → Open / Auth / High")
    t.add_hypothesis("auth_bug",  "Authentication token expired")
    t.add_hypothesis("cache_bug", "Cache invalidation failure")
    t.add_evidence("Jira confirms Auth category", supports="auth_bug")
    t.discard_hypothesis("cache_bug", "No cache errors in Jira log")
    t.decide("Rotate auth token", confidence=Fraction(74, 100))
# Trace is sealed and stored when the `with` block exits.
# entry_hash, chain_ok, and closed_at are set automatically.
```

---

## Slack Commands

```
/cronos explain [trace_id]   Full explanation of last (or specific) trace
/cronos trace [agent_id]     List recent traces, optionally filtered by agent
/cronos audit                Verify and export the SHA-256 audit chain
/cronos status               Overview of all agents and trace counts
/cronos help                 Command reference
```

---

## Key Design Decisions

**Records while it happens, not after** — The tracer is a context manager wrapping the agent's actual reasoning loop. Steps are timestamped as they occur. `/cronos explain` is not a post-hoc LLM rationalization — it's a replay of what actually happened.

**Zero floats in confidence scoring** — All `confidence` values are `fractions.Fraction`. Bit-for-bit reproducible. A 74% confidence is stored as `37/50`, reloaded as `37/50`, and displayed as `74%` — no floating-point drift across Python versions.

**Tamper-evident chain** — Every closed trace appends one entry to a SHA-256 hash chain. Each entry's hash incorporates the previous entry's hash + the trace's metadata. Retroactive modification breaks every subsequent hash. Exportable and verifiable independently of the running process.

**One atomic commit** — Steps + trace header + chain entry all land in a single `conn.commit()`. Either everything is stored or nothing is.

---

## Project Structure

```
cronos/
├── cronos/
│   ├── models.py       Trace, TraceStep, StepKind dataclasses
│   ├── tracer.py       CronosTracer SDK (context manager)
│   ├── chain.py        SHA-256 tamper-evident hash chain
│   ├── store.py        SQLite WAL persistence
│   └── narrator.py     Natural language synthesis (no LLM)
├── slack/
│   ├── bot.py          Bolt async app factory
│   ├── commands.py     /cronos subcommand handlers
│   └── output.py       Block Kit formatters
├── demo/
│   └── agent.py        Demo support ticket resolver using the SDK
├── tests/
│   ├── test_tracer.py   (28 tests)
│   ├── test_chain.py    (15 tests)
│   ├── test_store.py    (16 tests)
│   ├── test_narrator.py (27 tests)
│   └── test_output.py   (18 tests)
├── main.py             Entry point
├── config.py           Environment config
└── slack_manifest.yml  Import directly at api.slack.com/apps
```

---

## Setup

### 1. Create the Slack app

Import `slack_manifest.yml` at [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From a manifest**.

Enable **Socket Mode** and generate an App-Level Token with `connections:write`.

### 2. Configure environment

```bash
cp .env.example .env
# Fill in SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_SIGNING_SECRET
```

### 3. Run

**Local:**
```bash
pip install -e ".[dev]"
python3 main.py
```

**Docker:**
```bash
docker compose up
```

---

## Tests

```bash
pip install -e ".[dev]"
pytest                   # all 104 tests
pytest tests/test_tracer.py    # SDK recording
pytest tests/test_chain.py     # hash chain integrity
pytest tests/test_store.py     # persistence
pytest tests/test_narrator.py  # NL synthesis
pytest tests/test_output.py    # Block Kit formatters
pytest --cov=cronos --cov-report=term-missing
```

---

## License

Apache 2.0
