# Submission answers

This document maps the requested submission items to the implementation and explains how to run each part locally.

## How to run

Requirements: Python 3.10+ and no third-party packages.

```bash
python -m unittest discover -s tests -v
python -m smartdialer.simulation --mode progressive --scenario A --leads 100 --agents 4
python -m smartdialer.simulation --mode predictive --scenario C --leads 300 --agents 8 --drop-agents-at-turn 3 --drop-agent-count 2 --inject-abandon-at-turn 5
python scripts/load_test.py
```

## Checklist answers

| Requested item | Where it is implemented |
| --- | --- |
| Working source code | `smartdialer/` contains the dependency-free Python implementation. |
| README with setup instructions | [README.md](../README.md) lists requirements and runnable commands. |
| Architecture diagram | [Architecture decision record](architecture.md) contains the Campaign -> Pacer -> Safety -> Allocator -> Provider diagram. |
| Agent state machine | `AgentState` in `smartdialer/models.py`; rendered Mermaid diagram in `architecture.md`. |
| Call state machine | `CallState` in `smartdialer/models.py`; rendered Mermaid diagram in `architecture.md`. |
| Progressive Dialer | `DialerEngine.run_turn()` with `mode="progressive"`; it approves no more calls than current available agents. |
| Predictive Pacing Engine | `PredictivePacer` in `smartdialer/pacing.py`; it proposes volume from capacity, answer rate, and abandonment feedback. |
| Safety Controller | `SafetyController` in `smartdialer/safety.py`; it alone approves, reduces, rejects, or falls back to progressive capacity. |
| Mock telecom providers | `ReliableMockProvider` and `ChaoticMockProvider` in `smartdialer/providers.py`. Provider B produces failures, duplicate events, and out-of-order events. |
| Tests | `tests/test_smartdialer.py`: 16 automated tests, including races, idempotency, recovery, failover, agent drops, and fallback. |
| Basic simulation | `smartdialer/simulation.py`: scenario A-D, setup/talk-time occupancy, provider behavior, availability drops, and safety fallback injection. |
| Basic load test | `scripts/load_test.py`: 10,000 leads and 1,000 agents with a capacity-invariant check. |
| Short architecture decision document | [architecture.md](architecture.md): safety reasoning, failures, retry policy, multi-worker transaction pattern, and scale plan. |

## Key design answer

Predictive pacing is advisory. A call may be initiated only after Safety Controller approval and only when it has a deterministic connection token: an available agent or a specifically bound, imminent release slot that becomes free before the simulated answer event. When abandonment, provider health, or agent presence is uncertain, Safety Controller immediately reduces to currently protected capacity. This retains predictive scheduling benefits without allowing a prediction to bypass progressive-dialer safety.
