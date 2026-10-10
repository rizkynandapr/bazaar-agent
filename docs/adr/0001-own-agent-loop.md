# ADR-0001: Write the agent loop ourselves instead of using an agent framework

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

The agent needs a tool-calling loop: send messages, run requested tools, feed results back, stop on a final answer or a step limit. Frameworks (LangGraph, PydanticAI, the OpenAI Agents SDK, ...) provide this.

This project exists to demonstrate engineering judgment, and the loop is the part reviewers will ask about. It also has to expose every step to tracing and to the benchmark runner.

## Decision

Implement the loop in plain Python (~150 lines) on top of our own `LLMClient` protocol and Pydantic types. No agent framework.

## Consequences

- ✅ Every line is explainable; no hidden prompts or retries inside a dependency.
- ✅ Tracing, step limits and tool-error handling are first-class, not callbacks bolted on.
- ✅ Fewer dependencies, smaller attack surface.
- ❌ More code to write and test up front.
- ❌ Features like parallel tool calls or durable checkpoints must be built when needed.

**Revisit if** the agent grows into multi-agent orchestration or needs durable long-running workflows.
