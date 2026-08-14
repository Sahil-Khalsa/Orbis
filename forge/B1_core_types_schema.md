# B1 — Core types + schema

Paste after `architecture.md` context is loaded. Done when: all tables below exist in the `orbis-dev` database, confirmed from a shell in the sandbox.

---

You are building Orbis, the authorization layer for AI agents taking consequential actions. An agent runs in a sandbox with no payment credentials — it can only ask. Every spend request is adjudicated against a warrant and six deterministic rules; clean requests execute (agent-to-bank or agent-to-agent), ambiguous or violating ones route to a human.

Five invariants that constrain everything you generate, in this step and every step after:
1. Money never moves on a model decision — rules decide; an LLM reasoner may only run on explicit DEFER, and its return type must contain no "approve" value.
2. Money is always integer cents. No floats, no Decimal, anywhere in the money path.
3. Every decision cites a policy artifact — a rule ID, a warrant clause, or both.
4. The reasoner never sees raw untrusted text — only structured/extracted fields.
5. The agent holds no credentials — it can only reach the Orbis API.

For this step, generate only the core types and database schema. No business logic yet.

**Core types:**
- `Outcome` = `AUTO_APPROVE | ROUTE_TO_HUMAN | BLOCK | DEFER`
- `DestinationType` = `bank | agent`

**Data model** (money as integer cents throughout):

```
principals(id, name, email, role)

agents(id, name, principal_id, sandbox_id, kind, wallet_id, status)
                                    -- kind: spender | payee
                                    -- status: active | frozen

warrants(id, agent_id, principal_id, categories,
         ceiling_per_txn_cents, ceiling_total_cents,
         vendor_scope, counterparty_scope,
         valid_from, valid_until, status, clause_text)

vendors(id, canonical_name, aliases, status, first_seen_at)

budgets(id, category, period_start, period_end,
        budgeted_cents, committed_cents)

transactions(id, destination_type, vendor_id, counterparty_agent_id,
             category, amount_cents, occurred_at, description,
             recurring, stripe_ref, spend_request_id)
                                    -- destination_type: bank | agent

spend_requests(id, agent_id, warrant_id, destination_type,
               vendor_name_raw, counterparty_agent_id, category,
               amount_cents, business_purpose_raw, submitted_at, status)

extractions(id, spend_request_id, vendor_name_norm, vendor_id_match,
            match_confidence, purpose_class, line_items, injection_flags)

decisions(id, spend_request_id, outcome, decided_at, decided_by,
          rationale, cited_rule_ids, cited_warrant_id)

rule_results(id, decision_id, rule_id, outcome, reason_code,
             detail, evidence_ids)

approvals(id, decision_id, principal_id, action, note, acted_at)
```

**Requirements:**
- `amount_cents`, `ceiling_per_txn_cents`, `ceiling_total_cents`, `budgeted_cents`, `committed_cents` are integers everywhere — in the schema, any generated ORM models, and any API types. Never a float or decimal type.
- `destination_type` must exist on both `transactions` and `spend_requests`, and must be easy to render in the UI later — don't bury it behind a join.
- `category` (on warrants, budgets, transactions, spend_requests) is a fixed enum: `infrastructure, software, legal, contractor, marketing, travel, hardware, other`.
- `outcome` on `decisions` is one of `AUTO_APPROVE, ROUTE_TO_HUMAN, BLOCK` only — `DEFER` is a transient in-memory adjudication state and must never be persisted.
- `rule_id` on `rule_results` is one of `R1`..`R6`.
- Don't build the spend-request API, rules, or UI yet — those are the next steps. Just get these tables created and live in `orbis-dev`.
