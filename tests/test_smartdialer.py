from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from smartdialer.engine import DialerEngine
from smartdialer.models import Agent, CallRecord, CallState, CampaignConfig, Lead, Outcome, ProviderEvent
from smartdialer.pacing import PredictivePacer
from smartdialer.providers import ChaoticMockProvider, MockTelecomProvider
from smartdialer.repository import InMemoryRepository, SqliteReservationStore
from smartdialer.safety import SafetyController


class SmartDialerTests(unittest.TestCase):
    def test_progressive_only_dials_free_agents(self):
        engine = self.engine(mode="progressive", agents=2)
        self.assertEqual(len(engine.run_turn(self.leads(5), self.noon())), 2)

    def test_predictive_is_reduced_to_protected_agent_capacity(self):
        engine = self.engine(agents=2)
        engine.pacer.ratio = 3
        self.assertEqual(len(engine.run_turn(self.leads(10), self.noon())), 2)
        self.assertTrue(engine.safety.decisions[-1].fallback_to_progressive)

    def test_dnc_and_hours_are_not_dialed(self):
        engine = self.engine()
        dnc, late = Lead("d", "+1", dnc=True), Lead("l", "+2")
        engine.run_turn([dnc], self.noon())
        engine.run_turn([late], datetime(2026, 1, 1, 2))
        self.assertEqual((dnc.attempts, late.attempts), (0, 0))
        self.assertIn(Outcome.BLOCKED_DNC, [record.outcome for record in engine.records])
        self.assertIn(Outcome.BLOCKED_HOURS, [record.outcome for record in engine.records])

    def test_duplicate_and_out_of_order_events_are_idempotent(self):
        engine = self.engine(providers=[ChaoticMockProvider(outcomes=[Outcome.ANSWERED])])
        call = engine.run_turn(self.leads(1), self.noon())[0]
        self.assertEqual(call.state, CallState.COMPLETED)
        self.assertEqual(call.history.count("answered"), 1)
        self.assertEqual(len(engine.records), 1)

    def test_terminal_event_blocks_late_answer(self):
        engine = self.engine()
        call = CallRecord("x", provider="mock", state=CallState.INITIATED)
        engine.repository.add_leads([Lead("x", "+1")])
        self.assertTrue(engine.repository.reserve("x", call))
        engine.process_event(ProviderEvent("done", call.id, CallState.COMPLETED, "mock"))
        self.assertFalse(engine.process_event(ProviderEvent("late", call.id, CallState.ANSWERED, "mock")))
        self.assertEqual(call.state, CallState.COMPLETED)

    def test_atomic_reservation_allows_one_winner(self):
        repo = InMemoryRepository([Agent("a")], [Lead("l", "+1")])
        calls = [CallRecord("l"), CallRecord("l")]
        with ThreadPoolExecutor(max_workers=2) as pool:
            wins = list(pool.map(lambda call: repo.reserve("l", call), calls))
        self.assertEqual(sum(wins), 1)

    def test_sqlite_transaction_allows_one_multi_worker_winner(self):
        with TemporaryDirectory() as directory:
            path = str(Path(directory) / "reservations.db")
            SqliteReservationStore(path).seed(["a"], ["l"])
            with ThreadPoolExecutor(max_workers=2) as pool:
                winners = list(pool.map(lambda call: SqliteReservationStore(path).reserve_pair("l", call), ["one", "two"]))
        self.assertEqual(sum(winner is not None for winner in winners), 1)

    def test_answered_connected_completed_lifecycle_is_preserved(self):
        engine = self.engine(providers=[MockTelecomProvider("mock", outcomes=[Outcome.ANSWERED])])
        call = engine.run_turn(self.leads(1), self.noon())[0]
        self.assertEqual(call.history[-3:], ["answered", "connected", "completed"])

    def test_retry_fails_over_to_second_provider(self):
        first = MockTelecomProvider("first", outcomes=[Outcome.FAILED])
        second = MockTelecomProvider("second", outcomes=[Outcome.ANSWERED])
        engine = self.engine(providers=[first, second])
        call = engine.run_turn(self.leads(1), self.noon())[0]
        self.assertEqual((call.provider, call.attempts, call.outcome), ("second", 2, Outcome.ANSWERED))

    def test_predictive_binds_imminent_release_slot(self):
        provider = MockTelecomProvider("mock", outcomes=[Outcome.ANSWERED, Outcome.ANSWERED], setup_turns=1, talk_turns=2)
        engine = self.engine(agents=1, providers=[provider])
        leads = self.leads(2)
        engine.run_turn(leads, self.noon())  # ringing
        engine.run_turn(leads, self.noon())  # first agent connected; releases at turn 4
        future = engine.run_turn(leads, self.noon())
        self.assertEqual(len(future), 1)
        self.assertEqual(engine.agents[0].future_call_id, future[0].id)

    def test_agent_drop_immediately_removes_future_capacity(self):
        engine = self.engine(agents=3)
        engine.mark_agents_unavailable(["0", "1"])
        self.assertEqual(len(engine.run_turn(self.leads(10), self.noon())), 1)

    def test_end_to_end_abandon_guard_reduces_predictive_request(self):
        engine = self.engine(agents=3)
        engine.records.append(CallRecord("probe", Outcome.ABANDONED, state=CallState.COMPLETED))
        engine.pacer.ratio = 3
        engine.run_turn(self.leads(10), self.noon())
        decision = engine.safety.decisions[-1]
        self.assertEqual((decision.approved, decision.fallback_to_progressive), (3, True))

    def test_worker_recovery_reconciles_provider_status(self):
        provider = MockTelecomProvider("mock")
        engine = self.engine(providers=[provider])
        call = CallRecord("x", provider="mock", state=CallState.INITIATED)
        engine.repository.add_leads([Lead("x", "+1")])
        engine.repository.reserve("x", call)
        provider.status_by_call[call.id] = [ProviderEvent("done", call.id, CallState.COMPLETED, "mock")]
        self.assertEqual(engine.recover(), 1)
        self.assertEqual(call.state, CallState.COMPLETED)
        self.assertEqual(engine.agents[0].state.value, "available")

    def test_provider_outage_rejects_new_calls(self):
        provider = MockTelecomProvider("mock")
        provider.breaker.opened_until = 99
        engine = self.engine(providers=[provider])
        self.assertEqual(engine.run_turn(self.leads(2), self.noon()), [])
        self.assertEqual(engine.safety.decisions[-1].reason, "no healthy provider")

    def test_pacer_backs_off_on_bad_answer_rate(self):
        self.assertEqual(PredictivePacer(ratio=3.5).update(0, .03, .1), 1)

    def test_abandon_guard_falls_back_to_progressive(self):
        safety = SafetyController(CampaignConfig(max_abandon_rate=.03))
        request = type("Request", (), {"requested": 10, "available_agents": 3, "provider_healthy": True, "mode": "predictive"})()
        self.assertEqual(safety.authorize(request, .03).approved, 3)

    def engine(self, mode="predictive", agents=4, cap=20, providers=None):
        return DialerEngine(CampaignConfig(mode=mode, max_concurrent_calls=cap), [Agent(str(i)) for i in range(agents)], providers or [MockTelecomProvider("mock", outcomes=[Outcome.NO_ANSWER] * 200)])

    def leads(self, count): return [Lead(str(i), f"+1{i}") for i in range(count)]
    def noon(self): return datetime(2026, 1, 1, 12)


if __name__ == "__main__":
    unittest.main()
