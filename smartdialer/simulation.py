import argparse
from datetime import datetime

from .engine import DialerEngine
from .models import Agent, CampaignConfig, Lead
from .providers import ChaoticMockProvider, ReliableMockProvider

SCENARIOS = {"A": (.20, 120), "B": (.50, 90), "C": (.70, 180), "D": (.32, 120)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a safe SmartDialer simulation")
    parser.add_argument("--mode", choices=["progressive", "predictive"], default="predictive")
    parser.add_argument("--scenario", choices=SCENARIOS, default="D")
    parser.add_argument("--leads", type=int, default=300)
    parser.add_argument("--agents", type=int, default=8)
    args = parser.parse_args()
    answer_rate, talk_time = SCENARIOS[args.scenario]
    config = CampaignConfig(mode=args.mode, start_hour=0, end_hour=24)
    providers = [ReliableMockProvider(), ChaoticMockProvider()]
    providers[0].answer_rate, providers[1].answer_rate = answer_rate, answer_rate
    engine = DialerEngine(config, [Agent(str(n)) for n in range(args.agents)], providers)
    leads = [Lead(str(n), f"+155500{n:04d}", dnc=(n == 7)) for n in range(args.leads)]
    while any(not lead.dnc and lead.attempts < config.max_attempts_per_lead for lead in leads):
        engine.run_turn(leads, datetime(2026, 8, 30, 12, 0))
    print(f"Scenario {args.scenario}: answer rate={answer_rate:.0%}, avg talk time={talk_time}s")
    for key, value in engine.summary().items(): print(f"{key.replace('_', ' ').title()}: {value}")
    print("Last safety decision:", engine.safety.decisions[-1])


if __name__ == "__main__":
    main()
