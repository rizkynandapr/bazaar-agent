# BazaarBench

A τ-bench-style benchmark for customer-service agents in **Indonesian online commerce**: multi-turn conversations with a simulated customer, real tool use against a store database, and written store policy the agent must follow.

## Why it exists

Agent benchmarks for policy-bound customer service, notably [τ-bench](https://github.com/sierra-research/tau-bench), are English and US-centric. Indonesian LLM evaluations such as SEA-HELM measure general language ability, not whether an agent can run a shop's customer service. Indonesian small businesses sell largely through chat, and customers write informally: abbreviations, typos, code-mixing with English and regional languages. BazaarBench measures agents in that setting.

## How a task works

1. A fresh copy of the **Senja Wear** seed store is loaded (a fictional fashion store; "today" is fixed to 2026-10-12 so date rules are deterministic).
2. An LLM **customer simulator** receives a persona and a private instruction (its goal, the facts it knows, how to react). It chats in informal Indonesian and reveals information gradually.
3. The **agent under test** answers, calling tools (`search_products`, `get_order`, `create_order`, `cancel_order`, `request_return`, `handover_to_human`, ...).
4. The conversation ends when the customer is done, the agent hands over to a human, or a turn limit is hit.
5. **Grading is deterministic, with no LLM judge:**
   - The task's `expected_actions` are replayed on a fresh store. The agent passes the state check only if its final store state is identical (free-text fields such as address and name are ignored; stock, items, totals, statuses, returns and handover count are compared).
   - Required amounts (e.g. the order total) must appear in the agent's messages; forbidden amounts or strings (e.g. another customer's order details) must not. Amounts are parsed from Indonesian formats: `Rp259.000`, `259rb`, `259k`, `1,5 jt`.

Reported metric is **pass^k**: the probability that all k independent trials of a task succeed. pass^1 is accuracy; higher k exposes inconsistency.

## v0 task set

20 hand-written tasks in [`tasks/v0.yaml`](tasks/v0.yaml).

| Category | Tasks | What it tests |
|---|---|---|
| `happy_path` | T01–T04 | Ordering, vouchers, shipping quotes, order lookup |
| `edge_case` | T05–T10 | Out-of-stock, partial stock, expired or under-minimum vouchers, COD unavailable, cancellation |
| `policy_refusal` | T11–T15 | Refusing what policy forbids (shipped cancellation, late return, final sale, change of mind), plus one valid return |
| `handover` | T16–T17 | Payment disputes, bulk orders |
| `adversarial` | T18–T19 | Social engineering for another customer's data; prompt injection for a discount |
| `language` | T20 | Javanese–Indonesian code-mixing |

## Answer-key quality

τ-bench's maintainers later published a cleaned airline subset after finding tasks with wrong or ambiguous answer keys. BazaarBench guards against that in CI (`tests/test_tasks.py`):

- every task's expected actions must replay without errors on the seed store;
- every task that creates an order must require the agent to state that order's exact total, as computed by the store;
- required and forbidden checks may not overlap.

Hard business invariants (stock, voucher validity, COD availability, cancellable status) are enforced by the tools. Soft rules (identity verification, the 7-day return window, final sale, acceptable return reasons, when to hand over) are enforced **only by the written policy** (`src/bazaar/store/policies.md`). That gap is what the benchmark measures.

## Known limitations of v0

- 20 tasks is small; per-category rates have wide error bars. v1 targets 40–60 tasks.
- The customer simulator is itself an LLM and can drift from its instruction. Use the strongest simulator model available, run k ≥ 3 trials, and read failing transcripts before trusting a number.
- Only one store domain (fashion) and one regional language mix.
- Some policy behavior (asking for confirmation before writes) is not graded directly.

## Data

All people, phone numbers, addresses and orders are fictional. No real customer data is used. Task data is released under CC BY 4.0; code under MIT.
