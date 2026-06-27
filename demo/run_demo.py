#!/usr/bin/env python3
"""
CRONOS — Standalone CLI Demo
============================

Runs the Black Box Recorder end to end, in your terminal, with NO Slack tokens
and NO external services. It uses the real CRONOS SDK (CronosTracer, TraceStore,
Narrator, TraceChain) to:

  1. Run several support-ticket scenarios through the instrumented decision cycle
  2. Print each sealed trace — decision, "why" lines, full step log, and the
     deterministic natural-language explanation
  3. Export and verify the SHA-256 audit chain
  4. TAMPER with a stored trace and re-verify, proving the chain catches it

Everything is deterministic and reproducible — the same inputs always produce
the same traces and the same hashes.

Run it
------
    python3 demo/run_demo.py            # from the repo root
    python3 -m demo.run_demo            # as a module

Options
-------
    --no-color       disable ANSI colors (for logs / piping)
    --keep-db PATH   write the SQLite DB to PATH instead of a temp file
"""

import argparse
import os
import sqlite3
import sys
import tempfile

# Allow `python3 demo/run_demo.py` from the repo root without installing.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cronos import TraceStore                       # noqa: E402
from cronos.narrator import Narrator                # noqa: E402
from demo.agent import run_decision_cycle           # noqa: E402


# ── ANSI helpers ────────────────────────────────────────────────────────────────

class C:
    """ANSI color codes, blanked out when colors are disabled."""
    enabled = True
    RESET = "\033[0m";  BOLD = "\033[1m";  DIM = "\033[2m"
    INDIGO = "\033[38;5;105m"; CYAN = "\033[38;5;44m"
    GREEN = "\033[38;5;42m";   RED = "\033[38;5;203m"
    AMBER = "\033[38;5;215m";  GREY = "\033[38;5;245m"

    @classmethod
    def disable(cls) -> None:
        cls.enabled = False
        for name in ("RESET", "BOLD", "DIM", "INDIGO", "CYAN",
                     "GREEN", "RED", "AMBER", "GREY"):
            setattr(cls, name, "")


def c(text: str, color: str) -> str:
    return f"{color}{text}{C.RESET}"


def rule(char: str = "─", width: int = 64) -> str:
    return c(char * width, C.GREY)


def conf_bar(pct: int, width: int = 10) -> str:
    filled = round(pct / 100 * width)
    color = C.GREEN if pct >= 80 else (C.INDIGO if pct >= 65 else C.AMBER)
    return c("█" * filled, color) + c("░" * (width - filled), C.GREY)


# ── Demo scenarios ──────────────────────────────────────────────────────────────
# Each message routes deterministically to one category inside run_decision_cycle.

SCENARIOS = [
    ("Auth",     "Hey, ticket #442 is failing — users can't login to the app"),
    ("Cache",    "Ticket #108: product pages are showing stale prices, possible cache issue"),
    ("Security", "Ticket #731: engineer reported unexpected access escalation to prod IAM role"),
    ("DB",       "Ticket #519: service is timing out — database connection pool seems exhausted"),
]


# ── Rendering ───────────────────────────────────────────────────────────────────

# Map step kinds to C attribute *names* (not values) so colors resolve at
# render time — after --no-color may have blanked the codes out.
_STEP_COLORS = {
    "objective":  "GREY",
    "recall":     "CYAN",
    "tool":       "INDIGO",
    "hypothesis": "AMBER",
    "evidence":   "GREEN",
    "discard":    "RED",
    "decision":   "BOLD",
}


def render_trace(trace) -> None:
    """Pretty-print a single sealed trace to the terminal."""
    n = Narrator(trace)
    short = n.short()
    pct = int(short["confidence_pct"].rstrip("%")) if short["confidence_pct"].endswith("%") else 0

    print()
    print(c("⬡ CRONOS TRACE", C.INDIGO + C.BOLD) +
          c(f" · {trace.agent_id}", C.GREY))
    print(c(f"  Objective:  ", C.GREY) + trace.objective)
    print(c(f"  Decision:   ", C.GREY) + c(short["decision"], C.BOLD))
    print()

    # Why lines
    print(c("  Why?", C.GREY))
    for sym, text in short["why_lines"]:
        mark = c("✓", C.GREEN) if sym == "✓" else c("✗", C.RED)
        print(f"    {mark} {text}")
    print()

    # Confidence + quality
    print("  " + c("Confidence ", C.GREY) +
          conf_bar(pct) + f"  {c(short['confidence_pct'], C.BOLD)}"
          f"  {c('(' + short['confidence_label'] + ')', C.GREY)}")
    print("  " + c("Quality    ", C.GREY) +
          f"{short['quality']}   " +
          c(f"diversity {short['diversity_pct']}", C.GREY))
    if short["confidence_warnings"]:
        for w in short["confidence_warnings"]:
            print("  " + c(f"⚠ {w}", C.AMBER))
    print()

    # Full step log
    print(c("  Full step log", C.GREY))
    for i, step in enumerate(trace.steps):
        kind = step.kind.value
        color = getattr(C, _STEP_COLORS.get(kind, "RESET"))
        label = c(f"{kind.upper():<11}", color)
        detail = _step_detail(step)
        print(f"    {c(f'{i:02d}', C.GREY)} {label} {detail}")
    print()

    # Chain seal
    ok = c("✅ chain verified", C.GREEN) if trace.chain_ok else c("✗ not sealed", C.RED)
    print("  " + ok + c(f" · {(trace.entry_hash or '')[:12]}…", C.GREY))
    print()

    # Natural language
    print(c("  In plain language", C.GREY))
    print("  " + c(n.natural(), C.DIM))


