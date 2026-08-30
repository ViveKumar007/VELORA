# Velora — Repository Analysis

> **Define the boundary. Let AI do the rest.**
>
> Velora is a trust, authorization and audit layer for agentic commerce. An AI agent decides
> *what* to buy; Velora independently and deterministically decides *whether it is allowed to*.

This document is a structural analysis of the repository as it stands: what each part does, how
the pieces fit, which invariants the code enforces, and where the loose ends are. For how to run
it, see [runinst.md](runinst.md).

---

## 1. At a glance

| | |
|---|---|
| **Backend** | Python 3.11+ / FastAPI 0.115 / SQLAlchemy 2.0 / PostgreSQL (psycopg 3) |
| **Frontend** | React 19 / Vite 8 / Tailwind CSS 4 / react-router 7 |
| **Database** | PostgreSQL — required (JSONB, `SELECT … FOR UPDATE`, unique indexes) |
| **Payments** | Pluggable provider: in-process `stub` (default) or Razorpay |
| **Live updates** | Server-Sent Events, in-process bus |
| **Tests** | 117 tests across 7 files (unit tests run anywhere; DB tests auto-skip) |
| **Auth** | Three distinct caller kinds: agents, buyers, merchants |
| **Money** | Integer **paise** everywhere; rupees exist only at the API edge |
| **Schema mgmt** | `Base.metadata.create_all` (Alembic is a dependency but unused) |

---

## 2. Repository layout

```
VELORA/
├── README.md                    product-facing narrative
├── OVERVIEW.md                  this file
├── runinst.md                   run / setup instructions
├── LICENSE
├── backend/
│   ├── .env.example             config template (secrets excluded from git)
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── demo.py                  scripted end-to-end walkthrough over real HTTP
│   ├── qa_verify.py             independent verification harness (EXPECTED vs ACTUAL)
│   ├── app/
│   │   ├── main.py              FastAPI app, router wiring, /api/health, /api/config
│   │   ├── config.py            pydantic-settings Settings, .env loading
│   │   ├── db.py                engine + SessionLocal + get_db
│   │   ├── auth.py              password hashing + signed session tokens (stdlib only)
│   │   ├── security.py          agent bearer tokens (SHA-256 hashed at rest)
│   │   ├── seed.py              schema + demo world; prints agent tokens once
│   │   ├── catalog_seed.py      5 merchants, 14 products (the demo storefront)
│   │   ├── models/              base.py · core.py (8 tables) · enums.py
│   │   ├── schemas/api.py       every Pydantic request/response shape
│   │   ├── gate/                THE AUTHORIZATION ENGINE — pure, deterministic, no I/O
│   │   │   ├── context.py         EvalContext, CheckResult, Verdict, normalisers
│   │   │   ├── checks.py          13 rules, one function each
│   │   │   ├── engine.py          runs all of them, derives the verdict
│   │   │   └── reasons.py         the reason-code contract
│   │   ├── services/
│   │   │   ├── gateway.py         the request path: one txn, one lock, one decision
│   │   │   ├── budget.py          reserve → settle → release
│   │   │   ├── approvals.py       human approve / reject / expire
│   │   │   ├── payments_flow.py   the ONLY code that may create a payment
│   │   │   ├── state_machine.py   the lifecycle, and the core invariant
│   │   │   ├── audit.py           append-only, hash-chained
│   │   │   ├── events.py          in-process SSE bus
│   │   │   └── payments/          base.py · stub.py · razorpay_provider.py
│   │   ├── agent/               the shopping agent (proposes; never decides)
│   │   │   ├── intent.py          rules-based NL → structured intent
│   │   │   ├── scoring.py         explainable weighted ranking
│   │   │   ├── shopper.py         search → rank → pick one
│   │   │   └── recovery.py        turns a refusal into an in-policy offer
│   │   ├── api/
│   │   │   ├── deps.py            require_agent · current_user · current_merchant
│   │   │   └── routes/            auth · catalog · merchants · agents · policies ·
│   │   │                          gate · transactions · approvals · webhooks · dashboard
│   │   └── utils/money.py       paise ↔ rupees, format_inr
│   └── tests/                   conftest + 7 test modules (117 tests)
└── frontend/
    ├── vite.config.js           dev proxy /api → 127.0.0.1:8000 (never "localhost")
    └── src/
        ├── App.jsx              routing + BuyerShell / MerchantShell + route guards
        ├── index.css            Tailwind 4 theme (design tokens, dark UI)
        ├── lib/                 api.js · session.js · razorpay.js · format.js
        ├── hooks/useLive.js     SSE subscription + live resource + tick
        ├── components/          ui.jsx · Decision · AuthFlow · AuthorityFlow ·
        │                        ActivityStream · Logo
        └── pages/               Landing · Login · MerchantLogin · Dashboard · Agents ·
                                 AgentConsole · Policies · Approvals · Transactions ·
                                 AuditTrail · MerchantConsole · DemoMode
```

