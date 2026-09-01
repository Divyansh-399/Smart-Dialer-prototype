from collections import Counter
from datetime import datetime
from typing import Iterable

from .models import Agent, CallRecord, CampaignConfig, Lead, Outcome
from .pacing import PredictivePacer
from .providers import MockTelecomProvider
from .safety import SafetyGuard


class DialerEngine:
    def __init__(self, config: CampaignConfig, agents: Iterable[Agent], providers: Iterable[MockTelecomProvider]):
        self.config = config
        self.agents = list(agents)
        self.providers = list(providers)
        if not self.providers:
            raise ValueError("At least one provider is required")
        self.pacer = PredictivePacer()
        self.guard = SafetyGuard(config)
        self.records: list[CallRecord] = []
        self._reported_blocks: set[tuple[str, Outcome]] = set()
        self.turn = 0
        self.max_seen_concurrent = 0

    @property
    def abandon_rate(self) -> float:
        completed = sum(r.outcome in {Outcome.ANSWERED, Outcome.ABANDONED} for r in self.records)
        return sum(r.outcome == Outcome.ABANDONED for r in self.records) / completed if completed else 0.0

    def run_turn(self, leads: list[Lead], now: datetime | None = None) -> list[CallRecord]:
        now = now or datetime.utcnow()
        self.turn += 1
        free_agents = sum(agent.available for agent in self.agents)
        self.pacer.update(self.abandon_rate, self.config.max_abandon_rate)
        desired = self.pacer.target(free_agents, self.config.mode, self.config.max_concurrent_calls)
        target = self.guard.safe_target(desired, free_agents, self.abandon_rate)
        selected = []
        for lead in leads:
            blocked = self.guard.eligibility(lead, now)
            if blocked:
                key = (lead.id, blocked)
                if blocked in {Outcome.BLOCKED_DNC, Outcome.BLOCKED_HOURS} and key not in self._reported_blocks:
                    self.records.append(CallRecord(lead.id, blocked))
                    self._reported_blocks.add(key)
                continue
            selected.append(lead)
            if len(selected) == target:
                break
        self.max_seen_concurrent = max(self.max_seen_concurrent, len(selected))
        results = [self._call(lead, free_agents) for lead in selected]
        self.records.extend(results)
        return results

    def _call(self, lead: Lead, free_agents: int) -> CallRecord:
        lead.attempts += 1
        for attempt in range(1, self.config.retry_limit + 2):
            provider = self._provider()
            outcome = provider.place_call(lead, self.turn)
            if outcome != Outcome.FAILED:
                if outcome == Outcome.ANSWERED and free_agents <= 0:
                    outcome = Outcome.ABANDONED
                return CallRecord(lead.id, outcome, provider.name, attempt)
        return CallRecord(lead.id, Outcome.FAILED, self._provider().name, self.config.retry_limit + 1)

    def _provider(self) -> MockTelecomProvider:
        healthy = [p for p in self.providers if p.breaker.available(self.turn)]
        return (healthy or self.providers)[0]

    def summary(self) -> dict[str, int | float]:
        counts = Counter(r.outcome.value for r in self.records)
        return {**counts, "abandon_rate": round(self.abandon_rate * 100, 2), "pacing_ratio": self.pacer.ratio}
