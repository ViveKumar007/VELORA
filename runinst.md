# Velora — Run Instructions

Everything needed to get Velora running locally, plus the commands for seeding, demoing,
testing and troubleshooting. For what the code actually does, see [OVERVIEW.md](OVERVIEW.md).

---

## 0. Prerequisites

| Requirement | Version | Check |
|---|---|---|
| Python | 3.11+ | `python --version` |
| Node.js | 18+ | `node --version` |
| PostgreSQL | 14+, running locally | `psql --version` |

PostgreSQL is **not optional**. The backend uses JSONB columns, `SELECT … FOR UPDATE` row locks
and unique-index race arbitration; SQLite cannot stand in for any of them.

> **Already verified on this machine:** Python 3.13.9, Node v24.14.1, npm 11.11.0,
> PostgreSQL 17.10, `backend/.venv/` present, `frontend/node_modules/` present.
> If that is still true, skip to [§4 Run it](#4-run-it).

---

## 1. Database

```bash
createdb velora
```

If `createdb` is not on PATH (common on Windows):

```bash
psql -U postgres -c "CREATE DATABASE velora"
```

Optionally, a separate scratch database for the test suite:

```bash
psql -U postgres -c "CREATE DATABASE velora_test"
```

---

## 2. Backend

### 2.1 Virtual environment and dependencies

**Windows (PowerShell or Git Bash):**

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```

**macOS / Linux:**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2.2 Configuration

```bash
cp .env.example .env
```

Then edit `backend/.env` and set at minimum:

```bash
DATABASE_URL=postgresql+psycopg://postgres:<your-password>@localhost:5432/velora
```

> **Percent-encode special characters in the password**, or the URL will not parse:
> `*` → `%2A`, `@` → `%40`, `#` → `%23`, `:` → `%3A`, `/` → `%2F`.

Two settings that are worth adding even for a local run (neither is in `.env.example` yet, and
the first one causes a confusing symptom if left out):

```bash
# Signing key for buyer/merchant session tokens. Without it, a random key is
# generated per process, so every backend restart logs everyone out.
SESSION_SECRET=any-long-random-string

# Shared secret for the human-facing API. Leave EMPTY for a localhost demo.
OPERATOR_TOKEN=
```

Full setting-by-setting reference: [OVERVIEW.md §15](OVERVIEW.md#15-configuration-reference).

### 2.3 Seed the database

```bash
python -m app.seed --reset
```

`--reset` drops every table first. Without it the seed is idempotent and keeps existing data.

This creates the schema and the demo world: 1 user, 5 merchants, 14 products, 2 agents and
2 authorization policies.

**The seed prints each agent token exactly once. Copy them — the Agent Console needs one.**
Tokens are stored only as a SHA-256 hash, so a lost token can only be replaced by re-seeding
with `--reset`.

The seed output also prints the sign-in credentials:

| Console | Email | Password |
|---|---|---|
| Buyer | `demo@velora.local` | `velora123` |
| Merchant | `<slug>@velora.local` (e.g. `blinkit@velora.local`, `demostore@velora.local`) | `merchant123` |

### 2.4 Start the API

```bash
python -m uvicorn app.main:app --port 8000
```

Add `--reload` while developing.

- API: <http://127.0.0.1:8000>
- Interactive docs: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/api/health>

Bind to `127.0.0.1` (the default). Do not expose this without setting `OPERATOR_TOKEN`.

---

## 3. Frontend

In a **second terminal**:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

The Vite dev server proxies `/api` to `http://127.0.0.1:8000`, so the browser stays same-origin
and both CORS and the SSE stream work with no extra configuration. **The backend must already be
running** or every API call fails with a connection error.

If you set `OPERATOR_TOKEN` on the backend, the frontend needs the matching build-time value:

```bash
# frontend/.env.local
VITE_OPERATOR_TOKEN=<the same value as OPERATOR_TOKEN>
```

---

## 4. Run it

Two terminals, from the repo root:

**Terminal 1 — backend**

```bash
cd backend
.venv/Scripts/python -m uvicorn app.main:app --port 8000     # Windows
# source .venv/bin/activate && python -m uvicorn app.main:app --port 8000   # macOS/Linux
```

**Terminal 2 — frontend**

```bash
cd frontend
npm run dev
```

Then open <http://localhost:5173> and sign in as `demo@velora.local` / `velora123`.

---

## 5. The demo, in five clicks

1. **Agent Console** — paste an agent token, then run
   *"Buy me wireless headphones under 2000 with good battery life"*.
   The agent parses the goal, scores the catalog and picks **SoundBeat Pro (₹1,799)**.
2. Velora returns **PENDING_APPROVAL** — inside the ₹2,000 limit, above the ₹1,500
   auto-approval threshold — with all 13 checks shown.
3. **Approvals** — the purchase is waiting, with a live expiry countdown. Approve it.
4. **Transactions** — *Create payment*, then *Confirm payment*. The state walks
   `APPROVED → PAYMENT_CREATED → PAYMENT_SUCCESS`.
5. **Audit trail** — every check, the budget reservation, your approval and the payment, all
   hash-chained, with an integrity check that recomputes the chain.

Then try *"Buy me the best headphones you can find"*. The agent picks the ₹2,499 model and Velora
blocks it with `MAX_AMOUNT_EXCEEDED` — and offers a recovery: the best alternative the *same
policy* would actually approve.

There is also a guided **Live Demo** page in the buyer sidebar (`/app/demo`).

### Merchant side

Sign in at <http://localhost:5173/merchant/login> as `blinkit@velora.local` / `merchant123` to
see the seller's view: catalog, agent-driven revenue, and which purchases the gate allowed.

---

## 6. Scripted walkthrough

With the API running:

```bash
cd backend
python demo.py
```

Re-runnable and self-seeding — it rebuilds the demo world first, so it always tells the same
story. It exercises all four decision paths, the human approval flow, the payment leg,
idempotency and the audit trail, over real HTTP against a real database.

> `demo.py` calls `seed(reset=True)`, so **it wipes the database** and mints new agent tokens.
> Any token you had pasted into the Agent Console stops working; copy the new one from its output.

---

## 7. Verification harness

```bash
cd backend
python qa_verify.py
```

An independent end-to-end harness that drives the running API over HTTP and prints EXPECTED vs
ACTUAL for every scenario. Each scenario gets its own agent and policy, so no test can be
contaminated by another's budget or quota. Exit code is non-zero if anything failed.

---

## 8. Tests

```bash
cd backend
python -m pytest tests/ -q
```

**117 tests.** Unit tests need no database. Integration tests are skipped automatically if none
is reachable — to run them, point at a scratch database:

**Git Bash / macOS / Linux:**

```bash
TEST_DATABASE_URL=postgresql+psycopg://postgres:<pass>@localhost:5432/velora_test \
  python -m pytest tests/ -q
```

**PowerShell:**

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:<pass>@localhost:5432/velora_test"
python -m pytest tests/ -q
```

The test database is dropped and recreated on every run, so never point it at `velora`.

Useful variations:

```bash
python -m pytest tests/ -v                    # verbose
python -m pytest tests/test_gate.py -q        # one module
python -m pytest tests/ -k "idempoten" -q     # by name
python -m pytest tests/ -x                    # stop at first failure
```

The suite forces the stub payment provider unconditionally, so running tests can never create a
real Razorpay order — even with `PAYMENT_PROVIDER=razorpay` in `.env`.

---

## 9. Payments

### Stub mode (default — recommended)

```bash
PAYMENT_PROVIDER=stub
```

No keys, no network, no public webhook URL. The whole approve → pay → audit flow runs on a laptop.
Settlement happens through the authenticated `/api/webhooks/simulate` endpoint, which the
Transactions page drives for you. *Fail it* in the Transactions table triggers
`PAYMENT_CREATION_FAILED` deliberately.

The public `/api/webhooks/payment` endpoint **returns 404 in stub mode on purpose**: the stub's
signing secret lives in this repo, so a valid signature would prove nothing.

### Razorpay test mode

```bash
PAYMENT_PROVIDER=razorpay
RAZORPAY_KEY_ID=rzp_test_…
RAZORPAY_KEY_SECRET=…
RAZORPAY_WEBHOOK_SECRET=…
```

Restart the backend after changing these — the provider is cached for the life of the process.

Razorpay cannot reach `localhost`, so webhooks need a tunnel:

```bash
ngrok http 8000
# then register https://<id>.ngrok.app/api/webhooks/payment in the Razorpay dashboard
```

Without a tunnel, settle through the browser instead: Checkout hands its result back to the page,
which posts it to `/api/transactions/{id}/payment/confirm`, where the signature is verified
server-side before anything settles. That path works with no public URL at all.

> **If `RAZORPAY_WEBHOOK_SECRET` is empty, `verify_webhook` fails closed and every webhook is
> rejected with 401.** That is intentional — an unverifiable webhook is not a trusted webhook —
> but it means the browser-confirm path is your only settlement route until the secret is set.

---

## 10. Common tasks

| Task | Command |
|---|---|
| Reset everything and start fresh | `cd backend && python -m app.seed --reset` |
| Mint a fresh agent token | Same as above (tokens are shown once, on creation) |
| Check the API is up | `curl http://127.0.0.1:8000/api/health` |
| See which payment provider is active | Same endpoint — it reports `payment_provider` |
| Browse the API | <http://127.0.0.1:8000/docs> |
| Build the frontend for production | `cd frontend && npm run build` |
| Preview the production build | `cd frontend && npm run preview` |

---

## 11. Troubleshooting

**`could not translate host name` / `password authentication failed`**
`DATABASE_URL` is wrong. Percent-encode special characters in the password
(`*` → `%2A`, `@` → `%40`, `#` → `%23`).

**`connection refused` on every frontend call**
The backend is not running, or not on port 8000. The Vite proxy targets `127.0.0.1:8000`.

**Every request takes ~2 seconds on Windows**
Something is using `localhost` instead of `127.0.0.1`. `localhost` resolves to `::1` first,
uvicorn binds IPv4 only, and each call eats a connection-refused retry (measured 2043 ms vs 3 ms).
The Vite config, `demo.py` and `qa_verify.py` all use `127.0.0.1` for this reason.

**Logged out after every backend restart**
`SESSION_SECRET` is unset, so tokens are signed with a random per-process key. Set it in
`backend/.env`.

**`401 Unrecognised agent token` in the Agent Console**
The token was invalidated by a re-seed (`--reset`, or a `demo.py` run). Re-seed and paste the new
one.

**`403 X-User-Id is not accepted`**
Correct behaviour — that header is unauthenticated and is refused by design. Sign in at
`/api/auth/login` and send the session token as a bearer token instead.

**`404 No payment webhook is configured`**
You are in stub mode. Use `POST /api/webhooks/simulate` (which the UI does for you), or switch to
`PAYMENT_PROVIDER=razorpay`.

**`401 Invalid webhook signature` with Razorpay**
`RAZORPAY_WEBHOOK_SECRET` is empty or does not match the value registered in the Razorpay
dashboard.

**Tests all skip**
No database was reachable at `TEST_DATABASE_URL`. Create `velora_test` and set the variable.

**Seed crashes printing a rupee amount on Windows**
The console is on cp1252. `seed.py`, `demo.py` and `qa_verify.py` already call
`sys.stdout.reconfigure(encoding="utf-8")`; if a new script hits this, add the same line.

**`ModuleNotFoundError: app`**
Run backend commands from inside `backend/`, and use the venv's Python
(`.venv/Scripts/python` on Windows).

---

## 12. Security notes for anything beyond localhost

The defaults are tuned for a laptop demo. Before exposing this anywhere:

1. **Set `OPERATOR_TOKEN`** and the matching `VITE_OPERATOR_TOKEN`. Unset, the entire
   human-facing surface — approve, reject, pay, create policies — is open.
2. **Set `SESSION_SECRET`** to a long random value.
3. **Leave `DEV_ALLOW_USER_HEADER=false`.** Set to true, anyone can act as any user by sending
   an `X-User-Id` header.
4. **Change the seeded demo passwords** (`velora123`, `merchant123`).
5. **Keep the server bound to `127.0.0.1`** unless it is behind a reverse proxy that terminates
   TLS and adds rate limiting — there is none in the app.
6. **Never commit `backend/.env`.** It is covered by `backend/.gitignore`; keep it that way.

Known gaps, deliberately scoped out for the MVP: no rate limiting, `create_all` instead of
Alembic migrations, and a per-process event bus (so live updates assume a single backend
instance). See [OVERVIEW.md §17](OVERVIEW.md#17-observations-and-loose-ends).