def _step_detail(step) -> str:
    p = step.payload
    k = step.kind.value
    if k == "objective":
        return c(p.get("objective", "")[:60], C.GREY)
    if k == "recall":
        score = p.get("score", "")
        return f"{p['memory_id']} · {p.get('summary', '')[:46]} {c(score, C.GREY)}"
    if k == "tool":
        return f"{p['tool']} → {p['result'][:50]}"
    if k == "hypothesis":
        return f"{p['label']}: {p.get('description', '')[:46]}"
    if k == "evidence":
        rel = ("supports " + p["supports"]) if "supports" in p else \
              ("refutes " + p["refutes"]) if "refutes" in p else ""
        return f"{p['text'][:44]} {c('(' + rel + ')', C.GREY)}"
    if k == "discard":
        return f"{p['label']} — {p.get('reason', '')[:44]}"
    if k == "decision":
        return c(p.get("decision", "")[:48], C.BOLD) + c(f"  {p.get('confidence','')}", C.GREY)
    return str(p)


def render_chain(store: TraceStore) -> None:
    """Print the exported audit chain and verify it."""
    chain = store.chain.export()
    print(rule())
    print(c("  AUDIT CHAIN", C.INDIGO + C.BOLD) +
          c(f"  ({len(chain)} entries · SHA-256 linked)", C.GREY))
    print(rule())
    prev = "0" * 64
    for entry in chain:
        linked = entry["prev_hash"] == prev
        link = c("⛓", C.GREEN) if linked else c("✗", C.RED)
        print(f"  {link} #{entry['id']}  "
              f"{c(entry['entry_hash'][:16] + '…', C.CYAN)}  "
              f"{c('« ' + entry['prev_hash'][:8] + '…', C.GREY)}  "
              f"{entry['decision'][:34]}")
        prev = entry["entry_hash"]
    print()

    ok, errors = store.chain.verify()
    if ok:
        print("  " + c("✅ CHAIN INTACT", C.GREEN + C.BOLD) +
              c("  — every entry's hash recomputes and links correctly.", C.GREY))
    else:
        print("  " + c("✗ CHAIN BROKEN", C.RED + C.BOLD))
        for e in errors:
            print("    " + c(e, C.RED))
    print()


def demonstrate_tamper(store: TraceStore) -> None:
    """
    Tamper with a stored trace decision directly in SQLite, then re-verify.
    This proves the chain is tamper-evident: a retroactive edit breaks the hash.
    """
    print(rule("═"))
    print(c("  TAMPER TEST", C.AMBER + C.BOLD) +
          c("  — an attacker edits history after the fact", C.GREY))
    print(rule("═"))

    # Grab the first chain entry and forge its decision.
    conn = sqlite3.connect(store._path)
    row = conn.execute(
        "SELECT id, trace_id, decision FROM trace_chain ORDER BY id ASC LIMIT 1"
    ).fetchone()
    entry_id, trace_id, original = row
    forged = "Do nothing — close ticket as won't-fix"

    print(f"  Editing chain entry #{entry_id} ({trace_id[:8]}…)")
    print(f"    before: {c(original, C.GREY)}")
    print(f"    after:  {c(forged, C.RED)}")
    print(c("  (the hashes on disk are left untouched — exactly what a", C.GREY))
    print(c("   tamperer would hope nobody recomputes)", C.GREY))
    print()

    conn.execute(
        "UPDATE trace_chain SET decision = ? WHERE id = ?", (forged, entry_id)
    )
    conn.commit()
    conn.close()

    ok, errors = store.chain.verify()
    if ok:
        print("  " + c("✗ UNEXPECTED: tamper went undetected!", C.RED + C.BOLD))
    else:
        print("  " + c("✅ TAMPER DETECTED", C.GREEN + C.BOLD) +
              c("  — verification recomputed the hashes and caught it:", C.GREY))
        for e in errors:
            print("    " + c("• " + e, C.AMBER))
    print()
    print(c("  This is the whole point: you don't have to trust the database.", C.GREY))
    print(c("  The math doesn't lie — one edit invalidates every later hash.", C.GREY))
    print()


# ── Main ────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="CRONOS standalone CLI demo.")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    parser.add_argument("--keep-db", metavar="PATH", help="persist the SQLite DB here")
    args = parser.parse_args()

    if args.no_color or not sys.stdout.isatty():
        C.disable()

    if args.keep_db:
        db_path = args.keep_db
        cleanup = False
    else:
        fd, db_path = tempfile.mkstemp(prefix="cronos-demo-", suffix=".db")
        os.close(fd)
        cleanup = True

    print()
    print(c("  ╔══════════════════════════════════════════════════════════╗", C.INDIGO))
    print(c("  ║  CRONOS · Black Box Recorder for AI Agents — CLI demo     ║", C.INDIGO + C.BOLD))
    print(c("  ╚══════════════════════════════════════════════════════════╝", C.INDIGO))
    print(c(f"  store: {db_path}", C.GREY))

    store = TraceStore(db_path)
    try:
        for label, message in SCENARIOS:
            print()
            print(rule())
            print(c(f"  SCENARIO · {label}", C.CYAN + C.BOLD))
            print(c(f"  Slack message: ", C.GREY) + f"\"{message}\"")
            trace, _ = run_decision_cycle(store, message)
            render_trace(trace)

        print()
        render_chain(store)
        demonstrate_tamper(store)

        print(rule("═"))
        print("  " + c("Done.", C.BOLD) +
              c(f"  {store.count_traces()} traces recorded, sealed, and verified.", C.GREY))
        print(rule("═"))
        print()
    finally:
        if cleanup:
            try:
                os.remove(db_path)
                for ext in ("-wal", "-shm"):
                    if os.path.exists(db_path + ext):
                        os.remove(db_path + ext)
            except OSError:
                pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
