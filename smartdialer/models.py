"""Domain model and explicit lifecycle states for the SmartDialer prototype."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Optional
from uuid import uuid4


class AgentState(str, Enum):
    OFFLINE = "offline"
    AVAILABLE = "available"
    RESERVED = "reserved"
    DIALING = "dialing"
    CONNECTED = "connected"
    WRAP_UP = "wrap_up"
    PAUSED = "paused"


class CallState(str, Enum):
    QUEUED = "queued"
    RESERVED = "reserved"
    INITIATED = "initiated"
    RINGING = "ringing"
    ANSWERED = "answered"
    CONNECTED = "connected"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Outcome(str, Enum):
    ANSWERED = "answered"
    VOICEMAIL = "voicemail"
    BUSY = "busy"
    NO_ANSWER = "no_answer"
    FAILED = "failed"
    ABANDONED = "abandoned"
    BLOCKED_DNC = "blocked_dnc"
    BLOCKED_HOURS = "blocked_hours"


TERMINAL_CALL_STATES = {CallState.COMPLETED, CallState.FAILED, CallState.CANCELLED}


@dataclass
class Lead:
    id: str
    phone: str
    timezone: str = "UTC"
    dnc: bool = False
    attempts: int = 0
    reserved_call_id: Optional[str] = None


@dataclass
class Agent:
    id: str
    available: bool = True
    state: AgentState = AgentState.AVAILABLE
    reserved_call_id: Optional[str] = None
    future_call_id: Optional[str] = None
    release_turn: int = 0

    def __post_init__(self) -> None:
        if not self.available and self.state == AgentState.AVAILABLE:
            self.state = AgentState.OFFLINE


@dataclass
class CallRecord:
    lead_id: str
    outcome: Outcome = Outcome.NO_ANSWER
    provider: Optional[str] = None
    attempts: int = 0
    at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: str = field(default_factory=lambda: str(uuid4()))
    agent_id: Optional[str] = None
    state: CallState = CallState.QUEUED
    event_ids: set[str] = field(default_factory=set)
    history: list[str] = field(default_factory=lambda: [CallState.QUEUED.value])
    scheduled_turn: int = 0


@dataclass(frozen=True)
class ProviderEvent:
    id: str
    call_id: str
    state: CallState
    provider: str
    due_turn: int = 0


@dataclass(frozen=True)
class PacingRequest:
    requested: int
    mode: str
    available_agents: int
    ringing_calls: int
    provider_healthy: bool
    protected_release_slots: int = 0


@dataclass(frozen=True)
class SafetyDecision:
    requested: int
    approved: int
    reason: str
    fallback_to_progressive: bool = False


@dataclass
class CampaignConfig:
    mode: str = "predictive"
    max_concurrent_calls: int = 20
    max_attempts_per_lead: int = 3
    max_abandon_rate: float = 0.03
    start_hour: int = 8
    end_hour: int = 20
    retry_limit: int = 1
    reservation_ttl_turns: int = 2
    predictive_lookahead_turns: int = 1
    turn_seconds: int = 30
