<div align="center">

# Orbis
### Authorization Layer for AI Agents

<p>
  <img src="https://img.shields.io/badge/Python-3.13-3776ab?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-0.111-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/SQLite-Latest-003B57?style=for-the-badge&logo=sqlite&logoColor=white" />
  <img src="https://img.shields.io/badge/Stripe-API-635BFF?style=for-the-badge&logo=stripe&logoColor=white" />
  <img src="https://img.shields.io/badge/Pydantic-v2-E92063?style=for-the-badge&logo=pydantic&logoColor=white" />
  <img src="https://img.shields.io/badge/Rules-6_Deterministic-brightgreen?style=for-the-badge" />
</p>

**Orbis** is a deterministic authorization engine for AI agents taking consequential financial actions. An agent running in a sandboxed environment with no payment credentials can only *ask*. Every spend request is adjudicated against a warrant and six deterministic rules; clean ones execute agent-to-bank or agent-to-agent, ambiguous or violating ones route to a human for approval.

> **Money never moves on a model decision.** Rules produce the outcome. The LLM runs only on deferred cases, and its return type is deterministic: ROUTE, BLOCK, or CLEAR_DEFERRAL.

[What Makes This Different](#what-makes-this-different) | [Architecture](#system-architecture) | [Six Rules](#six-deterministic-rules) | [Features](#features) | [Quick Start](#quick-start)

</div>

---

## What Makes This Different

Most authorization systems are a black box: "approved" or "denied" with no audit trail. Orbis is transparent and deterministic.

| Traditional Authorization | Orbis |
|---|---|
| Centralized approval workflow | Deterministic rules run first; only ambiguous cases need a human |
| LLM decides, money moves | Rules decide, LLM only clarifies ambiguous matches |
| No audit trail | Every decision cites a rule and a warrant |
| Manual fraud review | Automated velocity, duplicate, and budget detection run on every request |
| Single destination (bank) | Supports both bank transfers and agent-to-agent settlements with same rules |
| No warrant enforcement | Every spend request must fall within an active warrant's scope |
| Vendor name is just text | Normalized vendor matching with confidence scoring (0.0-1.0) and ambiguity detection |

---

## System Architecture

```
╔════════════════════════════════════════════════════════════════════════════╗
║                    Orbis - Spend Request Adjudication                     ║
╠════════════════════════════════════════════════════════════════════════════╣
║                                                                            ║
║  Agent Sandbox (no credentials)        Human Approver (Orbis UI)          ║
║  ────────────────────────────────      ──────────────────────────         ║
║  Cannot access:                        Can view:                           ║
║  - Stripe key                          - Spend queue                       ║
║  - Database                            - Decision details                  ║
║  - Rules engine                        - Audit trail                       ║
║  - Warrants                            - Shadow report                     ║
║         │                                      │                          ║
║         │ POST /spend-requests                 │                          ║
║         ▼                                      ▼                          ║
║  ┌─────────────────────────────┐    ┌──────────────────────────┐         ║
║  │   agent_id                  │    │  /ui/queue               │         ║
║  │   destination_type          │    │  /ui/decisions/{id}      │         ║
║  │   vendor_name_raw           │    │  /ui/shadow (audit)      │         ║
║  │   business_purpose_raw      │    └──────────────────────────┘         ║
║  │   amount_cents              │                                          ║
║  │   category                  │                                          ║
║  └────────────┬────────────────┘                                          ║
║               │                                                            ║
║               ▼                                                            ║
║  ┌───────────────────────────────────────────────────────────────┐        ║
║  │                    SQLite Database                             │        ║
║  │  spend_requests | warrants | budgets | agents | transactions  │        ║
║  │  decisions | rule_results | approvals | ledger | audit        │        ║
║  └───────────────┬─────────────────────────────────────────────┘        ║
║                  │                                                        ║
║                  ▼                                                        ║
║  ┌───────────────────────────────────────────────────────────────┐        ║
║  │                    Adjudication Pipeline                       │        ║
║  └───────────────────────────────────────────────────────────────┘        ║
║                               │                                           ║
║  ┌────────────────────────────┼─────────────────────────────┐            ║
║  │                            │                             │            ║
║  ▼                            ▼                             ▼            ║
║ ┌────────────────┐  ┌──────────────────────┐  ┌────────────────────┐   ║
║ │  Extraction    │  │   All Six Rules Run  │  │  Decision Logic    │   ║
║ │ (normalize     │  │  (R1–R6 always)      │  │  (precedence:      │   ║
║ │  vendor name,  │  │  - Warrant           │  │   BLOCK > ROUTE    │   ║
║ │  purpose,      │  │  - Budget            │  │   > DEFER >        │   ║
║ │  injection     │  │  - Counterparty      │  │   AUTO_APPROVE)    │   ║
║ │  flags)        │  │  - Duplicate         │  │                    │   ║
║ │                │  │  - Velocity          │  │  Injection flags → │   ║
║ │                │  │  - Threshold         │  │  ROUTE_TO_HUMAN    │   ║
║ └────────────────┘  └──────────────────────┘  └────────────────────┘   ║
║  │                          │                            │                ║
║  └──────────────┬───────────┴────────────────────────────┘                ║
║                 ▼                                                          ║
║         ┌────────────────────┐                                            ║
║         │  DEFER Case Only?  │                                            ║
║         │  (confidence band  │                                            ║
║         │   0.65–0.90)       │                                            ║
║         └────────────────────┘                                            ║
║              │        │                                                   ║
║         NO   │        │   YES                                             ║
║              │        └──────────────┐                                    ║
║              ▼                       ▼                                    ║
║      ┌──────────────┐      ┌────────────────┐                            ║
║      │  AUTO_       │      │   Reasoner     │                            ║
║      │  APPROVE or  │      │   (LLM only    │                            ║
║      │  ROUTE or    │      │   here)        │                            ║
║      │  BLOCK       │      │                │                            ║
║      └──────┬───────┘      └────────┬───────┘                            ║
║             │                       │                                    ║
║             └───────────┬───────────┘                                    ║
║                         ▼                                                 ║
║         ┌──────────────────────────┐                                      ║
║         │   Persist Decision       │                                      ║
║         │   + cite rule IDs or     │                                      ║
║         │   warrant ID (assert)    │                                      ║
║         └────────────┬─────────────┘                                      ║
║                      ▼                                                     ║
║      ┌────────────────────────────────┐                                   ║
║      │  Branch by Outcome             │                                   ║
║      └────────────────────────────────┘                                   ║
║      │              │               │                                    ║
║  AUTO│APPROVE   ROUTE│TO_HUMAN   BLOCK                                   ║
║      │              │               │                                    ║
║      ▼              ▼               ▼                                    ║
║  ┌─────────┐  ┌──────────┐   ┌──────────┐                               ║
║  │ Execute │  │ Approval │   │ Stop     │                               ║
║  │ Payment │  │ Queue    │   │ Request  │                               ║
║  └─────────┘  └──────────┘   └──────────┘                               ║
║
║  destination_type=bank    → Stripe PaymentIntent                         ║
║  destination_type=agent   → Transfer to counterparty agent wallet        ║
║                                                                           ║
╚════════════════════════════════════════════════════════════════════════════╝
```

---

## Six Deterministic Rules

Every spend request is evaluated against all six rules. **No short-circuiting.** All results are shown in the decision view.

| ID | Rule | Logic | Outcome |
|---|---|---|---|
| **R1** | Warrant | Active, valid date range, category allowed, per-txn and total ceilings respected, destination within scope | BLOCK or DEFER |
| **R2** | Budget | Committed spend + new amount vs quarterly budget: ≤105% PASS | ≤120% ROUTE | >120% BLOCK | ROUTE or BLOCK |
| **R3** | Counterparty | Vendor status: approved PASS | pending ROUTE | blocked BLOCK | confidence [0.65–0.90) DEFER | unresolvable ROUTE NEW_VENDOR | DEFER, ROUTE, or BLOCK |
| **R4** | Duplicate | Prior txn same vendor ±5% amount within 30 days same category: recurring DEFER | else BLOCK DUPLICATE_SUSPECTED | DEFER or BLOCK |
| **R5** | Velocity | >5 requests in 10 min OR trailing-1h spend > 4× trailing-30d hourly baseline → BLOCK + freeze agent | BLOCK |
| **R6** | Threshold | Amount > $5,000 OR amount > $2,000 in legal/contractor/marketing → ROUTE APPROVAL_REQUIRED | ROUTE |

**Precedence:** BLOCK > ROUTE_TO_HUMAN > DEFER > AUTO_APPROVE

---

## Features

### Deterministic Decision Engine

- **Warrant-scoped spending** - every request checked against active warrant, category, and per-transaction ceiling
- **Budget enforcement** - quarterly committed spend tracked; headroom warnings at 105%, block at 120%
- **Vendor reconciliation** - normalized vendor matching with RapidFuzz (0.0–1.0 confidence); ambiguous matches (0.65–0.90) defer to reasoner
- **Duplicate detection** - flags similar transactions within 30 days; recurring true positives marked for reasoner
- **Velocity anomaly detection** - agents frozen after 6 requests in 10 minutes or anomalous hourly spend patterns
- **Approval thresholds** - hard-coded ceilings per transaction size and category (legal/contractor/marketing)

### Agent Isolation

- **Sandboxed agents** have no access to payment credentials, database, or rules engine
- **Egress restricted** - agents can only POST to the Orbis API
- **Warrant enforcement** - agents cannot bypass spending limits by any means

### Human-in-the-Loop Workflow

- **Decision queue** - view all routed (ROUTE_TO_HUMAN) decisions in `/ui/queue`
- **Decision detail** - click through to see rule results, extraction, and warrant clause
- **Approve/deny** - principal-signed approval with timestamp; approval triggers execution
- **Audit trail** - every decision persists rule results, cited warrant, rationale, and evidence IDs

### Execution & Ledger

- **Idempotent Stripe integration** - test-mode PaymentIntent creation, no live key accepted at startup
- **Agent-to-agent settlement** - destination_type=agent transfers to counterparty wallet
- **Ledger write-back** - on approval, transaction inserted, budgets incremented, decision closed
- **Dead-letter retry** - failed execution retried once; persistent failures escalate to human queue

### Shadow Audit Report

- **Backtesting engine** - replay adjudicate() over historical data as if each transaction were submitted today
- **Violation detection** - surface spending that would have been caught, with rule IDs and reason codes
- **Impact analysis** - total dollars at risk across all violations
- **Evidence traceability** - each finding includes transaction ID, rule fired, and amount

### Extraction & Reasoner

- **Extraction boundary** - only component permitted to read raw vendor_name_raw and business_purpose_raw
- **Injection detection** - flags authority-claiming language ("pre-approved", "skip review") in memo text
- **Reasoner** - runs only on DEFER; resolves ambiguous vendor matches and duplicate-vs-recurring decisions
- **Faithfulness validator** - deterministic check that cited evidence and clauses actually exist

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.13, FastAPI, Pydantic v2 |
| **Database** | SQLite (deterministic, seed-reproducible) |
| **Frontend** | Jinja2 server-rendered templates, Tailwind CSS |
| **Payment** | Stripe Test API (PaymentIntent) |
| **Vendor Matching** | RapidFuzz token_sort_ratio |
| **AI - Reasoner** | Anthropic Claude (Sonnet 4 or Haiku 4.5) |
| **Background** | APScheduler for demo scheduling |

---

## Project Structure

```
Orbis/
├── fallback/                          # Core local build
│   ├── main.py                        # FastAPI app + API routes + UI endpoints
│   ├── db.py                          # SQLite connection, schema, migrations
│   ├── schema.sql                     # 11 tables: spend_requests, warrants, budgets, etc.
│   ├── types.py                       # Pydantic models: SpendRequest, Decision, RuleResult
│   ├── extraction.py                  # Vendor normalization, injection flagging
│   ├── orchestrator.py                # Main adjudication pipeline
│   ├── rules/                         # Six rule implementations
│   │   ├── __init__.py
│   │   ├── r1_warrant.py             # R1: warrant scope + ceiling checks
│   │   ├── r2_budget.py              # R2: quarterly budget headroom
│   │   ├── r3_counterparty.py        # R3: vendor status & confidence band
│   │   ├── r4_duplicate.py           # R4: recurring vs suspected duplicate
│   │   ├── r5_velocity.py            # R5: request rate + hourly spend anomaly
│   │   └── r6_threshold.py           # R6: amount-based approval threshold
│   ├── reasoner.py                    # LLM for deferred cases + faithfulness validator
│   ├── matcher.py                     # Vendor name fuzzy matching (RapidFuzz)
│   ├── state.py                       # State loader: warrants, budgets, velocity, txn history
│   ├── execution.py                   # Stripe integration, ledger write-back
│   ├── shadow.py                      # Shadow report engine (backtesting)
│   ├── seed.py                        # Deterministic seed data (--seed 42)
│   ├── templates/                     # Jinja2 UI templates
│   │   ├── base.html
│   │   ├── home.html                 # Dashboard overview
│   │   ├── queue.html                # Approval queue
│   │   ├── decision.html             # Decision detail + rule results
│   │   └── shadow.html               # Shadow audit report view
│   └── requirements.txt
├── agents/                            # Agent sandbox implementations
│   ├── common.py                      # Shared: ORBIS_API_URL constant
│   ├── agent_ops.py                   # Spender: requests auto-approve, A2A, hero blocks
│   ├── agent_vendor.py                # Payee: issues invoice, awaits settlement
│   ├── agent_runaway.py               # Velocity test: burst 9 requests
│   └── agent_hostile.py               # Injection test: invoice with authority claims
├── tests/                             # Unit tests
├── demo.py                            # 9-beat demo harness (orchestrates live runs)
├── CLAUDE.md                          # Build guide + invariants
├── architecture.md                    # System design & decision rationale
├── README.md                          # This file
└── .env.example                       # Copy to .env, fill STRIPE_SECRET_KEY
```

---

## Database Schema - 11 Tables

```
spend_requests          agent, vendor, category, amount, warrant, status
warrants                agent, category, per-txn/total ceilings, dates, scope
budgets                 agent, quarter, budgeted/committed cents, principal
agents                  id, name, status (active/frozen), principal
counterparties          vendor_id, name, status (approved/pending/blocked)
decisions               spend_request_id, outcome, decided_by, rationale, cited_rule_ids
rule_results            decision_id, rule_id, outcome, reason_code, evidence_ids
extractions             spend_request_id, vendor_norm, confidence, injection_flags
approvals               decision_id, principal_id, action (approve/deny), note
transactions            spend_request_id, stripe_txn_id, amount_cents, status
audit_events            action (adjudicate, approve, execute), decision_id, timestamp
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Stripe account (test-mode API key)
- OpenAI or Anthropic API key (for reasoner, optional for DEFER cases)

### 1 - Install & Setup

```bash
# Clone and enter directory
cd Orbis

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env and set:
#   STRIPE_SECRET_KEY=sk_test_...  (required, test mode only)
#   OPENAI_API_KEY=...              (optional, for reasoner)
```

### 2 - Initialize Database with Seed Data

```bash
# Deterministic seed: 6 months, 385 clean txns, 7 planted violations
python -m fallback.seed --seed 42
```

### 3 - Start the Orbis API Server

```bash
# Boots only with test-mode Stripe key (sk_test_ prefix)
uvicorn fallback.main:app --port 8734

# Server ready at http://localhost:8734
```

### 4 - Run the 9-Beat Demo

**In another terminal:**

```bash
source venv/bin/activate
python demo.py
```

**Output: 9 demo beats**

1. ✅ Agent isolation boundary verification
2. ✅ Clean $200 auto-approve
3. ✅ Agent-to-agent settlement
4. ✅ **THE BLOCK** - $4,200 misspelled vendor vs $4,080 from 11 days prior
5. ✅ Velocity anomaly (R5 freezes agent after 6 requests in 10 min)
6. ✅ Injection flagging (hostile memo routed, not executed)
7. ✅ Human approval ($9,000 routes, principal approves, payment executes)
8. ✅ Shadow report (7 violations, $28,976.85 impact)
9. ✅ Close

---

## Access the UI

Once the server is running:

- **Home** - http://localhost:8734/
- **Approval Queue** - http://localhost:8734/ui/queue
- **Decision Detail** - http://localhost:8734/ui/decisions/{decision_id}
- **Shadow Audit** - http://localhost:8734/ui/shadow
- **Agent List** - http://localhost:8734/agents

---

## Running Tests

```bash
pytest tests/ -v
```

All tests are unit tests (no database required, mocked fixtures).

---

## Five Non-Negotiable Invariants

These constraints are enforced in code and must never be violated:

1. **Money never moves on a model decision.**  
   Rules produce the outcome. The LLM runs only on DEFER, and its return type is `Literal["ROUTE","BLOCK","CLEAR_DEFERRAL"]` - no approval value exists. Enforce with schema, not prompt instructions.

2. **Money is always integer cents.**  
   No floats, no `Decimal`, anywhere in the money path.

3. **Every decision cites a policy artifact.**  
   `cited_rule_ids` non-empty OR `cited_warrant_id` set. Assert before persisting.

4. **The reasoner never receives raw text.**  
   `vendor_name_raw` and `business_purpose_raw` are readable only by the extractor. No other component reads or forwards them.

5. **The agent holds no credentials.**  
   No Stripe key, no secrets, no egress except the Orbis API. Enforced by the sandbox boundary.

---

## Key Engineering Decisions

### 1. Deterministic Rules Before Any AI
The LLM in the reasoner only ever clarifies what the rules have already proven ambiguous. It never discovers insights on its own. Every decision is traceable to a rule and a warrant.

**Why:** Clinical/financial governance requires auditable provenance. A human approver must be able to point to the rule that fired and understand exactly why the system routed the request.

### 2. All Six Rules Always Run - No Short-Circuit
Even if R1 (warrant) blocks the request, R2–R6 still run so the decision view shows every failure point. This surfaces systematic issues (e.g., "this agent exceeds budget across multiple transactions").

**Why:** Visibility into rule conflicts helps the human approver make better decisions and identifies policy gaps.

### 3. Vendor Confidence Bands Over Hard Thresholds
Confidence [0, 0.65) → route (human decides); [0.65, 0.90) → defer (reasoner clarifies); [0.90, 1.0] → execute (high confidence).

**Why:** Fuzzy matching has no "right" threshold. Deferring to the reasoner (LLM) is cheaper and more reliable than making a binary choice at a hardcoded cutoff.

### 4. Injection Flagging, Not Blocking
If the memo says "pre-approved by the CFO", that's routed to a human with an injection flag, not silently flattened. The human sees what was attempted.

**Why:** Transparency. If an attacker tries social engineering via the API, the audit trail shows the attempt. Silent blocking hides the attack.

### 5. Separate Agent-to-Agent and Bank Paths, Same Rules
Whether the destination is a bank account or another agent's wallet, the adjudication pipeline is identical. Only the execution step differs.

**Why:** Consistency. A $4,000 payment is a $4,000 payment, regardless of destination. Keeping the rules identical prevents bypass vulnerabilities.

### 6. Deterministic, Reproducible Seed Data
The seed data (--seed 42) is frozen once finalized. This ensures the demo is reproducible and the system stability is verified across runs.

**Why:** Reproducibility. The demo must run identically every time, which proves the system is stable and consistent.

---

## Demo Scenario: The Block

From the seed data, there are two transactions that test duplicate detection at its most important moment:

| Date | Vendor | Amount | Status |
|---|---|---|---|
| 2026-07-02 | ACME Cloud Services LLC | $4,080 | executed |
| 2026-07-13 | Accme Cloud Svcs | $4,200 | **BLOCKED** |

The second request is:
- **R3:** Vendor confidence 0.77 (ambiguous band) → DEFER
- **R4:** Matches prior recurring txn, 2.9% amount difference → DEFER
- **Reasoner:** LLM confirms it's the same vendor with a misspelling
- **Outcome:** ROUTE_TO_HUMAN with cited evidence ID linking to the prior transaction

The human approver sees the cited evidence in `/ui/decisions/{id}`, compares the two payments, and either approves the correction or blocks a duplicate.

---

## What Orbis Does & Doesn't Do

| Orbis Does | Orbis Never Does |
|---|---|
| Flag spending against warrants | Approve on its own (rules decide) |
| Detect duplicate and velocity anomalies | Recommend amounts or vendors |
| Surface ambiguous vendor matches to a human | Contact agents or approve budgets |
| Create an immutable audit trail | Make decisions without evidence |
| Route high-risk requests for approval | Bypass the warrant system |
| Enforce budget ceilings deterministically | Accept live Stripe keys (safety check) |

**The human always decides. Orbis only enforces policy.**

---

## Future Scope

### Real-Time Warrant Updates
Currently warrants are static at request time. A future release could watch for warrant expiry and auto-close open decisions.

### Machine Learning Risk Scoring
Layer 2 could replace the weighted formula with a model trained on real approval/denial outcomes, improving vendor and agent risk profiles.

### Multi-Currency Support
Extend schema to support currency conversion and FX rate caching for agent-to-agent settlements across borders.

### Approval Chains
Some decisions may require multiple approvers (e.g., CFO + Board for >$100k). Extend the approval model to support sequential or parallel chains.

### Policy-as-Code
Move warrant definitions from the database to version-controlled DSL (e.g., Rego or Cedar) for audit and rollback.

### Integration with External Fraud Services
Plug in third-party vendor verification APIs (e.g., vendor registry lookups) to enrich the counterparty check.

---

## Stopping the Server

```bash
# Kill the background server
pkill -f "uvicorn fallback.main"

# Or from the terminal where it's running
Ctrl+C
```

Deactivate the virtual environment:

```bash
deactivate
```

---

## Contributing

1. Review the Five Invariants and Key Engineering Decisions sections
2. Follow the five invariants (enforce them in code, not just comments)
3. Add tests for new rules or extraction logic
4. Run `pytest tests/ -v` before committing
5. Do not regenerate seed data once finalized (--seed 42 is frozen)

---

## Team

Orbis is built and maintained by a core engineering team focused on deterministic authorization and financial controls for autonomous systems.

| Role | Responsibility |
|---|---|
| **Neshan Rochwani** | Architecture, rules engine, reasoner, execution |
| **Sahil** | Rules validation, testing, integration |

Contributing teams welcome. Please ensure all PRs include tests and maintain the five invariants.

---

## License

Internal use only.

---

<sub>Python | FastAPI | SQLite | Stripe | Pydantic | RapidFuzz | Anthropic</sub>

</div>