---

## 3. The core idea, in code

```
USER ──defines policy──▶ VELORA ◀──asks permission── AI AGENT
                            │
                    deterministic gate (13 checks)
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
    APPROVED         PENDING_APPROVAL        BLOCKED
        │                   │                   │
        │              human decides            ✕ no payment, ever
        └─────────┬─────────┘
                  ▼
          PAYMENT PROVIDER  ──▶  HASH-CHAINED AUDIT TRAIL
```

Two rules the code **enforces** rather than merely documents:

1. **The agent never touches the payment provider.** Exactly one module
   ([payments_flow.py](backend/app/services/payments_flow.py)) can create a payment, and it
   re-verifies authorization against the database under a row lock before doing so.
2. **A `BLOCKED` transaction can never become `PAYMENT_SUCCESS`.** `BLOCKED`, `REJECTED` and
   `EXPIRED` have zero outgoing edges in
   [state_machine.py](backend/app/services/state_machine.py), and a test walks the transition
   graph to prove no path exists.

**No language model participates in an authorization decision.** A model may propose a purchase
and may narrate a decision afterwards, but the gate is a pure function — same input, same verdict,
every time. Even the intent parser in [intent.py](backend/app/agent/intent.py) is deliberately
rules-based rather than a model call, so demos are reproducible.

---

## 4. Domain model

Eight tables in [models/core.py](backend/app/models/core.py). Every monetary column is a
`BigInteger` count of **paise**.

| Table | Purpose | Notable columns |
|---|---|---|
| `users` | The buyer who draws the boundary | `email` (unique), `password_hash` |
| `agents` | An autonomous actor | `token_hash` (SHA-256, unique), `status` |
| `merchants` | A seller that publishes an agent-readable catalog | `slug` (canonical match key), `email`, `password_hash`, `razorpay_account_id`, `agent_ready` |
| `products` | **Velora's own catalog** — the price authority | `price_paise`, `category`, `merchant` (denormalised string), `attributes` JSONB |
| `authorization_policies` | The boundary around one agent | `max_per_transaction_paise`, `total_budget_paise`, `approval_threshold_paise`, `allowed_categories/merchants`, `transactions_used`, `amount_reserved_paise`, `amount_settled_paise` |
| `transaction_requests` | One purchase attempt + the full record of how it was judged | `state`, `decision`, `reason_code`, `checks` JSONB, `policy_snapshot` JSONB, `recovery` JSONB, `idempotency_key`, `request_fingerprint` |
| `approval_requests` | A human decision point | `decision`, `expires_at`, `prompt` |
| `audit_logs` | Append-only, hash-chained history | `seq`, `prev_hash`, `entry_hash`, `event_metadata` |

### Design decisions worth knowing

- **Two amount limits, not one.** `max_per_transaction_paise` caps any single purchase;
  `total_budget_paise` caps the sum. A single `max_amount` is ambiguous the moment more than
  one transaction is allowed.
- **Policies are snapshotted at evaluation** (`policy_snapshot`). Raise a limit after a block and
  the audit trail still shows the limit that actually applied.
- **`decision` is never rewritten.** After a human approves an escalated purchase, `state` becomes
  `APPROVED` while `decision` stays `PENDING_APPROVAL` — the trail permanently records that a
  *human* approved it rather than the gate auto-approving.
- **The catalog is the price authority.** The agent sends only `product_id` + `idempotency_key`.
  Price, category and merchant are read server-side, so there is no field in which an agent could
  misdeclare a purchase to slip past a rule.
- **Unique constraints do real work:** `uq_txn_agent_idempotency` arbitrates duplicate requests;
  `uq_audit_txn_seq` keeps the hash chain hole-free.

---

## 5. The gate — [backend/app/gate/](backend/app/gate/)

