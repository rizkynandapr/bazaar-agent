# ADR-0003: Each conversation runs against a fresh copy of the seed store

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

The benchmark grades a task by comparing the final store state to an expected state, so every run must start from an identical, known state. The public demo must not let one visitor's orders or messages leak into another visitor's session, and must not persist personal data typed into a demo.

## Decision

The store is an in-memory Pydantic model loaded from versioned seed data. Every benchmark trial and every demo session gets its own deep copy. Nothing is written to disk.

## Consequences

- ✅ Benchmark runs are reproducible and parallel-safe.
- ✅ The demo stores no customer data by construction.
- ✅ No database to operate.
- ❌ Not a model of a real multi-user production store; a real deployment would put the same tool interface over a database. The tool layer is written against an interface so that swap is local.
