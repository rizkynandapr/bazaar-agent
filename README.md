# bazaar-agent

**A production-grade WhatsApp commerce agent for Indonesian SMBs, and BazaarBench, the benchmark that measures it.**

> 🚧 Work in progress. Milestone **M0 (foundation)** is done. Numbers below will be filled in from real BazaarBench runs; nothing here is claimed until it is measured.

## Why

Most Indonesian small businesses sell through WhatsApp. Customers write the way they talk: *"kak yg item size M ready ga? kl cod bisa?"*. A support agent has to check real stock, quote real prices and shipping, follow the store's return policy, refuse what it must refuse, and hand over to a human when needed.

Existing agent benchmarks for this kind of work, like [τ-bench](https://github.com/sierra-research/tau-bench), are English and US-centric. Indonesian LLM evaluations measure general language ability, not whether an agent can run a shop's customer service. **BazaarBench** fills that gap, and **bazaar-agent** is built and tuned against it.

## What's inside

| | |
|---|---|
| **Agent** | Tool-calling loop, retrieval over store policies, human handover, input/output guardrails, model routing |
| **BazaarBench** | Multi-turn tasks with a simulated customer, graded by final store state + rule checks, pass^k consistency |
| **Production** | FastAPI service, Docker, per-step tracing with token cost and latency, evals gating every PR in CI |

## Results

| Configuration | BazaarBench pass^1 | pass^3 | Cost / conversation | p50 latency |
|---|---|---|---|---|
| Baseline prompt | — | — | — | — |
| bazaar-agent | — | — | — | — |

## Quickstart

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/rizkynandapr/bazaar-agent.git
cd bazaar-agent
uv sync
cp .env.example .env   # add any OpenAI-compatible endpoint + model
make check             # lint, type check, offline tests
make live              # one real call to your endpoint
```

## Design

- [Architecture](docs/architecture.md)
- [Decision records](docs/adr/)
- [Roadmap](docs/roadmap.md)

## Data

All store data, customers and conversations in BazaarBench are synthetic. No real customer data is used anywhere in this project.

## License

MIT
