# Relay Smart Dialer

A safe, simulated Smart Dialer for demonstrating progressive and predictive dialing. It includes an interactive browser dashboard and a dependency-free Python simulation engine.

> **Demo only:** this project never places real calls and contains no real customer data.

## What it does

A call centre normally has agents dial phone numbers manually. Relay automates the decision of who to call next, while making sure the call is safe to place.

- **Progressive dialing** calls one customer only when an agent is free.
- **Predictive dialing** carefully dials ahead to reduce agent waiting time.
- **Safety controls** skip Do Not Call contacts, respect calling hours, cap repeat attempts, and reduce dialing if abandonment becomes unsafe.
- **Provider resilience** uses mock telecom providers, retries temporary failures, and avoids an unhealthy provider with a circuit breaker.
- **Visibility** shows queue, agents, safety status, provider health, and call activity in the browser dashboard.

## Quick start

### 1. Clone and enter the project

```bash
git clone <your-repository-url>
cd relay-smart-dialer
```

### 2. Run the simulation

No external Python packages are required.

```bash
python -m smartdialer.simulation --mode predictive --leads 300 --agents 8
```

Try safe progressive mode:

```bash
python -m smartdialer.simulation --mode progressive --leads 100 --agents 4
```

### 3. Run the automated tests

```bash
python -m unittest discover -s tests -v
```

### 4. Open the dashboard

Open `index.html` in a modern web browser. Click **Run next call** to advance the UI simulation.

## Project structure

```text
relay-smart-dialer/
├── index.html                 # Interactive dashboard
├── styles.css                 # Dashboard styling
├── app.js                     # Browser-only call simulation
├── smartdialer/
│   ├── models.py              # Lead, agent, call record, campaign settings
│   ├── engine.py              # Campaign loop, concurrency and retries
│   ├── pacing.py              # Predictive dial-ahead controller
│   ├── safety.py              # DNC, hours, attempt and abandon safeguards
│   ├── providers.py           # Mock telecom providers
│   ├── circuit_breaker.py     # Provider health isolation
│   └── simulation.py          # Command-line demo
├── tests/
│   └── test_smartdialer.py    # Automated checks
├── pyproject.toml             # Installable package metadata
├── LICENSE
└── README.md
```

## How the engine works

```text
Leads → safety check → pacing decision → concurrency cap → mock provider
          ↓                    ↓                                ↓
   DNC / hours / cap      progressive or              success, retry, or
     blocks call           predictive target             provider failover
```

The engine uses a safe fallback: if the abandon rate reaches the configured limit, it returns to progressive pacing instead of stopping forever. That allows the campaign to recover with lower-risk calls.

## Verification

The standard-library test suite covers:

- DNC and calling-hours blocking
- maximum calls per lead
- progressive pacing
- predictive pace adjustment
- concurrency limits
- provider retries and circuit breaker behaviour
- emergency-brake fallback

## Optional installation

To install the simulation command locally:

```bash
python -m pip install -e .
smartdialer-sim --mode predictive --leads 300 --agents 8
```

## Interview summary

> “I built a Smart Dialer prototype that simulates automated call-centre dialing. It supports safe progressive dialing and more efficient predictive dialing. Before any call, it enforces Do Not Call rules, approved calling hours, retry limits, agent capacity, and an abandonment-rate safety guard. It also handles provider failures through retries and fallback routing. The project includes a browser dashboard, a runnable simulation, and automated tests.”

## License

Released under the [MIT License](LICENSE).
