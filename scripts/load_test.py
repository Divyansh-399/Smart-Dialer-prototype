"""Dependency-free throughput smoke test; this is not a telecom benchmark."""
from datetime import datetime
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from smartdialer.engine import DialerEngine
from smartdialer.models import Agent, CampaignConfig, Lead
from smartdialer.providers import ReliableMockProvider


def main() -> None:
    lead_count, agent_count = 10_000, 1_000
    engine = DialerEngine(CampaignConfig(mode="predictive", start_hour=0, end_hour=24, max_concurrent_calls=agent_count), [Agent(str(i)) for i in range(agent_count)], [ReliableMockProvider()])
    leads = [Lead(str(i), f"+1555{i:07d}") for i in range(lead_count)]
    started = perf_counter(); engine.run_turn(leads, datetime(2026, 1, 1, 12)); seconds = perf_counter() - started
    print(f"Reserved and processed {len(engine.records)} calls from {lead_count:,} leads in {seconds:.3f}s.")
    print("Invariant: max batch <= available agents:", engine.max_seen_concurrent <= agent_count)


if __name__ == "__main__":
    main()
