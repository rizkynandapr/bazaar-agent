# ADR-0005: Grade by final state and explicit string checks, not by an LLM judge

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

BazaarBench must produce scores that are cheap to compute, reproducible, and trusted by people who did not build it. Two families of graders exist:

1. **LLM-as-judge**: a model reads the transcript and scores it against a rubric. Flexible, but costs money per run, varies between judge models and versions, and must itself be validated against human labels.
2. **Outcome checks**: compare the final database state with the state an ideal agent would produce, plus checks on specific facts the agent must or must not say. τ-bench uses this approach.

## Decision

Use outcome checks only in v0. The expected state is not written by hand; it is produced by replaying the task's `expected_actions` through the same tool code the agent uses, so the grader and the agent cannot disagree about what a tool does. Free-text fields (address, customer name, handover summary) are excluded from comparison. Required and forbidden amounts are parsed from common Indonesian formats.

## Consequences

- ✅ Zero grading cost, fully deterministic, and explainable failure reasons ("order ORD-1009 differs in total").
- ✅ Answer keys are themselves testable in CI.
- ❌ Conversation quality (tone, clarity, asking for confirmation) is not scored.
- ❌ An agent can say the right number in a confusing way and still pass.

**Revisit** when v1 adds tone and clarity metrics; any LLM judge introduced then will be calibrated against a human-labeled sample first.
