# STATUS — Orbis build tracker

SF Enterprise Hackathon, 14 Aug 2026, AWS Builder Loft · Window 9:40–5:30
**Checkpoint 1:30 · A2A hard stop 2:35 · Snapshot 2:45 · Hard freeze 3:15**
Build in **Forge** (SoftwareForge.ai), run and test in **Daytona**. Every step ships to Daytona before the next starts — don't batch prompts and test once.
Owners: **Sahil** · **Nesh**

**Legend:** `[ ]` not started · `[~]` in progress · `[x]` done, verified live in Daytona

> Superseded plan: this replaces the earlier T0–T14 / 3:45-freeze version of this file, written before the Forge+Daytona pivot.

---

## Before you start

- [ ] Forge account confirmed, access working
- [ ] Daytona account confirmed, a sandbox actually spun up
- [ ] Stripe test key in hand (`sk_test_` prefix)
- [ ] `architecture.md` pasted into Forge as context
- [ ] Recruit to four if possible at check-in — platform fluency is 30% of score, and stretch scope only comes into range at four

---

## 9:40–10:15 — Joint

- [ ] Confirm Forge access, spin up `orbis-dev` — **A1**
- [ ] Paste `architecture.md` into Forge as context

---

## Sahil — schema, rules→engine, execution, reasoner

| Time | Task | Build ID | Status |
|---|---|---|---|
| 10:15–11:30 | Forge: core types + schema (incl. `destination_type`); spend request API + warrant model; seed generator with all 7 violations | B1, B2, B3 | [ ] |
| 11:30–12:45 | Forge: adjudication orchestrator (stub extractor); approval queue + UI (submit, queue, decision detail) | B5, B6 | [ ] |
| 12:45–1:30 | Forge: Stripe test execution + ledger write-back | B7 | [ ] |
| 1:30–2:00 | Shadow report — must find exactly 7 findings, no more | C1 | [ ] |
| **1:30** | **CHECKPOINT** — end-to-end loop hosted and working, or cut all of the rows below | | [ ] |
| 2:00–2:35 | Reasoner + faithfulness validator — violation 1 blocks via DEFER path with cited evidence | D2 | [ ] |
| 2:35–2:45 | Decision detail view polished — every rule result and cited warrant clause renders, `destination_type` visible | D5 | [ ] |
| 2:45–3:15 | **Snapshot `orbis-dev`**; verify all 9 demo beats from the snapshot; fix + re-snapshot if anything fails | E1, E2 | [ ] |
| **3:15** | **Freeze. No more code.** | | [ ] |
| 3:15–5:00 | Five slides max, rehearse 3× timed | | [ ] |

## Nesh — rules R1–R6, Daytona agents, extractor, A2A

| Time | Task | Build ID | Status |
|---|---|---|---|
| 10:15–11:30 | Forge: rules R1–R6 + precedence | B4 | [ ] |
| 11:30–12:45 | Daytona: agent runtime script; spin `agent-ops`, wire it to the live API | A2 (part), B8 | [ ] |
| 12:45–1:30 | Daytona: spin `agent-runaway`, `agent-hostile` — verify no credentials, egress fails to anything but Orbis API | A2 (rest) | [ ] |
| **1:30** | **CHECKPOINT** — end-to-end loop hosted and working, or cut all of the rows below | | [ ] |
| 1:30–2:00 | Real extractor + injection flagging — `agent-hostile` request routes with flag set | D1 | [ ] |
| 2:00–2:35 | **`agent-vendor` sandbox + A2A settlement** — `agent-ops` pays `agent-vendor`, `destination_type=agent` visible in the decision; confirm `agent-runaway` triggers R5 live (freeze + hold pending) | D3, D4 | [ ] |
| **2:35** | **HARD STOP on A2A.** Not working? Kill it, demo without it. Do not let it push the snapshot. | | [ ] |
| 2:35–2:45 | Buffer | | [ ] |
| 2:45–3:15 | Record backup demo video from the verified snapshot | E3 | [ ] |
| **3:15** | **Freeze. No more code.** | | [ ] |
| 3:15–5:00 | Rehearse, run timer, play skeptical judge | | [ ] |

---

## Scope gates

- **P0 — no submission without it:** Daytona sandboxes running agents · spend request API · warrant model · rules R1–R6 · approval queue · Stripe test execution + write-back · seed data · shadow report · **hosted URL** · **verified snapshot**
- **P1 — only if P0 green at 1:30:** extractor + injection flagging · reasoner + faithfulness validator · **A2A settlement** · decision detail view
- **Stretch — only with 4 people, or P1 lands by 2:15:** `policy_leakage` + `duplicate_vendor` findings view · CSV bank-export connector
- **Roadmap slide only — do not build:** knowledge graph / audit-chain view, full advisory finder set, policy proposals, NL answer layer, real connectors, eval suite, other action surfaces

**Cut rules.** 1:30 not green → cut P1 entirely, P0 alone is a complete demo. A2A not working by 2:35 → kill it, don't let it touch the snapshot. Anything not working at 3:15 does not exist. Spare time → harden the shadow report and rehearse, never new features.

---

## Pre-freeze demo verification (run all 9 from the snapshot, 2:45–3:15)

1. [ ] Five Daytona sandboxes up; curl a non-Orbis URL from inside one, watch it fail
2. [ ] $200 API credits → auto-approves in ~2s
3. [ ] `agent-ops` pays `agent-vendor` → settles A2A in ~1s, inside a signed warrant
4. [ ] $4,200 `Accme Cloud Svcs` → BLOCK, shows $4,080 `ACME Cloud Services LLC` from 11 days earlier
5. [ ] `agent-runaway` bursts → R5 freezes it live, pending held
6. [ ] `agent-hostile` invoice "pre-approved by the CFO" → flattened, flagged, zero effect
7. [ ] $9,000 routes with cited warrant clause → approve live → payment executes, budget moves
8. [ ] Shadow report shows 7 violations, $23,400
9. [ ] Close line lands: "Stripe gave agents wallets. Orbis gives them approvals."

## Open items — resolve before or during the day, not on stage

- [ ] R2 budget bands (1.05 / 1.20) and R6 thresholds ($5,000 / $2,000) — invented, swap for a real approval matrix if anyone's seen one
- [ ] Ask at the mentor table: do RocketRide/Snyk sponsor prizes still apply alongside Forge/Daytona judging?
- [ ] Ask at the mentor table: does the day end at 5:30 or 7:00? (event page and organizer blast disagree)
- [ ] Confirm team size — plan is written for two; recruiting to four unlocks the stretch block
