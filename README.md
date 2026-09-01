# CredResolve SmartDialer

A working, dependency-free SmartDialer prototype built for the Hiring 2026 assignment. It is intentionally a small, explainable design that prioritizes deterministic safety over raw dial volume. It does not place real calls or contain real customer data.

## Run it

Requires Python 3.10+.

```bash
python -m unittest discover -s tests -v
python -m smartdialer.simulation --mode progressive --scenario A --leads 100 --agents 4
python -m smartdialer.simulation --mode predictive --scenario C --leads 300 --agents 8 --drop-agents-at-turn 3 --drop-agent-count 2 --inject-abandon-at-turn 5
python scripts/load_test.py
```

The optional static visual demo remains available by opening [index.html](index.html) in a browser.

## Assignment checklist

- Progressive and predictive pacing modes
- A separate Safety Controller that alone authorizes allocation
- Explicit agent and call state machines
- Atomic agent + borrower reservation using an in-memory lock and SQLite transactional store
- Idempotent provider event processing and terminal-state protection
- Reliable Provider A and duplicate/out-of-order Provider B mocks
- Circuit breaker provider isolation, retry/failover, restart recovery, timed simulations, tests, and a load smoke test
- Architecture decisions and scale plan in [docs/architecture.md](docs/architecture.md)

## Safety boundary

```text
Campaign -> Pacing Engine -> Safety Controller -> Call Allocator -> Telecom Provider
```

The pacer only produces a requested count. It has no provider reference. The Safety Controller can approve, reduce, reject, or force progressive fallback. Every initiated call holds a real agent reservation (a connection token), or an explicitly bound release slot whose call completion is scheduled before the answer event. This permits safe dial-ahead without prediction alone becoming a safety guarantee.

## Design notes

The in-memory repository is the source of truth for the prototype. Its lock makes the borrower + agent reservation one atomic operation, so two worker threads cannot allocate the same agent or lead. Production would preserve that exact invariant with a database transaction / conditional update and a unique active-reservation constraint; a cache would never override the database.

Provider events carry an event ID. Duplicate event IDs are ignored; once a call is terminal, later events are ignored. A restart calls the provider's status endpoint before cancelling a still-unknown reservation. The mock simulates that reconciliation path.

See [docs/architecture.md](docs/architecture.md) for the diagrams, failure walkthroughs, pacing explanation, scaling plan, and the short answer requested in the brief.
For a direct checklist-to-file mapping for reviewers, see [docs/submission_answers.md](docs/submission_answers.md).
The requested concise design response is in [docs/final_question_answer.md](docs/final_question_answer.md).
