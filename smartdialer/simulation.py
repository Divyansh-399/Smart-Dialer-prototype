import argparse
from collections import Counter
from datetime import datetime

from .engine import DialerEngine
from .models import Agent, CallRecord, CallState, CampaignConfig, Lead, Outcome
from .providers import ChaoticMockProvider, ReliableMockProvider

SCENARIOS = {"A": (.20, 120), "B": (.50, 90), "C": (.70, 180), "D": (.32, 120)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a safe SmartDialer simulation")
    parser.add_argument("--mode", choices=["progressive", "predictive"], default="predictive")
    parser.add_argument("--scenario", choices=SCENARIOS, default="D")
    parser.add_argument("--leads", type=int, default=300)
    parser.add_argument("--agents", type=int, default=8)
    parser.add_argument("--drop-agents-at-turn", type=int, default=0)
    parser.add_argument("--drop-agent-count", type=int, default=0)
    parser.add_argument("--inject-abandon-at-turn", type=int, default=0)
    args = parser.parse_args()
    answer_rate, talk_seconds = SCENARIOS[args.scenario]
    config = CampaignConfig(mode=args.mode, start_hour=0, end_hour=24)
    talk_turns = max(1, talk_seconds // config.turn_seconds)
    providers = [ReliableMockProvider(setup_turns=1, talk_turns=talk_turns),
                 ChaoticMockProvider(setup_turns=1, talk_turns=talk_turns)]
    for provider in providers:
        provider.answer_rate = answer_rate
    engine = DialerEngine(config, [Agent(str(n)) for n in range(args.agents)], providers)
    leads = [Lead(str(n), f"+155500{n:04d}", dnc=(n == 7)) for n in range(args.leads)]
    while (any(not lead.dnc and lead.attempts < config.max_attempts_per_lead for lead in leads) or engine.pending_events) and engine.turn < 1_000:
        next_turn = engine.turn + 1
        if args.inject_abandon_at_turn == next_turn:
            engine.records.append(CallRecord("safety-probe", Outcome.ABANDONED, state=CallState.COMPLETED))
        if args.drop_agents_at_turn == next_turn:
            engine.mark_agents_unavailable([str(i) for i in range(min(args.drop_agent_count, args.agents))])
        engine.run_turn(leads, datetime(2026, 8, 30, 12, 0))
    print(f"Scenario {args.scenario}: answer rate={answer_rate:.0%}, avg talk time={talk_seconds}s")
    for key, value in engine.summary().items():
        print(f"{key.replace('_', ' ').title()}: {value}")
    print("Safety decisions:", dict(Counter(decision.reason for decision in engine.safety.decisions)))
    print("Safety reductions:", sum(decision.approved < decision.requested for decision in engine.safety.decisions))


if __name__ == "__main__":
    main()
