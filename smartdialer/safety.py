"""Non-bypassable policy boundary between pacing and allocation."""

from datetime import datetime

from .models import CampaignConfig, Lead, Outcome, PacingRequest, SafetyDecision


class SafetyController:
    """Owns permission to create calls; the pacer never receives a provider."""
    def __init__(self, config: CampaignConfig):
        self.config = config
        self.decisions: list[SafetyDecision] = []

    def eligibility(self, lead: Lead, now: datetime) -> Outcome | None:
        if lead.dnc:
            return Outcome.BLOCKED_DNC
        if lead.attempts >= self.config.max_attempts_per_lead:
            return Outcome.NO_ANSWER
        if not self.config.start_hour <= now.hour < self.config.end_hour:
            return Outcome.BLOCKED_HOURS
        return None

    def authorize(self, request: PacingRequest, abandon_rate: float) -> SafetyDecision:
        if not request.provider_healthy:
            decision = SafetyDecision(request.requested, 0, "no healthy provider")
        elif abandon_rate >= self.config.max_abandon_rate:
            decision = SafetyDecision(request.requested, min(request.requested, request.available_agents), "abandon guard: progressive fallback", True)
        elif request.mode == "progressive":
            decision = SafetyDecision(request.requested, min(request.requested, request.available_agents), "progressive capacity")
        else:
            approved = min(request.requested, request.available_agents, self.config.max_concurrent_calls)
            decision = SafetyDecision(request.requested, approved, "predictive request approved" if approved == request.requested else "reduced to protected agent capacity", approved < request.requested)
        self.decisions.append(decision)
        return decision


SafetyGuard = SafetyController
