from dataclasses import dataclass


@dataclass
class CircuitBreaker:
    failure_threshold: int = 2
    cool_down_turns: int = 3
    failures: int = 0
    opened_until: int = 0

    def available(self, turn: int) -> bool:
        return turn >= self.opened_until

    def success(self) -> None:
        self.failures = 0

    def failure(self, turn: int) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.opened_until = turn + self.cool_down_turns
            self.failures = 0
