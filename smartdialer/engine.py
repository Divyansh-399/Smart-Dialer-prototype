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
        self.pending_events: list[ProviderEvent] = []

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
        self._process_due_events()
        self.repository.add_leads(leads)
        available = self.repository.available_agents()
        protected_slots = self._protected_release_slots()
        healthy = any(provider.healthy(self.turn) for provider in self.providers)
        self.pacer.update(self.abandon_rate, self.config.max_abandon_rate, self.answer_rate)
        pacing_capacity = available + (protected_slots if self.config.mode == "predictive" else 0)
        requested = self.pacer.target(pacing_capacity, self.config.mode, self.config.max_concurrent_calls)
        ringing = sum(call.state == CallState.RINGING for call in self.repository.calls.values())
        decision = self.safety.authorize(PacingRequest(requested, self.config.mode, available, ringing, healthy, protected_slots), self.abandon_rate)
        selected: list[CallRecord] = []
        for lead in leads:
            if len(selected) >= decision.approved:
                break
            blocked = self.safety.eligibility(lead, now)
            if blocked:
                self._report_block(lead, blocked)
                continue
            call = CallRecord(lead_id=lead.id)
            lookahead = self.config.predictive_lookahead_turns if self.config.mode == "predictive" else 0
            if self.repository.reserve(lead.id, call, self.turn, lookahead):
                lead.attempts += 1
                selected.append(call)
        self.max_seen_concurrent = max(self.max_seen_concurrent, len(selected))
        for call in selected:
            self._initiate(call)
        self._process_due_events()
        return selected

    def _report_block(self, lead: Lead, outcome: Outcome) -> None:
        key = (lead.id, outcome)
        if outcome in {Outcome.BLOCKED_DNC, Outcome.BLOCKED_HOURS} and key not in self._reported_blocks:
            self.records.append(CallRecord(lead.id, outcome=outcome, state=CallState.CANCELLED))
            self._reported_blocks.add(key)

    def _initiate(self, call: CallRecord, exclude_provider: str | None = None) -> None:
        provider = self._provider(exclude_provider)
        if provider is None:
            call.state, call.outcome = CallState.FAILED, Outcome.FAILED
            call.history.append(CallState.FAILED.value)
            self.repository.release(call)
            self.records.append(call)
            return
        call.provider, call.state = provider.name, CallState.INITIATED
        call.attempts += 1
        call.history.append(CallState.INITIATED.value)
        agent = self.repository.agents[call.agent_id]
        if agent.reserved_call_id == call.id:
            agent.state = AgentState.DIALING
        self.pending_events.extend(provider.initiate(call, self.turn))

    def _process_due_events(self) -> None:
        while True:
            due = [event for event in self.pending_events if event.due_turn <= self.turn]
            self.pending_events = [event for event in self.pending_events if event.due_turn > self.turn]
            if not due:
                return
            # Free a different call's deterministic future token before an answer,
            # but preserve normal RINGING -> ANSWERED -> CONNECTED -> COMPLETED order.
            nonterminal_same_turn = {event.call_id for event in due if event.state != CallState.COMPLETED}
            order = {CallState.RINGING: 0, CallState.ANSWERED: 1, CallState.CONNECTED: 2,
                     CallState.FAILED: 3, CallState.COMPLETED: 4}
            due.sort(key=lambda event: (event.due_turn,
                                        0 if event.state == CallState.COMPLETED and event.call_id not in nonterminal_same_turn else 1,
                                        order.get(event.state, 5), event.id))
            for event in due:
                self.process_event(event)

    def _protected_release_slots(self) -> int:
        return sum(agent.state == AgentState.CONNECTED and not agent.future_call_id
                   and agent.release_turn <= self.turn + self.config.predictive_lookahead_turns
                   for agent in self.agents)

    def process_event(self, event: ProviderEvent) -> bool:
        call = self.repository.calls.get(event.call_id)
        if not call or event.id in call.event_ids or call.state in TERMINAL_CALL_STATES:
            return False
        call.event_ids.add(event.id)
        if event.state == CallState.RINGING and call.state in {CallState.RESERVED, CallState.INITIATED}:
            call.state = CallState.RINGING
        elif event.state == CallState.ANSWERED and call.state in {CallState.INITIATED, CallState.RINGING}:
            call.state, call.outcome = CallState.ANSWERED, Outcome.ANSWERED
        elif event.state == CallState.CONNECTED and call.state == CallState.ANSWERED:
            call.state = CallState.CONNECTED
            agent = self.repository.agents[call.agent_id]
            agent.state = AgentState.CONNECTED
            agent.release_turn = max((pending.due_turn for pending in self.pending_events
                                      if pending.call_id == call.id and pending.state == CallState.COMPLETED), default=self.turn)
        elif event.state == CallState.COMPLETED:
            call.state = CallState.COMPLETED
        elif event.state == CallState.FAILED:
            if call.attempts <= self.config.retry_limit:
                call.history.append("retrying_after_provider_failure")
                self._initiate(call, event.provider)
                return True
            call.state, call.outcome = CallState.FAILED, Outcome.FAILED
        else:
            return False
        call.history.append(event.state.value)
        if call.state in TERMINAL_CALL_STATES:
            self.repository.release(call)
            if call not in self.records:
                self.records.append(call)
        return True

    def mark_agents_unavailable(self, agent_ids: list[str]) -> None:
        """Immediately remove agents from future pacing; cancel only pre-connect calls."""
        for agent_id in agent_ids:
            agent = self.repository.agents[agent_id]
            active = next((call for call in self.repository.calls.values()
                           if call.agent_id == agent_id and call.state not in TERMINAL_CALL_STATES), None)
            if active and active.state in {CallState.RESERVED, CallState.INITIATED, CallState.RINGING}:
                active.state = CallState.CANCELLED
                active.history.append("cancelled_agent_unavailable")
                self.pending_events = [event for event in self.pending_events if event.call_id != active.id]
                self.repository.release(active)
                self.records.append(active)
            self.repository.mark_agent_offline(agent_id)

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

    def _provider(self, exclude: str | None = None) -> MockTelecomProvider | None:
        return next((p for p in self.providers if p.name != exclude and p.healthy(self.turn)), None)

    def summary(self) -> dict[str, int | float]:
        counts = Counter(record.outcome.value for record in self.records)
        return {**counts, "abandon_rate": round(self.abandon_rate * 100, 2), "pacing_ratio": self.pacer.ratio,
                "safety_decisions": len(self.safety.decisions), "max_batch": self.max_seen_concurrent}
