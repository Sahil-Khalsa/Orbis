-- Orbis schema. Money columns are always INTEGER cents.
-- List-valued fields are stored as JSON text (SQLite has no array type).

CREATE TABLE IF NOT EXISTS principals (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    principal_id TEXT NOT NULL REFERENCES principals(id),
    runtime_id TEXT NOT NULL,          -- local process label, Daytona sandbox_id equivalent
    kind TEXT NOT NULL,                -- spender | payee
    wallet_id TEXT,
    status TEXT NOT NULL DEFAULT 'active'  -- active | frozen
);

CREATE TABLE IF NOT EXISTS warrants (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(id),
    principal_id TEXT NOT NULL REFERENCES principals(id),
    categories TEXT NOT NULL,          -- JSON list
    ceiling_per_txn_cents INTEGER NOT NULL,
    ceiling_total_cents INTEGER NOT NULL,
    spent_total_cents INTEGER NOT NULL DEFAULT 0,
    vendor_scope TEXT NOT NULL,        -- JSON list of vendor ids, or ["*"]
    counterparty_scope TEXT NOT NULL,  -- JSON list of agent ids, or ["*"]
    valid_from TEXT NOT NULL,          -- ISO date
    valid_until TEXT NOT NULL,         -- ISO date
    status TEXT NOT NULL DEFAULT 'active',
    clause_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vendors (
    id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',  -- JSON list
    status TEXT NOT NULL DEFAULT 'pending',  -- approved | pending | blocked
    first_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budgets (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    budgeted_cents INTEGER NOT NULL,
    committed_cents INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    destination_type TEXT NOT NULL,      -- bank | agent
    vendor_id TEXT REFERENCES vendors(id),
    counterparty_agent_id TEXT REFERENCES agents(id),
    category TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    occurred_at TEXT NOT NULL,           -- ISO datetime
    description TEXT NOT NULL DEFAULT '',
    recurring INTEGER NOT NULL DEFAULT 0,  -- 0/1
    stripe_ref TEXT,
    spend_request_id TEXT REFERENCES spend_requests(id)
);

CREATE TABLE IF NOT EXISTS spend_requests (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(id),
    warrant_id TEXT REFERENCES warrants(id),
    destination_type TEXT NOT NULL,      -- bank | agent
    vendor_name_raw TEXT,
    counterparty_agent_id TEXT REFERENCES agents(id),
    category TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    business_purpose_raw TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'submitted'
);

CREATE TABLE IF NOT EXISTS extractions (
    id TEXT PRIMARY KEY,
    spend_request_id TEXT NOT NULL REFERENCES spend_requests(id),
    vendor_name_norm TEXT NOT NULL,
    vendor_id_match TEXT REFERENCES vendors(id),
    match_confidence REAL NOT NULL DEFAULT 0,
    purpose_class TEXT NOT NULL,
    line_items TEXT NOT NULL DEFAULT '[]',    -- JSON list
    injection_flags TEXT NOT NULL DEFAULT '[]'  -- JSON list
);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    spend_request_id TEXT NOT NULL REFERENCES spend_requests(id),
    outcome TEXT NOT NULL,               -- AUTO_APPROVE | ROUTE_TO_HUMAN | BLOCK
    decided_at TEXT NOT NULL,
    decided_by TEXT NOT NULL,            -- engine | reasoner | human
    rationale TEXT NOT NULL,
    cited_rule_ids TEXT NOT NULL DEFAULT '[]',  -- JSON list
    cited_warrant_id TEXT REFERENCES warrants(id)
);

CREATE TABLE IF NOT EXISTS rule_results (
    id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES decisions(id),
    rule_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    detail TEXT NOT NULL,
    evidence_ids TEXT NOT NULL DEFAULT '[]'  -- JSON list
);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES decisions(id),
    principal_id TEXT NOT NULL REFERENCES principals(id),
    action TEXT NOT NULL,                -- approve | deny
    note TEXT NOT NULL DEFAULT '',
    acted_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transactions_vendor ON transactions(vendor_id);
CREATE INDEX IF NOT EXISTS idx_transactions_counterparty ON transactions(counterparty_agent_id);
CREATE INDEX IF NOT EXISTS idx_transactions_occurred_at ON transactions(occurred_at);
CREATE INDEX IF NOT EXISTS idx_spend_requests_agent ON spend_requests(agent_id);
CREATE INDEX IF NOT EXISTS idx_decisions_spend_request ON decisions(spend_request_id);
CREATE INDEX IF NOT EXISTS idx_rule_results_decision ON rule_results(decision_id);
