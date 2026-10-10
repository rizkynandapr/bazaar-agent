# ADR-0004: Start retrieval with BM25; add embeddings only if evals show misses

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

The agent answers policy questions (returns, shipping, size guide, payment) from a small corpus of store documents: tens of chunks, not millions. Customers write informal, code-mixed Indonesian.

## Decision

Ship M2 with BM25 keyword retrieval plus light normalization (lowercasing, common slang/abbreviation expansion such as "brp" → "berapa", "ongkir" → "ongkos kirim"). Track retrieval hit-rate as a BazaarBench metric. Add an embedding retriever (hybrid) only if that metric shows misses that BM25 cannot fix.

## Consequences

- ✅ Zero cost, zero extra service, deterministic, fast.
- ✅ The decision to add embeddings will be backed by a number, not a default.
- ❌ Paraphrased questions with no shared keywords may be missed until the hybrid step.
