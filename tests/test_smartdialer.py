from datetime import datetime
import unittest

from smartdialer.engine import DialerEngine
from smartdialer.models import Agent, CampaignConfig, Lead, Outcome
from smartdialer.pacing import PredictivePacer
from smartdialer.providers import MockTelecomProvider
from smartdialer.safety import SafetyGuard


class SmartDialerTests(unittest.TestCase):
    def test_progressive_only_dials_free_agents(self):
        engine = self.engine(mode="progressive", agents=2)
        results = engine.run_turn(self.leads(5), self.noon())
        self.assertEqual(len(results), 2)

    def test_concurrency_cap_is_never_exceeded(self):
        engine = self.engine(agents=8, cap=3)
        engine.run_turn(self.leads(20), self.noon())
        self.assertLessEqual(engine.max_seen_concurrent, 3)

    def test_dnc_is_not_dialed(self):
        lead = Lead("x", "+1", dnc=True)
        engine = self.engine()
        engine.run_turn([lead], self.noon())
        self.assertEqual(lead.attempts, 0)
        self.assertEqual(engine.records[-1].outcome, Outcome.BLOCKED_DNC)

    def test_outside_hours_is_not_dialed(self):
        engine = self.engine()
        lead = Lead("x", "+1")
        engine.run_turn([lead], datetime(2026, 1, 1, 2))
        self.assertEqual(lead.attempts, 0)
        self.assertEqual(engine.records[-1].outcome, Outcome.BLOCKED_HOURS)

    def test_attempt_cap_prevents_redial(self):
        engine = self.engine()
        lead = Lead("x", "+1", attempts=3)
        engine.run_turn([lead], self.noon())
        self.assertEqual(lead.attempts, 3)

    def test_pacer_climbs_when_safe(self):
        pacer = PredictivePacer()
        self.assertGreater(pacer.update(0, .03), 1)

    def test_pacer_backs_off_at_cap(self):
        pacer = PredictivePacer(ratio=3.5)
        self.assertEqual(pacer.update(.03, .03), 1)

    def test_emergency_brake_falls_back_to_progressive(self):
        guard = SafetyGuard(CampaignConfig(max_abandon_rate=.03))
        self.assertEqual(guard.safe_target(10, 3, .03), 3)

    def test_provider_retries_infrastructure_failure(self):
        provider = MockTelecomProvider("mock", outcomes=[Outcome.FAILED, Outcome.ANSWERED])
        engine = self.engine(providers=[provider])
        result = engine.run_turn(self.leads(1), self.noon())[0]
        self.assertEqual(result.outcome, Outcome.ANSWERED)
        self.assertEqual(result.attempts, 2)

    def test_circuit_breaker_opens_after_repeated_failures(self):
        provider = MockTelecomProvider("mock", outcomes=[Outcome.FAILED, Outcome.FAILED])
        engine = self.engine(providers=[provider])
        engine.run_turn(self.leads(1), self.noon())
        self.assertFalse(provider.breaker.available(engine.turn))

    def engine(self, mode="predictive", agents=4, cap=20, providers=None):
        return DialerEngine(CampaignConfig(mode=mode, max_concurrent_calls=cap), [Agent(str(i)) for i in range(agents)], providers or [MockTelecomProvider("mock", outcomes=[Outcome.NO_ANSWER] * 100)])

    def leads(self, count): return [Lead(str(i), f"+1{i}") for i in range(count)]
    def noon(self): return datetime(2026, 1, 1, 12)


if __name__ == "__main__":
    unittest.main()
