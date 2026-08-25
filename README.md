# Velora

**Define the boundary. Let AI do the rest.**

Velora is a trust, authorization, and audit layer for agentic commerce. AI agents decide *what*
to buy; Velora independently decides *whether they are allowed to*.

> We don't give AI agents access to money. We give them limited authority.

---

## The idea

An autonomous agent that can spend money is only as safe as the boundary around it. Velora is
that boundary. It sits between the agent and the payment provider, and every purchase request
passes through it.

```
USER ──defines policy──▶ VELORA ◀──asks permission── AI AGENT
                            │
                    deterministic gate
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
    APPROVED         PENDING_APPROVAL        BLOCKED
        │                   │                   │
        │              user decides             ✕ no payment, ever
        │                   │
        └─────────┬─────────┘
                  ▼
          PAYMENT PROVIDER  ──▶  AUDIT TRAIL
```

Two rules the code enforces rather than merely documents:

1. **The agent never touches the payment provider.** One function can create a payment, and it
   re-verifies authorization against the database under a row lock before doing so.
2. **A BLOCKED transaction can never become PAYMENT_SUCCESS.** `BLOCKED`, `REJECTED` and
   `EXPIRED` have zero outgoing edges in the state machine, and a test walks the transition
   graph to prove no path exists.

No language model participates in an authorization decision. A model may propose a purchase and
may narrate a decision afterwards, but the gate itself is a pure function — same input, same
verdict, every time.

---

## Quick start

**Requires:** Python 3.11+, Node 18+, PostgreSQL 14+ running locally.

### 1. Database

```bash
createdb velora        # or: psql -U postgres -c "CREATE DATABASE velora"
```

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS/Linux

cp .env.example .env        # then set DATABASE_URL to your Postgres credentials
python -m app.seed --reset  # creates the schema + demo world, prints an agent token
python -m uvicorn app.main:app --port 8000
```

The seed prints an **agent token** exactly once. Copy it — the Agent Console needs it.

> If your password contains URL-special characters, percent-encode them in `DATABASE_URL`
> (`*` → `%2A`, `@` → `%40`, `#` → `%23`).

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. API docs are at http://localhost:8000/docs.

### 4. See it work

Either drive the UI, or run the scripted walkthrough:

```bash
cd backend
python demo.py      # self-seeding and re-runnable
```

It exercises all four decision paths, the human approval flow, the payment leg, idempotency,
and the audit trail — over real HTTP against a real database.

---

## The demo, in five clicks

1. **Agent Console** — paste your agent token, then run
   *"Buy me wireless headphones under 2000 with good battery life"*.
   The agent parses the goal, scores the catalog, and picks **SoundBeat Pro (₹1,799)**.
2. Velora returns **PENDING_APPROVAL** — inside the ₹2,000 limit, above the ₹1,500
   auto-approval threshold — with all 13 checks shown.
3. **Approval Centre** — the purchase is waiting, with a live expiry countdown.
   Approve it.
4. **Transactions** — *Create payment*, then *Confirm payment*. State walks
   `APPROVED → PAYMENT_CREATED → PAYMENT_SUCCESS`.
5. **Audit trail** — every check, the budget reservation, your approval, and the payment, all
   hash-chained, with an integrity check that recomputes the chain.

Then try *"Buy me the best headphones you can find"*. The agent picks the ₹2,499 model and
Velora blocks it with `MAX_AMOUNT_EXCEEDED`. **The agent is allowed to want things it cannot
have — catching that is the entire point.**

---

## How the gate works

Every request runs **all** thirteen checks — never stopping at the first failure, because the
decision object has to show the whole checklist. The verdict follows by precedence:

| Any check | Decision |
|---|---|
| `FAIL` | `BLOCKED` — no payment may ever be created |
| `REVIEW` | `PENDING_APPROVAL` — a human decides |
| otherwise | `APPROVED` |

```
Authorization Exists → Agent Status → Agent Identity → Authorization Active →
Validity Window → Product Resolved → Transaction Quota → Merchant → Category →
Currency → Per-Transaction Limit → Remaining Budget → Approval Threshold
```

Only the last one can return `REVIEW`. Everything above it is a hard yes or no.

### What the agent is allowed to send

```json
{ "product_id": "prd_…", "idempotency_key": "…" }
```

That's all. Price, category and merchant are read from Velora's own catalog, so there is no
field in which an agent could misdeclare a purchase to slip past a rule. Identity comes from a
bearer token, not from the request body — an `agent_id` in the payload is only a claim, and a
mismatch is blocked.

---

## Design decisions worth knowing

**Two amount limits, not one.** `max_per_transaction` caps any single purchase;
`total_budget` caps the sum. A single `max_amount` is ambiguous the moment more than one
transaction is allowed.

**Budget is reserved at decision time, not payment time.** Fire five requests at a policy with
room for one and only the first reserves; the rest see the reservation and are blocked. Rejecting
or expiring a purchase returns both the money and the transaction slot.

**Money is integer paise everywhere.** Rupees exist only at the API edge. Floats cannot represent
currency exactly, and Razorpay counts in paise.

**Policies are snapshotted at evaluation.** Raise a limit after a block and the audit trail still
shows the limit that actually applied, so the record stays verifiable.

**`decision` is never rewritten.** After you approve an escalated purchase its `state` becomes
`APPROVED` while `decision` stays `PENDING_APPROVAL` — the trail permanently records that a human
approved it rather than the gate auto-approving it.

