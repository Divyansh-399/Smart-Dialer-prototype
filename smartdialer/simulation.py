import argparse
from datetime import datetime

from .engine import DialerEngine
from .models import Agent, CampaignConfig, Lead
from .providers import MockTelecomProvider


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a safe smart dialer simulation")
    parser.add_argument("--mode", choices=["progressive", "predictive"], default="predictive")
    parser.add_argument("--leads", type=int, default=300)
    parser.add_argument("--agents", type=int, default=8)
    args = parser.parse_args()
    config = CampaignConfig(mode=args.mode, start_hour=0, end_hour=24)
    engine = DialerEngine(config, [Agent(str(n)) for n in range(args.agents)], [MockTelecomProvider("MockTwilio"), MockTelecomProvider("MockTelnyx")])
    leads = [Lead(str(n), f"+155500{n:04d}", dnc=(n == 7)) for n in range(args.leads)]
    while any(not lead.dnc and lead.attempts < config.max_attempts_per_lead for lead in leads):
        engine.run_turn(leads, datetime(2026, 8, 30, 12, 0))
    summary = engine.summary()
    print("SmartDialer simulation complete")
    for key, value in summary.items():
        print(f"{key.replace('_', ' ').title()}: {value}")


if __name__ == "__main__":
    main()
