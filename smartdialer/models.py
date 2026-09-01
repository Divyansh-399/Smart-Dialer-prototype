from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Optional


class Outcome(str, Enum):
    ANSWERED = "answered"
    VOICEMAIL = "voicemail"
    BUSY = "busy"
    NO_ANSWER = "no_answer"
    FAILED = "failed"
    ABANDONED = "abandoned"
    BLOCKED_DNC = "blocked_dnc"
    BLOCKED_HOURS = "blocked_hours"


@dataclass
class Lead:
    id: str
    phone: str
    timezone: str = "UTC"
    dnc: bool = False
    attempts: int = 0


@dataclass
class Agent:
    id: str
    available: bool = True


@dataclass
class CallRecord:
    lead_id: str
    outcome: Outcome
    provider: Optional[str] = None
    attempts: int = 1
    at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class CampaignConfig:
    mode: str = "predictive"  # predictive | progressive
    max_concurrent_calls: int = 20
    max_attempts_per_lead: int = 3
    max_abandon_rate: float = 0.03
    start_hour: int = 8
    end_hour: int = 20
    retry_limit: int = 2