`evaluate(ctx) -> Verdict` is a pure function: context in, verdict out. No I/O, no writes,
no model calls. It runs **all** thirteen checks — never stopping at the first failure, because
the decision object has to show the whole checklist.

### The 13 checks, in order

```
 1. Authorization Exists       → NO_AUTHORIZATION
 2. Agent Status               → AGENT_SUSPENDED
 3. Agent Identity             → AGENT_IDENTITY_MISMATCH
 4. Authorization Active       → AUTHORIZATION_INACTIVE
 5. Validity Window            → AUTHORIZATION_EXPIRED / NOT_YET_VALID
 6. Product Resolved           → PRODUCT_NOT_FOUND / OUT_OF_STOCK
 7. Transaction Quota          → MAX_TRANSACTIONS_EXCEEDED / ALREADY_USED
 8. Merchant                   → MERCHANT_NOT_ALLOWED
 9. Category                   → CATEGORY_NOT_ALLOWED
10. Currency                   → CURRENCY_MISMATCH
11. Per-Transaction Limit      → MAX_AMOUNT_EXCEEDED
12. Remaining Budget           → BUDGET_EXCEEDED
13. Approval Threshold         → APPROVAL_THRESHOLD_EXCEEDED   ← the only REVIEW
```

Adding a rule means writing a function and appending it to `CHECKS`. Nothing else changes.

### Verdict precedence

| Any check returns | Decision |
|---|---|
| `FAIL` | `BLOCKED` — no payment may ever be created |
| `REVIEW` | `PENDING_APPROVAL` — a human decides |
| otherwise | `APPROVED` |

Only check 13 can return `REVIEW`. Everything above it is a hard yes or no. `SKIP` results (used
when there is no policy to evaluate against) appear in the checklist but are excluded from the
audit stream.

A subtlety worth preserving: check 4 deliberately **passes** an `EXHAUSTED` policy so check 7 can
say precisely *why* — a spent single-use authorization (`AUTHORIZATION_ALREADY_USED`) is a
different fact from a 5-transaction budget that ran out (`MAX_TRANSACTIONS_EXCEEDED`).

---

## 6. The request path — [gateway.py](backend/app/services/gateway.py)

`handle_purchase_request()` does everything inside **one** database transaction:

1. **Idempotency, fast path** — look up `(agent_id, idempotency_key)`; replay if found.
   A key reused with a *different* payload raises `IdempotencyConflict` rather than lying.
2. **Insert under a savepoint** — two identical requests can both miss the fast path; the
   unique index settles it, and the loser replays the winner.
3. **Lock the policy row `FOR UPDATE`** — held across evaluation *and* reservation, so
   concurrent requests cannot both pass the same quota check.
4. **Snapshot the policy**, move to `EVALUATING`, run the gate.
5. **Apply the decision:**
   - `BLOCKED` → look for a recovery offer, record it, terminate.
   - `APPROVED` / `PENDING_APPROVAL` → **reserve budget first**, then move state. Reserving at
     decision time (not payment time) is what stops an agent from outrunning its own budget.
6. **Commit** — decision, accounting and audit entries land atomically or not at all.

Lock ordering is consistently **transaction → policy**, which is why `audit.record()` taking the
transaction row lock cannot deadlock against `budget.lock_policy()`.

---

## 7. State machine — [state_machine.py](backend/app/services/state_machine.py)

```
CREATED ─▶ EVALUATING ─┬─▶ BLOCKED            (terminal)
                       ├─▶ PENDING_APPROVAL ─┬─▶ APPROVED
                       │                     ├─▶ REJECTED   (terminal)
                       │                     └─▶ EXPIRED    (terminal)
                       └─▶ APPROVED ─┬─▶ PAYMENT_CREATED ─┬─▶ PAYMENT_SUCCESS (terminal)
                                     │                    └─▶ PAYMENT_FAILED  (terminal)
                                     └─▶ PAYMENT_CREATION_FAILED ─▶ PAYMENT_CREATED
```

- `PAYABLE_STATES = {APPROVED, PAYMENT_CREATION_FAILED}` — an **allowlist**, so it fails closed.
- `PAYMENT_CREATION_FAILED` is deliberately *not* terminal: a provider outage is retryable and
  authorization already passed, so it is not re-litigated.
- `move_state()` in the gateway is the only sanctioned way to change state; it asserts the
  transition, writes the audit entry, and records old → new in one place.

