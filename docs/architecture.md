# Architecture

bazaar-agent has two halves that share one codebase:

- **The agent**: a customer-service agent for an Indonesian online fashion store, reachable over an HTTP API (and a demo chat UI).
- **BazaarBench**: a τ-bench-style benchmark that measures the agent (or any model) on realistic, multi-turn Indonesian commerce conversations.

The benchmark is the agent's test suite. Every claim the README makes about the agent is a BazaarBench number.

## System view

```mermaid
flowchart LR
    subgraph Clients
        WA[Demo chat UI / WhatsApp-style client]
        SIM[BazaarBench user simulator<br/>LLM playing a customer]
    end

    subgraph Agent["bazaar.agent"]
        GIN[Input guardrails<br/>injection, length, PII]
        LOOP[Agent loop<br/>plan → tool call → observe]
        ROUTER[Model router<br/>cheap model first, escalate]
        GOUT[Output guardrails<br/>every number must come from a tool]
    end

    subgraph Tools["bazaar.store + bazaar.rag"]
        STORE[(Store state<br/>products, stock, orders, vouchers)]
        RAG[Policy retrieval<br/>returns, shipping, size guide]
        HO[Human handover]
    end

    LLM[[LLMClient<br/>any OpenAI-compatible endpoint]]
    TRACE[(Traces<br/>every step, tokens, cost, latency)]

    WA --> GIN
    SIM --> GIN
    GIN --> LOOP
    LOOP <--> ROUTER
    ROUTER <--> LLM
    LOOP <--> STORE
    LOOP <--> RAG
    LOOP --> HO
    LOOP --> GOUT
    LOOP -.-> TRACE
```

## Benchmark view

```mermaid
flowchart LR
    TASK[Task<br/>persona + secret goal + seed state] --> RUN
    RUN[Runner<br/>simulator ⇄ agent, k trials] --> FINAL[(Final store state<br/>+ transcript)]
    FINAL --> G1[State grader<br/>diff vs expected state]
    FINAL --> G2[Rule graders<br/>no invented prices, handover when required]
    G1 & G2 --> REPORT[Report<br/>pass^k, cost, latency, failure taxonomy]
```

A task passes only if the store ends in exactly the expected state **and** every rule check passes. State comparison is deterministic and costs no LLM calls, which keeps grading cheap and reproducible (τ-bench uses the same idea).

## Package layout

| Package | Responsibility | Milestone |
|---|---|---|
| `bazaar.config` | Settings from env; secrets as `SecretStr` | M0 ✅ |
| `bazaar.llm` | Provider-agnostic `LLMClient`, OpenAI-compatible adapter, `FakeLLM` | M0 ✅ |
| `bazaar.store` | Fashion store domain model, seed data, tool functions | M1 |
| `bazaar.bench` | Task schema, user simulator, runner, graders, reports | M1 |
| `bazaar.agent` | Agent loop, system prompt (versioned), handover | M2 |
| `bazaar.rag` | Policy documents + BM25 retrieval | M2 |
| `bazaar.guardrails` | Input/output checks | M3 |
| `bazaar.routing` | Model routing by difficulty | M3 |
| `bazaar.api` | FastAPI service, rate limiting, demo UI | M5 |

## Decisions

Architecture decisions are recorded in [`docs/adr/`](adr/).