**The audit log is hash-chained.** Each entry hashes over its predecessor, so editing any past
entry breaks every hash after it. `GET /api/transactions/{id}/audit` returns an integrity block
that recomputes the chain.

---

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/policies` | Create an authorization |
| `GET` | `/api/policies` | List authorizations |
| `POST` | `/api/policies/{id}/revoke` | Withdraw authority immediately |
| `POST` | `/api/agents` | Register an agent (returns its token once) |
| `POST` | `/api/agent/request` | **The gate.** Agent asks permission |
| `POST` | `/api/agent/run` | Agent takes a plain-language goal end to end |
| `GET` | `/api/approvals` | Pending human decisions |
| `POST` | `/api/transactions/{id}/approve` | Approve |
| `POST` | `/api/transactions/{id}/reject` | Reject |
| `POST` | `/api/transactions/{id}/payment` | Create a payment — approved only |
| `GET` | `/api/transactions/{id}/audit` | Full trail + integrity check |
| `POST` | `/api/webhooks/payment` | Provider callback (HMAC verified) |
| `GET` | `/api/events` | SSE stream for live UI updates |

---

## Payments

Ships with a **stub provider** so the whole flow runs with no keys, no network and no public
webhook URL. It also lets a failure be triggered deliberately (*Fail it* in the Transactions
table), which is how `PAYMENT_CREATION_FAILED` gets demonstrated on purpose rather than by
waiting for an outage.

To use Razorpay test mode:

```bash
PAYMENT_PROVIDER=razorpay
RAZORPAY_KEY_ID=rzp_test_…
RAZORPAY_KEY_SECRET=…
RAZORPAY_WEBHOOK_SECRET=…
```

Razorpay cannot reach `localhost`, so webhooks need a tunnel (ngrok/cloudflared) pointed at
`/api/webhooks/payment`. Signatures are verified with HMAC-SHA256 over the raw request body, and
an unverifiable webhook is rejected — an unauthenticated endpoint that marks purchases paid would
hand that power to anyone.

---

## Tests

```bash
cd backend
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/velora_test \
  python -m pytest tests/ -q
```

**81 tests.** The unit tests need no database; the integration tests are skipped automatically
if none is reachable.

Ones worth reading:

- `test_blocked_can_never_reach_payment_success` — graph traversal over the state machine.
- `test_concurrent_requests_cannot_both_consume_a_one_time_authorization` — two threads race a
  single-use policy; results must be exactly `["APPROVED", "BLOCKED"]`.
- `test_tampering_with_the_audit_trail_is_detected` — edits a historical entry and confirms the
  hash chain catches it.
- `test_policy_snapshot_survives_a_later_policy_edit` — raises a limit after a block and confirms
  the record still shows what actually applied.
- `test_reservations_count_against_budget` — pending approvals cannot collectively exceed budget.

---

## Layout

```
backend/
  app/
    gate/          the authorization engine — pure, deterministic, no I/O
      checks.py      13 rules, one function each
      engine.py      runs all of them, derives the verdict
      reasons.py     the reason-code contract
    services/
      gateway.py     the request path: one transaction, one lock, one decision
      budget.py      reserve → settle → release
      approvals.py   human decisions
      payments_flow.py  the only code that may create a payment
      state_machine.py  the lifecycle, and the invariant
      audit.py       append-only, hash-chained
    agent/         the shopping agent: intent, scoring, selection
    api/routes/    thin HTTP layer
  tests/
frontend/
  src/pages/       Dashboard · Authorizations · Agent Console · Approvals · Transactions · Audit
```

---

## Security

Run the backend bound to `127.0.0.1` (the default). Two settings matter beyond that:

```bash
OPERATOR_TOKEN=            # shared secret for approve / reject / pay / policies
DEV_ALLOW_USER_HEADER=false
```

- **`OPERATOR_TOKEN`** — when set, every human-facing route requires `X-Velora-Token`, and the
  SSE stream requires `?token=`. Leave it empty **only** for a localhost demo. The frontend
  sends it from `VITE_OPERATOR_TOKEN` at build time.
- **`DEV_ALLOW_USER_HEADER`** — when false (the default), `X-User-Id` is rejected outright.
  It previously selected any user, which meant anyone who guessed a user id could read that
  user's policies, approve their purchases and create payments for them. Enable it only for
  local multi-user testing.

Agents authenticate with a bearer token whose SHA-256 hash is all that is stored. A suspended
agent is not refused at the door — it reaches the gate and is blocked with `AGENT_SUSPENDED`
and a full audit trail, because a suspended agent trying to spend money is exactly the event
worth recording.

In stub mode the public `/api/webhooks/payment` endpoint is **closed**: the stub's signing
secret lives in this repo, so a valid signature would prove nothing. Use the authenticated
`/api/webhooks/simulate` for demos; the public endpoint opens only with a real provider.

## Status

Hackathon MVP. The authorization core is production-shaped: deterministic, concurrency-safe,
idempotent, fully audited. Verified by 97 tests plus a 130-check live harness
(`python qa_verify.py`).

Known gaps, deliberately scoped out:

- **No per-user sessions.** This is a single-operator deployment guarded by a shared token.
  Real multi-tenant auth means replacing one function, `current_user` in `api/deps.py`.
- **No rate limiting.** Agent tokens are 48 hex characters so brute force is impractical, but
  a reverse proxy or slowapi should front this before it is exposed.
- **Schema migrations** use `create_all` rather than Alembic.
- **The event bus is per-process**, so real-time updates assume a single backend instance.
