from collections import Counter
from datetime import UTC, datetime
from typing import Iterable

from .models import (Agent, AgentState, CallRecord, CallState, CampaignConfig, Lead,
                     Outcome, PacingRequest, ProviderEvent, TERMINAL_CALL_STATES)
from .pacing import PredictivePacer
from .providers import MockTelecomProvider
from .repository import InMemoryRepository
from .safety import SafetyController


class DialerEngine:
    """Campaign -> Pacer -> Safety Controller -> Allocator -> Provider."""
    def __init__(self, config: CampaignConfig, agents: Iterable[Agent], providers: Iterable[MockTelecomProvider]):
        self.config = config
        self.providers = list(providers)
        if not self.providers:
            raise ValueError("At least one provider is required")
        self.repository = InMemoryRepository(list(agents))
        self.pacer, self.safety = PredictivePacer(), SafetyController(config)
        self.records: list[CallRecord] = []
        self._reported_blocks: set[tuple[str, Outcome]] = set()
        self.turn, self.max_seen_concurrent = 0, 0

    @property
    def agents(self) -> list[Agent]:
        return list(self.repository.agents.values())

    @property
    def abandon_rate(self) -> float:
        connected = sum(r.outcome == Outcome.ANSWERED for r in self.records)
        abandoned = sum(r.outcome == Outcome.ABANDONED for r in self.records)
        return abandoned / (connected + abandoned) if connected + abandoned else 0.0

    @property
    def answer_rate(self) -> float:
        completed = [r for r in self.records if r.state in TERMINAL_CALL_STATES]
        return sum(r.outcome == Outcome.ANSWERED for r in completed) / len(completed) if completed else .32

    def run_turn(self, leads: list[Lead], now: datetime | None = None) -> list[CallRecord]:
        now = now or datetime.now(UTC)
        self.turn += 1
        self.repository.add_leads(leads)
        available = self.repository.available_agents()
        healthy = any(provider.healthy(self.turn) for provider in self.providers)
        self.pacer.update(self.abandon_rate, self.config.max_abandon_rate, self.answer_rate)
        requested = self.pacer.target(available, self.config.mode, self.config.max_concurrent_calls)
        decision = self.safety.authorize(PacingRequest(requested, self.config.mode, available, 0, healthy), self.abandon_rate)
        selected: list[CallRecord] = []
        for lead in leads:
            if len(selected) >= decision.approved:
                break
            blocked = self.safety.eligibility(lead, now)
            if blocked:
                self._report_block(lead, blocked)
                continue
            call = CallRecord(lead_id=lead.id)
            if self.repository.reserve(lead.id, call):
                lead.attempts += 1
                selected.append(call)
        self.max_seen_concurrent = max(self.max_seen_concurrent, len(selected))
        for call in selected:
            self._initiate(call)
        return selected

    def _report_block(self, lead: Lead, outcome: Outcome) -> None:
        key = (lead.id, outcome)
        if outcome in {Outcome.BLOCKED_DNC, Outcome.BLOCKED_HOURS} and key not in self._reported_blocks:
            self.records.append(CallRecord(lead.id, outcome=outcome, state=CallState.CANCELLED))
            self._reported_blocks.add(key)

    def _initiate(self, call: CallRecord) -> None:
        provider = self._provider()
        if provider is None:
            call.state, call.outcome = CallState.FAILED, Outcome.FAILED
            call.history.append(CallState.FAILED.value)
            self.repository.release(call)
            self.records.append(call)
            return
        call.provider, call.state, call.attempts = provider.name, CallState.INITIATED, 1
        call.history.append(CallState.INITIATED.value)
        self.repository.agents[call.agent_id].state = AgentState.DIALING
        for event in provider.initiate(call, self.turn):
            self.process_event(event)

    def process_event(self, event: ProviderEvent) -> bool:
        call = self.repository.calls.get(event.call_id)
        if not call or event.id in call.event_ids or call.state in TERMINAL_CALL_STATES:
            return False
        call.event_ids.add(event.id)
        if event.state == CallState.RINGING and call.state in {CallState.RESERVED, CallState.INITIATED}:
            call.state = CallState.RINGING
        elif event.state == CallState.ANSWERED and call.state in {CallState.INITIATED, CallState.RINGING}:
            call.state, call.outcome = CallState.CONNECTED, Outcome.ANSWERED
            self.repository.agents[call.agent_id].state = AgentState.CONNECTED
        elif event.state == CallState.COMPLETED:
            call.state = CallState.COMPLETED
        elif event.state == CallState.FAILED:
            call.state, call.outcome = CallState.FAILED, Outcome.FAILED
        else:
            return False
        call.history.append(event.state.value)
        if call.state in TERMINAL_CALL_STATES:
            self.repository.release(call)
            if call not in self.records:
                self.records.append(call)
        return True

    def recover(self) -> int:
        """Reconcile in-flight calls with the provider after a worker restart."""
        recovered = 0
        for call in list(self.repository.calls.values()):
            if call.state in TERMINAL_CALL_STATES:
                continue
            provider = next((p for p in self.providers if p.name == call.provider), None)
            for event in provider.status(call.id) if provider else []:
                self.process_event(event)
            if call.state not in TERMINAL_CALL_STATES:
                call.state = CallState.CANCELLED
                call.history.append("cancelled_after_recovery")
                self.repository.release(call)
                self.records.append(call)
            recovered += 1
        return recovered

    def _provider(self) -> MockTelecomProvider | None:
        return next((p for p in self.providers if p.healthy(self.turn)), None)

    def summary(self) -> dict[str, int | float]:
        counts = Counter(record.outcome.value for record in self.records)
        return {**counts, "abandon_rate": round(self.abandon_rate * 100, 2), "pacing_ratio": self.pacer.ratio,
                "safety_decisions": len(self.safety.decisions), "max_batch": self.max_seen_concurrent}
