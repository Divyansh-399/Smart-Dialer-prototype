from datetime import datetime

from .models import CampaignConfig, Lead, Outcome


class SafetyGuard:
    def __init__(self, config: CampaignConfig):
        self.config = config

    def eligibility(self, lead: Lead, now: datetime) -> Outcome | None:
        if lead.dnc:
            return Outcome.BLOCKED_DNC
        if lead.attempts >= self.config.max_attempts_per_lead:
            return Outcome.NO_ANSWER  # exhausted: never dial again
        if not self.config.start_hour <= now.hour < self.config.end_hour:
            return Outcome.BLOCKED_HOURS
        return None

    def safe_target(self, desired: int, free_agents: int, abandon_rate: float) -> int:
        # Emergency-brake fallback is progressive, not a permanent full stop.
        if abandon_rate >= self.config.max_abandon_rate:
            return min(desired, free_agents)
        return desired
