# Sandboxes

One folder per Daytona sandbox. Each holds the small script that runs *inside* that sandbox — not part of the Orbis service, which is built in Forge and lives in `orbis-dev`.

Every agent script does one thing: `POST /spend-requests` to the Orbis API with `destination_type`, counterparty, category, amount, business purpose. No Stripe key, no database access, no secrets, no egress except the Orbis API — verify that from inside each sandbox before the demo (curl something else, watch it fail).

| Folder | Sandbox | Behavior |
|---|---|---|
| `agent-ops/` | `agent-ops` | Well-behaved procurement agent — submits clean requests, and later pays `agent-vendor` for A2A |
| `agent-vendor/` | `agent-vendor` | Payee agent — does work, returns a result + invoice, holds a wallet id, no more authority than the others |
| `agent-runaway/` | `agent-runaway` | Bursts 9 requests in 6 minutes — fires R5 live |
| `agent-hostile/` | `agent-hostile` | Submits an invoice with injection text in the memo — extractor must flatten it with zero effect on the decision |

Build order: A2 (spin sandboxes, verify no egress) → B8 (wire `agent-ops` to the live API) → D3 (`agent-vendor` + A2A) → D4 (`agent-runaway` fires R5 live). See `STATUS.md`.
