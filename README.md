# CRONOS

![Tests](https://img.shields.io/badge/tests-104%20passed-brightgreen) ![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![License](https://img.shields.io/badge/license-Apache%202.0-blue)

**Black Box Recorder for AI Agents.**

Most agents say: *"I searched for relevant information and decided to respond X."*
That's rationalization after the fact — not traceability.

CRONOS records the decision process **while it happens**: which memories were retrieved, which tools were called, which hypotheses were generated, which were discarded and why, and what confidence score drove the final decision. Every trace is sealed with a SHA-256 hash chain. Any retroactive modification breaks the chain.

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
Agent Decision Cycle (any agent)
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
├── web/
│   ├── app.py          Read-only FastAPI dashboard + JSON API
│   └── static/         Dashboard SPA (vanilla JS, no build step)
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

## Real-World Example

CRONOS isn't just a demo harness — it's used to audit real coding agents on real repositories. Below is an unedited trace from an actual session: a Claude Code agent auditing [REBOUND](https://github.com/annatchijova/rebound), a biomimetic sonar-navigation project for visually impaired users.

What makes this trace worth reading: the operator (me) has a strict global instruction that forbids floats anywhere near a decision or scoring path — `fractions.Fraction` only. REBOUND's memory agent legitimately uses `float` weights for Bayesian display priors, a cosmetic layer with no sealed/hashed output. Without a forensic record, a rule-following agent can misapply a strict instruction out of context and "fix" code that was never broken — in this case, code that runs on my mother's project. CRONOS captured the moment the agent raised `memory_agent_float_leak` as a hypothesis, checked it against the live code, found the floats were intentional and out of scope for the no-float invariant, and *discarded* the hypothesis with a documented reason instead of acting on it. The trace is the evidence that the correct call was reasoned, not lucky.

```markdown
# Cronos Audit Trail — REBOUND Code Audit
<!-- trace_id: d1a0de7a-0516-49d6-84d1-f74324afacd3 -->

| Field | Value |
|-------|-------|
| Trace ID | `d1a0de7a-0516-49d6-84d1-f74324afacd3` |
| Agent | `claude-code-auditor` |
| Started | 2026-07-09T01:56:09 UTC |
| Closed | 2026-07-09T01:59:36 UTC |
| Quality | PARTIAL (2/3 observation groups) |
| Confidence | 17/20 (submitted 22/25 — capped by diversity ceiling) |
| Chain hash | `97533588e6d332701ba17a908f5f0d8676d036db392fba9804afae38023bb8d3` |
| Chain integrity | OK |
| Cronos version | 0.1.0 |

---

## Objective

Audit the /rebound project (`/home/labestiadevigia/rebound`): read the source, identify at least one improvement, implement it using appropriate skills.

---

## Step-by-step trace

### 1. Tool — Glob (01:56:22 UTC)

Found `rebound/` directory, `rebound.zip`, HTML files, JSX file, PEM keys, demo video. No skill file named rebound in `~/.claude`.

### 2. Tool — Glob+ls (01:56:28 UTC)

`rebound/` is a full project: `src/`, `tests/`, `models/`, `docs/`, `frontend/`, `Dockerfile`, `requirements`, `CHANGELOG`, `AUDITORIA_ADVERSARIAL.md`, `LIMITATIONS.md`.

### 3. Tool — Read+Bash (01:56:38 UTC)

REBOUND: biomimetic sonar nav for visually impaired. Python FastAPI backend + React PWA. Modules: `signal/`, `features/`, `models/`, `memory/`, `cloud/`. README explicitly documents hardcoded `user_action="advance"` bug in `Live.jsx` as known gap.

### 4. Hypothesis registered: `hardcoded_user_action` (01:56:42 UTC)

`Live.jsx` always sends `user_action="advance"` regardless of real user behavior, breaking the Bayesian personalization pipeline. README explicitly calls this out as known gap. Likely the most impactful improvement.

### 5. Hypothesis registered: `api_server_security_gap` (01:56:42 UTC)

`api_server.py` may have security or correctness issues not covered by the prior adversarial audit (`AUDITORIA_ADVERSARIAL.md` already exists, so some findings were fixed — need to check what remains).

### 6. Hypothesis registered: `memory_agent_float_leak` (01:56:44 UTC)

Memory agent uses Bayesian priors and multipliers. If floats enter sealed/scored paths instead of staying in cosmetic layer, that's a determinism/correctness defect per the `CLAUDE.md` invariants.

### 7. Tool — Read api_server.py + agent.py (01:57:06 UTC)

`api_server.py`: solid security hardening, semaphore, LRU eviction, token auth, user_id validation.
`agent.py`: **CRITICAL CODE DUPLICATION** — `MockQwenMemoryAgent._call_qwen` (lines 402-473) is a near-identical copy of `_mock_response_from_context` (lines 476-537). The helper was clearly written to deduplicate but `MockQwenMemoryAgent` was never refactored to use it. Also: `apply_memory_ops` normalizes `class_weights` with float division in the profile update path.

### 8. Evidence — supports `hardcoded_user_action` (01:57:38 UTC)

`Live.jsx` line 115: `user_action` hardcoded to `"advance"`. README explicitly documents this as known gap — integration work remaining, not a capability the system lacks.
*(negation detected in text)*

### 9. Evidence — supports `api_server_security_gap` (01:57:38 UTC)

`agent.py`: `MockQwenMemoryAgent._call_qwen` (lines 402-473) is a ~60-line near-duplicate of `_mock_response_from_context` (lines 476-537). `MockAsyncQwenMemoryAgent` already delegates to the helper (line 543), but `MockQwenMemoryAgent` was never refactored. Dead duplication with live sister function.

### 10. Evidence — refutes `api_server_security_gap` (01:57:40 UTC)

`api_server.py` security hardening is comprehensive: token auth, user_id regex, CORS scoped, semaphore, LRU eviction, class_name whitelist, multiplier clamp. No new gaps found beyond what the adversarial audit already addressed.
*(negation detected in text)*

### 11. Evidence — refutes `memory_agent_float_leak` (01:57:42 UTC)

`profile.py`: `class_weights` is `list[float]` by design — this is a cosmetic/display path, not a sealed hash. Float arithmetic here is intentional. The Cronos/Corvus pattern does not apply to REBOUND's Bayesian weights.
*(negation detected in text)*

### 12. Discard — `api_server_security_gap` (01:57:48 UTC)

**Reason:** Security hardening is thorough and matches the adversarial audit changelog. What was found instead is code duplication in the mock agent layer, not a security gap.

### 13. Discard — `memory_agent_float_leak` (01:57:48 UTC)

**Reason:** `class_weights` are floats by intentional design (Bayesian display priors, not sealed hashes). REBOUND has no determinism-seal invariant equivalent to Cronos/Corvus.

### 14. Decision sealed (01:59:36 UTC)

`MockQwenMemoryAgent._call_qwen` replaced with one-line delegation to `_mock_response_from_context`, eliminating ~60 lines of duplicated logic. Both `api_server_security_gap` and `memory_agent_float_leak` hypotheses were refuted against the live code. Patch applied surgically with backup, AST verification, and full test suite (90/90 pass).

---

## Hypotheses summary

| Label | Status | Outcome |
|-------|--------|---------|
| `hardcoded_user_action` | Active — known gap | Confirmed by `Live.jsx:115`. Documented in README; requires mobile UX work, out of scope for this session. |
| `api_server_security_gap` | Discarded | Refuted: security hardening is comprehensive. Reclassified finding as code duplication. |
| `memory_agent_float_leak` | Discarded | Refuted: `class_weights` are display-layer floats by design, not sealed paths. |

---

## Decision

**Fix applied:** `src/memory/agent.py` — `MockQwenMemoryAgent._call_qwen` collapsed to single delegation call.

**Commit:** `4d3abb3` — `Remove duplicate mock response logic from MockQwenMemoryAgent`
**Tests:** 90/90 pass
**Patch method:** surgical (anchored edit, `.bak` backup, AST parse verification, anchor-gone check)

---

## Quality metrics

| Metric | Value |
|--------|-------|
| Quality tier | PARTIAL |
| Observational diversity | 2/3 groups |
| Confidence submitted | 22/25 (88%) |
| Confidence stored | 17/20 (85%) — capped by diversity ceiling |

**Confidence ceiling warning:** Only 2/3 observation groups covered — confidence reduced from 88% to 85%.

**Contradictions flagged by Cronos:**
- Type A: `api_server_security_gap` has evidence both supporting and refuting it (resolved by discard with documented reason).
- Type B: `api_server_security_gap` has supporting evidence but was discarded — Cronos flags this as potentially premature; the discard reason is on record.

---

## Chain of custody

entry_hash : 97533588e6d332701ba17a908f5f0d8676d036db392fba9804afae38023bb8d3
chain_ok   : true
```

A second, differently-shaped example lives at [vigia-intent-analysis/cronos](https://github.com/annatchijova/vigia-intent-analysis/tree/main/cronos): there, CRONOS audits an agent that itself calls the `vigia` MCP server, so the trace records tool calls into another forensic system rather than a plain codebase read. Worth comparing the two — same tracer, very different investigation shape.

### Adopted in

CRONOS has been wired into these projects as the audit/reasoning-trace layer for their agents:

- [forge](https://github.com/annatchijova/forge) — `forge/` folder
- [wolf-and-cronos](https://github.com/annatchijova/wolf-and-cronos) — `corvus-cronos-bridge/` folder
- [rebound](https://github.com/annatchijova/rebound) — the audit above

---

## Installation

```bash
git clone https://github.com/annatchijova/cronos.git
cd cronos
bash install.sh
```

`install.sh` creates a `.venv`, installs the package in editable mode with dev dependencies, and generates a `.env` template for your Slack credentials.

CRONOS works two ways: as a standalone Python SDK (no Slack required — see **SDK Usage** above), or with the Slack bot for `/cronos explain`, `/cronos trace`, and `/cronos audit` posted inline in a channel. Pick whichever fits your use case; the Slack layer is optional.

---

## Web Dashboard

A read-only web UI for browsing sealed traces — trace list with quality badges and confidence bars, full trace detail (step timeline, hypotheses kept vs. discarded, evidence, contradictions, devil's advocate), on-demand chain verification and audit export. Bilingual (EN/ES), no build step.

```bash
pip install -e ".[ui]"                 # FastAPI + uvicorn (optional extra)
python demo_seed.py --reset            # optional: seed 8 demo traces
python -m web                          # http://127.0.0.1:8300/dashboard
```

Configuration via environment: `CRONOS_DB_PATH` (same database the bot and MCP server write to), `CRONOS_WEB_HOST` (default `127.0.0.1`), `CRONOS_WEB_PORT` (default `8300`). Or run `uvicorn web.app:app --reload` during development.

The JSON API mirrors the MCP tool contract — fractions travel as `"p/q"` strings, never floats:

```bash
curl localhost:8300/api/traces                  # list (agent_id, limit, offset)
curl localhost:8300/api/traces/<trace_id>       # full narrated detail + raw steps
curl localhost:8300/api/verify                  # recompute the SHA-256 chain
curl localhost:8300/api/stats                   # per-agent counts, quality histogram
curl -O localhost:8300/api/audit/export         # downloadable chain export
```

Try the tamper demo: `python demo_seed.py --tamper`, then hit **Verify chain** in the dashboard — the exact forged entry is reported.

---

## Setup (Slack bot)

Skip this section if you only want the SDK (`pip install -e .` and `from cronos import CronosTracer, TraceStore` is enough).

### 1. Create the Slack app

Import [`slack_manifest.yml`](slack_manifest.yml) at [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From a manifest**. The manifest declares the `/cronos` slash command and the bot scopes CRONOS needs — nothing is configured by hand.

Enable **Socket Mode** under **Settings → Socket Mode**, then generate an **App-Level Token** with the `connections:write` scope. Socket Mode means no public URL or reverse proxy is required to run this locally.

Install the app to your workspace and collect three values from **Settings → Basic Information** and **Features → OAuth & Permissions**:

| Value | Where to find it |
|---|---|
| `SLACK_BOT_TOKEN` | OAuth & Permissions → Bot User OAuth Token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Basic Information → App-Level Tokens (`xapp-...`) |
| `SLACK_SIGNING_SECRET` | Basic Information → Signing Secret |

### 2. Configure environment

```bash
cp .env.example .env
# Fill in SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_SIGNING_SECRET
```

`.env` is git-ignored. Never commit real tokens — if one leaks, rotate it immediately from the Slack app settings page.

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

Both entry points read `.env` via `config.py` and start the Bolt app in Socket Mode — no inbound webhook configuration needed.

### 4. Verify it's working

Once the bot is running and invited to a channel, run `/cronos status` — it should return an overview of registered agents and trace counts (empty on a fresh install). If nothing responds, check that Socket Mode is enabled and the App-Level Token has `connections:write`.

---

## Tests

```bash
pip install -e ".[dev]"
pytest                          # all 104 tests
pytest tests/test_tracer.py     # SDK recording
pytest tests/test_chain.py      # hash chain integrity
pytest tests/test_store.py      # persistence
pytest tests/test_narrator.py   # NL synthesis
pytest tests/test_output.py     # Block Kit formatters
pytest --cov=cronos --cov-report=term-missing
```

---

## Contributing

Issues and PRs are welcome. If you add a feature that touches the decision path (tracer, chain, store), keep the invariants in `SYSTEM_PROMPT.md` intact: no floats in sealed data, one atomic commit per trace, and hash-chain integrity must hold under `pytest tests/test_chain.py` before and after your change.

---

## License

Apache 2.0