---

## 8. Budget accounting — [budget.py](backend/app/services/budget.py)

```
available ──▶ reserved    when the gate approves or escalates
reserved  ──▶ settled     when a payment actually succeeds
reserved  ──▶ available   when rejected, expired, or the payment fails
```

`committed_paise = settled + reserved`, and `remaining_budget_paise = max(0, total - committed)`.
Every mutation happens while holding a `FOR UPDATE` lock on the policy row.

`active_policy_for_agent()` prefers a live `ACTIVE` policy, but deliberately falls back to the
agent's most recent policy of *any* status so the checks can name the real problem instead of
collapsing everything into a vague `NO_AUTHORIZATION`.

---

## 9. Audit trail — [audit.py](backend/app/services/audit.py)

Append-only. Nothing in the module ever updates or deletes a row.

Each entry hashes its own contents **together with the hash of the previous entry for the same
transaction**: `sha256(prev_hash + "|" + canonical_json(payload))`. Editing any historical row
invalidates every hash after it, and `verify_chain()` recomputes the whole chain so a reviewer can
check the claim rather than take it on faith. `GET /api/transactions/{id}/audit` returns the trail
plus an integrity block.

Appends serialise on the transaction row lock, because `seq` and `prev_hash` are both
read-then-write — without it, two concurrent appends compute the same `seq` and one dies on
`uq_audit_txn_seq`, leaving a hole in the chain.

Event types recorded: `REQUEST_RECEIVED`, `EVALUATION_STARTED`, `CHECK_EVALUATED`,
`DECISION_MADE`, `RECOVERY_OFFERED`, `DUPLICATE_SUPPRESSED`, `BUDGET_RESERVED`,
`BUDGET_RELEASED`, `HUMAN_APPROVED`, `HUMAN_REJECTED`, `APPROVAL_EXPIRED`, `PAYMENT_CREATED`,
`PAYMENT_CREATION_FAILED`, `PAYMENT_SUCCEEDED`, `PAYMENT_FAILED`, `STATE_CHANGED`.

---

## 10. The agent — [backend/app/agent/](backend/app/agent/)

The agent reads a goal, searches the catalog, ranks what it finds, picks one item — and stops.
It cannot pay, cannot see the policy, and cannot learn whether it is allowed to buy what it chose
except by asking Velora and being told. That blindness is intentional: an agent that could read
the policy would be tempted to route around it.

| Module | Role |
|---|---|
| [intent.py](backend/app/agent/intent.py) | Rules-based NL parse: category hints, preference hints, budget regexes (`under 2000`, `₹1.5k`). Documented as the seam where a model-backed parser could drop in without changing anything downstream. |
| [scoring.py](backend/app/agent/scoring.py) | Weighted sum with **reported components**, so the console can show *why* an item won. Base weights: budget 0.35, rating 0.30, category 0.15. Optional dimensions (battery life, stated preferences) apply only when asked for, then everything renormalises to 1. Scoring never considers policy limits. |
| [shopper.py](backend/app/agent/shopper.py) | Narrow by category → rank → choose → build a rationale. Falls back to the whole catalog rather than returning nothing. |
| [recovery.py](backend/app/agent/recovery.py) | **Turns refusals into sales.** On a block for `MAX_AMOUNT_EXCEEDED`, `BUDGET_EXCEEDED` or `MERCHANT_NOT_ALLOWED`, finds the best same-category alternative and **runs it through the real gate** before offering it. `CATEGORY_NOT_ALLOWED` is deliberately excluded — the user said they don't want that kind of thing, so offering more of it is nagging, not help. |

---

## 11. Payments — [backend/app/services/payments/](backend/app/services/payments/)

`get_provider()` (lru-cached) resolves `stub` or `razorpay` from settings.

| Provider | Behaviour |
|---|---|
| **stub** (default) | In-process. No network, no keys, no public webhook URL. Accepts `force_failure` in notes so `PAYMENT_CREATION_FAILED` can be demonstrated deliberately instead of waiting for an outage. |
| **razorpay** | Real orders. `enabled_methods()` queries the account's live method list and degrades to "show everything" on failure, never to "show nothing". |

### Three settlement paths, one implementation

1. `POST /api/webhooks/payment` — provider callback. HMAC-SHA256 verified over the **raw** body
   (re-serialising parsed JSON would change the bytes and break the HMAC). **In stub mode this
   endpoint returns 404 on purpose**: the stub's signing secret ships in the source tree, so a
   valid signature would prove nothing.
