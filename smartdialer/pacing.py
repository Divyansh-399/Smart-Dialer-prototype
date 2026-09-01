from dataclasses import dataclass


@dataclass
class PredictivePacer:
    """A conservative feedback controller for dial-ahead volume."""
    ratio: float = 1.0
    minimum: float = 1.0
    maximum: float = 3.5
    step: float = 0.25

    def update(self, abandon_rate: float, cap: float) -> float:
        if abandon_rate >= cap:
            self.ratio = self.minimum
        elif abandon_rate >= cap * 0.75:
            self.ratio = max(self.minimum, self.ratio - self.step)
        elif abandon_rate <= cap * 0.25:
            self.ratio = min(self.maximum, self.ratio + self.step)
        return self.ratio

    def target(self, free_agents: int, mode: str, max_concurrent: int) -> int:
        if mode == "progressive":
            return min(free_agents, max_concurrent)
        return min(max_concurrent, int(free_agents * self.ratio + 0.999))
