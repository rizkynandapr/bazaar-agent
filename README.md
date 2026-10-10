# bazaar-agent

**A production-grade WhatsApp commerce agent for Indonesian SMBs, and BazaarBench, the benchmark that measures it.**

> 🚧 Work in progress. **M0 (foundation)** and **M1 (store + BazaarBench v0, 20 tasks)** are built and tested. The results table is filled only from real BazaarBench runs; nothing here is claimed until it is measured.

## Why

Most Indonesian small businesses sell through WhatsApp. Customers write the way they talk: *"kak yg item size M ready ga? kl cod bisa?"*. A support agent has to check real stock, quote real prices and shipping, follow the store's return policy, refuse what it must refuse, and hand over to a human when needed.

Existing agent benchmarks for this kind of work, like [τ-bench](https://github.com/sierra-research/tau-bench), are English and US-centric. Indonesian LLM evaluations measure general language ability, not whether an agent can run a shop's customer service. **BazaarBench** fills that gap, and **bazaar-agent** is built and tuned against it.

## What's inside

| | |
|---|---|
| **BazaarBench** | 20 multi-turn tasks across 6 categories with an LLM-simulated Indonesian customer; graded deterministically by final store state + required/forbidden facts; pass^k consistency. [Details →](benchmark/README.md) |
| **Agent** | Hand-written tool-calling loop over 10 store tools; versioned prompts. Coming: policy retrieval, guardrails, model routing |
| **Production** *(planned)* | FastAPI service, Docker, per-step tracing with token cost and latency, evals gating every PR in CI |

## Results

| Configuration | BazaarBench pass^1 | pass^3 | Tokens / conversation |
|---|---|---|---|
| Baseline prompt (`baseline_v0`) | — | — | — |
| bazaar-agent | — | — | — |

## Quickstart

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). Works on Windows, macOS and Linux.

```bash
git clone https://github.com/rizkynandapr/bazaar-agent.git
cd bazaar-agent
uv sync
uv run pytest                              # 100+ offline tests, no API key needed
uv run python -m bazaar.bench validate     # replay every task's answer key
```

To run the benchmark, copy `.env.example` to `.env` and point it at any OpenAI-compatible endpoint (OpenRouter, Groq, Gemini, a local proxy):

```bash
uv run python -m bazaar.bench ping                                  # check agent + simulator connections
uv run python -m bazaar.bench run --ids T01,T11,T18 --trials 1      # smoke test, 3 tasks
uv run python -m bazaar.bench run --trials 3                        # full run, 20 tasks x 3 trials
```

Each run writes `summary.md`, `summary.json` and `trials.jsonl` (full transcripts with every tool call) to `runs/<run-id>/`. On macOS/Linux, `make check`, `make bench-smoke` and `make bench` are shortcuts.

## Repository layout

```
src/bazaar/
  llm/      provider-agnostic LLM client (OpenAI-compatible adapter + scripted fake)
  store/    fictional store: models, seed data, written policy, tools
  agent/    agent loop and versioned system prompts
  bench/    tasks, customer simulator, runner, graders, pass^k, reports, CLI
benchmark/  BazaarBench task files and datasheet
docs/       architecture, decision records, roadmap
```

## Design

- [Architecture](docs/architecture.md)
- [Decision records](docs/adr/)
- [Roadmap](docs/roadmap.md)

## Data

All store data, customers and conversations in BazaarBench are synthetic. No real customer data is used anywhere in this project.

## License

Code: MIT. Benchmark task data: CC BY 4.0.
