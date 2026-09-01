# CredResolve SmartDialer

A working, dependency-free SmartDialer prototype built for the Hiring 2026 assignment. It is intentionally a small, explainable design that prioritizes deterministic safety over raw dial volume. It does not place real calls or contain real customer data.

## Run it

Requires Python 3.10+.

```bash
python -m unittest discover -s tests -v
python -m smartdialer.simulation --mode progressive --scenario A --leads 100 --agents 4
python -m smartdialer.simulation --mode predictive --scenario C --leads 300 --agents 8
python scripts/load_test.py
```

The optional static visual demo remains available by opening [index.html](index.html) in a browser.

## Assignment checklist

- Progressive and predictive pacing modes
- A separate Safety Controller that alone authorizes allocation
- Explicit agent and call state machines
- Atomic agent + borrower reservation using a repository lock
- Idempotent provider event processing and terminal-state protection
- Reliable Provider A and duplicate/out-of-order Provider B mocks
- Circuit breaker provider isolation, restart recovery, simulations, tests, and a load smoke test
- Architecture decisions and scale plan in [docs/architecture.md](docs/architecture.md)

## Safety boundary

```text
Campaign -> Pacing Engine -> Safety Controller -> Call Allocator -> Telecom Provider
```

The pacer only produces a requested count. It has no provider reference. The Safety Controller can approve, reduce, reject, or force progressive fallback. In this prototype every initiated call holds a real agent reservation (a connection token), so predictive requests above protected capacity are reduced. This sacrifices aggressive oversubscription while making the no-abandon invariant deterministic.

## Design notes

The in-memory repository is the source of truth for the prototype. Its lock makes the borrower + agent reservation one atomic operation, so two worker threads cannot allocate the same agent or lead. Production would preserve that exact invariant with a database transaction / conditional update and a unique active-reservation constraint; a cache would never override the database.

Provider events carry an event ID. Duplicate event IDs are ignored; once a call is terminal, later events are ignored. A restart calls the provider's status endpoint before cancelling a still-unknown reservation. The mock simulates that reconciliation path.

See [docs/architecture.md](docs/architecture.md) for the diagrams, failure walkthroughs, pacing explanation, scaling plan, and the short answer requested in the brief.