2. `POST /api/webhooks/simulate` — authenticated demo path for stub mode.
3. `POST /api/transactions/{id}/payment/confirm` — browser Checkout result. Untrusted input:
   verified with HMAC over `order_id|payment_id`, then **converted into exactly the webhook event
   shape and handed to `handle_webhook_event`**, so duplicate-suppression, out-of-order handling
   and budget settlement cannot drift between the two routes.

`handle_webhook_event` is written to survive the two things webhooks always do: arrive twice
(duplicate suppressed and audited) and arrive out of order (recorded, no state change applied).

---

## 12. Authentication — three kinds of caller

| Caller | Mechanism | Resolver |
|---|---|---|
| **Agent** | Long-lived bearer token, only its SHA-256 stored. Shown once at creation. | `require_agent` |
| **Buyer** | email + password → signed session token (`vs_<b64>.<hmac>`), 12h | `current_user` |
| **Merchant** | email + password → signed session token, different **audience** | `current_merchant` |

[auth.py](backend/app/auth.py) is entirely stdlib — PBKDF2-HMAC-SHA256 at 200,000 rounds with a
per-password salt, stored algorithm-tagged so parameters can be raised later without invalidating
existing hashes; session tokens are HMAC-SHA256 over a compact JSON payload.

**Buyer and merchant sessions are never interchangeable.** `read_session(token, expect=…)` checks
the `kind` claim, so a merchant token presented to a buyer endpoint is refused. Two doors, not one
with a role flag — a buyer and a seller have opposed interests.

Notable security posture, all with the reasoning preserved in comments:

- **A suspended agent is not refused at the door.** It reaches the gate and is blocked with
  `AGENT_SUSPENDED` and a full audit trail, because a suspended agent trying to spend money is
  exactly the event a trust layer must capture.
- **`X-User-Id` is rejected outright**, not ignored, unless `DEV_ALLOW_USER_HEADER=true`. The
  header was previously trusted, which meant anyone who guessed a user id could read that user's
  policies and approve their purchases.
- **`OPERATOR_TOKEN`**, when set, gates the whole human-facing surface via `X-Velora-Token`, and
  the SSE stream via `?token=` (EventSource cannot set headers).
- Login returns **the same message and does the same work** whether the account is missing or the
  password is wrong, so it cannot be used to enumerate accounts.
- A failed payment-confirmation signature is recorded as a security event, not a user error.

---

