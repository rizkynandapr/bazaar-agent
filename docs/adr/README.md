# Architecture Decision Records

Short notes on decisions that shaped the system: the context, what was chosen, and what it costs.

| # | Decision | Status |
|---|---|---|
| [0001](0001-own-agent-loop.md) | Write the agent loop ourselves | Accepted |
| [0002](0002-openai-compatible-llm-layer.md) | One `LLMClient` protocol, OpenAI-compatible adapter | Accepted |
| [0003](0003-fresh-store-per-session.md) | Fresh in-memory store per conversation | Accepted |
| [0004](0004-bm25-before-embeddings.md) | BM25 retrieval first, embeddings only if evals demand | Accepted |
| [0005](0005-deterministic-grading.md) | Grade by final state and explicit checks, not an LLM judge | Accepted |

New ADRs copy the format of an existing one. Superseded ADRs stay in place with their status changed.
