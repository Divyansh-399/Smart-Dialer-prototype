"""Provider interface plus deterministic reliable and chaotic mocks."""

import random
from dataclasses import dataclass, field

from .circuit_breaker import CircuitBreaker
from .models import CallRecord, CallState, Outcome, ProviderEvent


@dataclass
class MockTelecomProvider:
    name: str
    outcomes: list[Outcome] = field(default_factory=list)
    failure_rate: float = 0.03
    answer_rate: float = 0.32
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    status_by_call: dict[str, list[ProviderEvent]] = field(default_factory=dict)
    setup_turns: int = 0
    talk_turns: int = 0

    def healthy(self, turn: int) -> bool:
        return self.breaker.available(turn)

    def initiate(self, call: CallRecord, turn: int) -> list[ProviderEvent]:
        if not self.healthy(turn):
            return [self._event(call.id, CallState.FAILED)]
        outcome = self.outcomes.pop(0) if self.outcomes else self._random_outcome()
        events = self._events_for(call.id, outcome, turn)
        self.status_by_call[call.id] = events
        if outcome == Outcome.FAILED:
            self.breaker.failure(turn)
        else:
            self.breaker.success()
        return events

    def status(self, call_id: str) -> list[ProviderEvent]:
        return self.status_by_call.get(call_id, [])

    def _event(self, call_id: str, state: CallState, index: int = 0, due_turn: int = 0) -> ProviderEvent:
        return ProviderEvent(f"{self.name}:{call_id}:{state.value}:{index}", call_id, state, self.name, due_turn)

    def _events_for(self, call_id: str, outcome: Outcome, turn: int) -> list[ProviderEvent]:
        if outcome == Outcome.ANSWERED:
            answer_at = turn + self.setup_turns
            return [self._event(call_id, CallState.RINGING, 0, turn),
                    self._event(call_id, CallState.ANSWERED, 1, answer_at),
                    self._event(call_id, CallState.CONNECTED, 2, answer_at),
                    self._event(call_id, CallState.COMPLETED, 3, answer_at + self.talk_turns)]
        if outcome == Outcome.FAILED:
            return [self._event(call_id, CallState.FAILED, 0, turn)]
        return [self._event(call_id, CallState.RINGING, 0, turn),
                self._event(call_id, CallState.COMPLETED, 1, turn + self.setup_turns)]

    def _states_for(self, outcome: Outcome) -> list[CallState]:
        if outcome == Outcome.ANSWERED:
            return [CallState.RINGING, CallState.ANSWERED, CallState.COMPLETED]
        if outcome == Outcome.FAILED:
            return [CallState.FAILED]
        return [CallState.RINGING, CallState.COMPLETED]

    def _random_outcome(self) -> Outcome:
        roll = random.random()
        if roll < self.failure_rate:
            return Outcome.FAILED
        if roll < self.failure_rate + self.answer_rate:
            return Outcome.ANSWERED
        if roll < .58:
            return Outcome.NO_ANSWER
        if roll < .80:
            return Outcome.VOICEMAIL
        return Outcome.BUSY


class ReliableMockProvider(MockTelecomProvider):
    def __init__(self, name: str = "ProviderA", **kwargs: object) -> None:
        super().__init__(name=name, failure_rate=0.01, answer_rate=0.35, **kwargs)


class ChaoticMockProvider(MockTelecomProvider):
    """Slow/faulty mock: duplicated and deliberately out-of-order webhooks."""
    def __init__(self, name: str = "ProviderB", **kwargs: object) -> None:
        super().__init__(name=name, failure_rate=0.12, answer_rate=0.32, **kwargs)

    def initiate(self, call: CallRecord, turn: int) -> list[ProviderEvent]:
        events = super().initiate(call, turn)
        if len(events) >= 2:
            return [events[-1], events[1], events[1], *events[:-1]]
        return events
