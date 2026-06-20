"""
CRONOS — shared data models.
All confidence values use fractions.Fraction — zero floats in the scoring path.
"""
from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction
from typing import Optional


class StepKind(str, Enum):
    OBJECTIVE  = "objective"   # what the agent was asked to do
    RECALL     = "recall"      # memory retrieved from episodic store
    TOOL       = "tool"        # external tool called (Jira, GitHub, DB…)
    HYPOTHESIS = "hypothesis"  # candidate explanation generated
    DISCARD    = "discard"     # hypothesis rejected with reason
    EVIDENCE   = "evidence"    # fact that supports or refutes a hypothesis
    DECISION   = "decision"    # final action chosen


@dataclass
class TraceStep:
    kind: StepKind
    payload: dict   # step-specific structured data (varies by kind)
    timestamp: str  # UTC ISO-8601


@dataclass
class Trace:
    trace_id: str             # UUID4
    agent_id: str             # e.g. "ticket-resolver", "onboarding-bot"
    channel_id: str           # Slack channel where the agent was triggered
    user_id: str              # Slack user who triggered the action
    objective: str            # what the agent was asked to accomplish
    steps: list[TraceStep] = field(default_factory=list)
    decision: Optional[str] = None           # final decision text
    confidence: Optional[Fraction] = None    # 0–1, no floats
    started_at: Optional[str] = None         # UTC ISO-8601
    closed_at: Optional[str] = None          # UTC ISO-8601
    entry_hash: Optional[str] = None         # SHA-256 from the chain
    chain_ok: bool = False                   # chain integrity at close time
    closed: bool = False