## 13. API surface

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/health` | none | Liveness + active provider |
| `GET` | `/api/config` | none | Public runtime config (publishable Razorpay key, enabled methods) |
| `POST` | `/api/auth/login` | none | Buyer sign-in |
| `POST` | `/api/auth/merchant/login` | none | Merchant sign-in |
| `GET` | `/api/auth/me` · `/api/auth/merchant/me` | session | Whoami |
| `GET` | `/api/products` · `/api/products/{id}` | none | Catalog |
| `GET` | `/api/merchants` · `/api/merchants/{slug}` | none | Merchant directory |
| `GET` | `/api/merchants/catalog` | none | **Agent-readable catalog + purchase protocol** |
| `GET` | `/api/merchants/me` | merchant | Merchant console stats |
| `POST` | `/api/agents` | user | Register an agent (returns its token once) |
| `GET` | `/api/agents` | user | List agents |
| `POST` | `/api/agents/{id}/suspend` | user | Suspend |
| `POST` | `/api/policies` | user | Create an authorization |
| `GET` | `/api/policies` · `/{id}` | user | Read |
| `POST` | `/api/policies/{id}/revoke` | user | Withdraw authority immediately |
| `POST` | `/api/agent/request` | **agent** | **The gate.** Agent asks permission |
| `POST` | `/api/agent/run` | **agent** | Plain-language goal, end to end |
| `GET` | `/api/approvals` | user | Pending human decisions |
| `POST` | `/api/transactions/{id}/approve` · `/reject` | user | Decide |
| `GET` | `/api/transactions` · `/{id}` | user | List / read |
| `GET` | `/api/transactions/{id}/audit` | user | Full trail + integrity check |
| `POST` | `/api/transactions/{id}/payment` | user | Create a payment — approved only |
| `POST` | `/api/transactions/{id}/payment/confirm` | user | Settle a browser checkout result |
| `POST` | `/api/webhooks/payment` | signature | Provider callback (404 in stub mode) |
| `POST` | `/api/webhooks/simulate` | user | Stub-mode settlement for demos |
| `GET` | `/api/dashboard` | user | Aggregate stats |
| `GET` | `/api/events` | operator token | SSE stream for live UI updates |

### The agent-readable catalog

`GET /api/merchants/catalog` is a nice piece of design: one document an autonomous buyer can fetch
to learn what is for sale *and exactly how to buy it* — prices in integer paise so no client has
to guess a unit, plus a `purchase_protocol` block naming the endpoint, the auth header, the
two-field request body, the three possible decisions, and what to do with a `recovery` offer.

---

## 14. Frontend — [frontend/src/](frontend/src/)

Two shells behind route guards in [App.jsx](frontend/src/App.jsx):

- **`BuyerShell`** (`/app/*`) — sidebar command centre with a live-connection dot and a pending-
  approvals badge. Pages: Overview, Agents, Agent Console, Authorization, Approvals,
  Transactions, Audit Trail, plus a full-screen Demo Mode.
- **`MerchantShell`** (`/merchant`) — deliberately a different colour and structure, so it is
  unmistakably the other side of the deal.

Public routes: `/` (Landing), `/login`, `/merchant/login`.

| Module | Role |
|---|---|
| [lib/api.js](frontend/src/lib/api.js) | Single `request()` with an `auth` selector: `'user'` \| `'merchant'` \| `'agent'` \| `'none'`. A 401 on a session call clears that session rather than leaving the UI retrying against a dead token. |
| [lib/session.js](frontend/src/lib/session.js) | Buyer and merchant sessions under separate `localStorage` keys, so both consoles can be open at once. Every access is try/catch-wrapped for private mode. |
| [lib/razorpay.js](frontend/src/lib/razorpay.js) | Lazily loads Checkout once. Card details stay inside Razorpay's hosted iframe — never our page, never our server (RBI card-on-file rules). |
| [hooks/useLive.js](frontend/src/hooks/useLive.js) | `useEventStream` (SSE), `useLiveResource` (fetch + refetch on event + slow poll fallback), `useTick` (countdowns without refetching). |

**The SSE stream is advisory by design.** A message only says *something changed*; the client
refetches. A dropped event can therefore never leave the UI asserting a decision the backend
disagrees with — worst case is a stale view the next event or poll corrects.

The Vite dev proxy points at `127.0.0.1:8000`, **never `localhost`** — on Windows, `localhost`
resolves to `::1` first, uvicorn binds IPv4 only, and every proxied call ate a ~2s
connection-refused retry (measured 2043ms vs 3ms). The same note appears in `demo.py` and
`qa_verify.py`.

---

## 15. Configuration reference

Read by [config.py](backend/app/config.py) from `backend/.env` (see
[.env.example](backend/.env.example)).

| Setting | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/velora` | Percent-encode special characters in the password (`*` → `%2A`, `@` → `%40`, `#` → `%23`) |
| `PAYMENT_PROVIDER` | `stub` | `stub` or `razorpay` |
| `RAZORPAY_KEY_ID` / `_KEY_SECRET` / `_WEBHOOK_SECRET` | empty | Only the key id is ever returned to the browser |
| `APPROVAL_TTL_MINUTES` | `15` | How long a `PENDING_APPROVAL` stays actionable |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated |
| `OPERATOR_TOKEN` | empty | Shared secret for the human-facing API. Empty is only acceptable bound to 127.0.0.1 |
| `SESSION_SECRET` | empty | Signing key for session tokens. Empty ⇒ random per-process key ⇒ **everyone is logged out on restart** |
| `DEV_ALLOW_USER_HEADER` | `false` | Allow `X-User-Id` impersonation. Local testing only |

Frontend build-time: `VITE_OPERATOR_TOKEN` (must match `OPERATOR_TOKEN` when that is set).

---

## 16. Tests — [backend/tests/](backend/tests/)

**117 tests** across seven modules. Unit tests run anywhere; integration tests skip automatically
when no database is reachable at `TEST_DATABASE_URL`.

| File | Tests | Covers |
|---|---|---|
| `test_flows.py` | 27 | End-to-end request → decision → approval → payment paths |
| `test_gate.py` | 23 | All 13 checks and verdict precedence |
| `test_auth.py` | 21 | Password hashing, session tokens, audience separation |
| `test_security.py` | 17 | Identity, impersonation, webhook signatures, operator token |
| `test_agent.py` | 11 | Intent parsing, scoring, selection |
| `test_state_machine.py` | 10 | The lifecycle graph and its invariant |
| `test_recovery.py` | 8 | In-policy alternatives on a block |

A fixture in [conftest.py](backend/tests/conftest.py) is autouse and **unconditionally forces the
stub provider** — the suite previously inherited `PAYMENT_PROVIDER` from `.env` and started
calling Razorpay's live API as a side effect of running tests.

Ones worth reading:

- `test_blocked_can_never_reach_payment_success` — graph traversal over the state machine.
- `test_concurrent_requests_cannot_both_consume_a_one_time_authorization` — two threads race a
  single-use policy; results must be exactly `["APPROVED", "BLOCKED"]`.
- `test_tampering_with_the_audit_trail_is_detected` — edits a historical entry, confirms the chain
  catches it.
- `test_policy_snapshot_survives_a_later_policy_edit`.
- `test_reservations_count_against_budget`.

Beyond pytest there are two live harnesses: `demo.py` (a scripted narrative walkthrough, self-
seeding and re-runnable) and `qa_verify.py` (independent EXPECTED-vs-ACTUAL verification, each
scenario getting its own agent and policy so none can contaminate another).

---

## 17. Observations and loose ends

### Documentation drift

- `README.md` claims **81 tests** in one place and **97** in another; the suite currently holds
  **117**.
- The README's "demo in five clicks" predates the login layer — both consoles now sit behind
  `/login` and `/merchant/login`. Credentials are printed by the seed
  (`demo@velora.local` / `velora123`, `<slug>@velora.local` / `merchant123`).
- `SESSION_SECRET` exists in `config.py` but is **missing from `.env.example`**, so a fresh setup
  silently gets ephemeral sessions that die on every backend restart.
- In `Settings`, the docstring comment describing `operator_token` sits above `session_secret` —
  the two comment blocks have drifted apart from the fields they describe.

### Configuration state on this machine

`backend/.env` currently has `PAYMENT_PROVIDER=razorpay` with real key values but an **empty
`RAZORPAY_WEBHOOK_SECRET`**. `verify_webhook` fails closed on an empty secret, so the public
webhook endpoint will reject every callback — settlement has to come through
`/payment/confirm` (browser Checkout, signature-verified) until a webhook secret is set. The file
is correctly covered by `backend/.gitignore` and is not in git.

### Deliberately scoped out (per the README)

- **No schema migrations** — `create_all` rather than Alembic, though Alembic is already a
  declared dependency.
- **No rate limiting** — agent tokens are long enough that brute force is impractical, but a
  reverse proxy or slowapi should front this before exposure.
- **The event bus is per-process**, so live updates assume a single backend instance.
- **Approval expiry is lazy.** `models/core.py` refers to a sweeper in `services/expiry.py`, but
  that module does not exist — expiry is enforced on read only. A pending approval on a quiet
  system therefore stays `PENDING_APPROVAL` in the database until something looks at it.

### Working-tree state

The branch is `main` with a large body of uncommitted work: the entire auth layer
(`app/auth.py`, `routes/auth.py`, `tests/test_auth.py`), merchants (`routes/merchants.py`,
`catalog_seed.py`), recovery (`agent/recovery.py`, `tests/test_recovery.py`), and eleven new
frontend files including the Landing, Login, MerchantConsole and DemoMode pages. Roughly 28
tracked files are also modified. None of this is committed yet.

---

## 18. What is genuinely strong here

- **The authorization core is production-shaped**: deterministic, concurrency-safe, idempotent,
  fully audited — and each of those properties has a test that would fail if it regressed.
- **Failure modes are engineered, not hoped for.** Forced provider failures, duplicate webhooks,
  out-of-order webhooks, idempotency-key reuse with a different payload, races on a single-use
  policy — each has an explicit, audited branch.
- **The comments explain *why*, not *what*.** Nearly every non-obvious decision carries the
  reasoning and, frequently, the bug that motivated it. That is unusually maintainable.
- **Refusal is designed as a product surface.** The recovery path treats a block as the start of a
  negotiation rather than a dead end — and validates every offer through the real gate first, so
  the guardrail never teaches the buyer that its refusals are noise.
