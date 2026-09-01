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

    def healthy(self, turn: int) -> bool:
        return self.breaker.available(turn)

    def initiate(self, call: CallRecord, turn: int) -> list[ProviderEvent]:
        if not self.healthy(turn):
            return [self._event(call.id, CallState.FAILED)]
        outcome = self.outcomes.pop(0) if self.outcomes else self._random_outcome()
        events = [self._event(call.id, state, index) for index, state in enumerate(self._states_for(outcome))]
        self.status_by_call[call.id] = events
        if outcome == Outcome.FAILED:
            self.breaker.failure(turn)
        else:
            self.breaker.success()
        return events

    def status(self, call_id: str) -> list[ProviderEvent]:
        return self.status_by_call.get(call_id, [])

    def _event(self, call_id: str, state: CallState, index: int = 0) -> ProviderEvent:
        return ProviderEvent(f"{self.name}:{call_id}:{state.value}:{index}", call_id, state, self.name)

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
    def __init__(self, name: str = "ProviderA") -> None:
        super().__init__(name=name, failure_rate=0.01, answer_rate=0.35)


class ChaoticMockProvider(MockTelecomProvider):
    """Slow/faulty mock: duplicated and deliberately out-of-order webhooks."""
    def __init__(self, name: str = "ProviderB", **kwargs: object) -> None:
        super().__init__(name=name, failure_rate=0.12, answer_rate=0.32, **kwargs)

    def initiate(self, call: CallRecord, turn: int) -> list[ProviderEvent]:
        events = super().initiate(call, turn)
        if len(events) >= 2:
            return [events[-1], events[1], events[1], *events[:-1]]
        return events
