import random
from dataclasses import dataclass, field

from .circuit_breaker import CircuitBreaker
from .models import Lead, Outcome


@dataclass
class MockTelecomProvider:
    name: str
    outcomes: list[Outcome] = field(default_factory=list)
    failure_rate: float = 0.03
    answer_rate: float = 0.32
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)

    def place_call(self, lead: Lead, turn: int) -> Outcome:
        if not self.breaker.available(turn):
            return Outcome.FAILED
        outcome = self.outcomes.pop(0) if self.outcomes else self._random_outcome()
        if outcome == Outcome.FAILED:
            self.breaker.failure(turn)
        else:
            self.breaker.success()
        return outcome

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
