# ADR-0002: One `LLMClient` protocol, one OpenAI-compatible adapter

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

BazaarBench must compare many models from many providers, on a near-zero budget (free tiers). The agent must be able to switch models per request (routing, ADR to come).

Options considered:

1. **Each provider's native SDK.** Best feature coverage, but N adapters to maintain.
2. **A multi-provider library (e.g. LiteLLM).** One call for everything, but a large dependency with its own abstractions, release churn and supply-chain surface.
3. **The OpenAI chat-completions wire format through the official `openai` SDK.** OpenRouter, Groq, Gemini, vLLM and most local proxies speak it.

## Decision

Option 3. The codebase depends only on our `LLMClient` protocol (`bazaar/llm/base.py`). `OpenAICompatClient` is the single production adapter; `FakeLLM` is the deterministic test double.

Provider-specific behavior that matters (malformed tool arguments, missing usage, error shapes) is normalized in the adapter, never leaked to callers. Errors never include request content, which may contain customer data.

## Consequences

- ✅ Switching provider or model is a config change.
- ✅ Agent and benchmark tests run offline against `FakeLLM`.
- ❌ Provider-only features (e.g. some caching or reasoning controls) are not available until a dedicated adapter is added behind the same protocol.
