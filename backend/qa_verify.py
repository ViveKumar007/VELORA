"""Independent end-to-end verification harness.

Drives the running API over real HTTP and reports EXPECTED vs ACTUAL for
every scenario. Each scenario gets its own agent and policy so no test can
be contaminated by another's budget or quota.

Run with the API up:   python qa_verify.py
Exit code is non-zero if anything failed.
"""

import json
import sys
import threading
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000"  # not "localhost": IPv6-first resolution costs ~2s/request on Windows
RESULTS = []


def call(method, path, body=None, token=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.loads(res.read() or b"null")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw or b"null")
        except json.JSONDecodeError:
            return exc.code, {"detail": raw.decode(errors="replace")[:200]}
    except urllib.error.URLError as exc:
        raise SystemExit(f"Cannot reach {BASE}: {exc}")


def check(phase, what, expected, actual):
    ok = expected == actual
    RESULTS.append((phase, what, expected, actual, ok))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {what}")
    if not ok:
        print(f"         expected: {expected!r}")
        print(f"         actual  : {actual!r}")
    return ok


def phase(title):
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def new_agent(name):
    status, agent = call("POST", "/api/agents", {"name": name, "agent_type": "shopping"})
    if status != 201:
        raise SystemExit(f"Could not create agent: {status} {agent}")
    return agent


def new_policy(agent_id, **overrides):
    body = {
        "agent_id": agent_id,
        "name": "QA policy",
        "max_per_transaction": 2000,
        "total_budget": 2000,
        "approval_threshold": 1500,
        "allowed_categories": ["electronics"],
        "allowed_merchants": ["DemoStore"],
        "max_transactions": 1,
        "one_time_use": True,
        "expires_in_minutes": 30,
        "currency": "INR",
    }
    body.update(overrides)
    return call("POST", "/api/policies", body)


def buy(token, product_id, key, **kw):
    body = {"product_id": product_id, "idempotency_key": key}
    body.update(kw)
    return call("POST", "/api/agent/request", body, token=token)


def select_first_user():
    """Oldest user -- the one current_user resolves to by default."""
    from sqlalchemy import select

    from app.models import User

    return select(User).order_by(User.created_at.asc()).limit(1)


def main():
    _, products = call("GET", "/api/products")
    if not products:
        raise SystemExit("No products. Run: python -m app.seed --reset")
    cat = {p["name"]: p for p in products}
    LITE = cat["SoundBeat Lite"]["id"]
    PRO = cat["SoundBeat Pro"]["id"]
    PREMIUM = cat["Premium Audio Max"]["id"]
    SUB = cat["Gaming Subscription (3 months)"]["id"]
    HOUSE = cat["AudioHouse Studio Buds"]["id"]

    # ---------------------------------------------------------------- P4
    phase("PHASE 4 — POLICY CREATION")
    agent = new_agent("qa-policy-agent")
    status, view = new_policy(agent["id"], name="shopping-agent-001 policy")
    check("P4", "policy created (HTTP 201)", 201, status)
    p = view["policy"]
    check("P4", "max_per_transaction stored as paise", 200000, p["max_per_transaction_paise"])
    check("P4", "approval_threshold stored as paise", 150000, p["approval_threshold_paise"])
    check("P4", "allowed_categories", ["electronics"], p["allowed_categories"])
    check("P4", "allowed_merchants", ["DemoStore"], p["allowed_merchants"])
    check("P4", "max_transactions", 1, p["max_transactions"])
    check("P4", "one_time_use", True, p["one_time_use"])
    check("P4", "status ACTIVE", "ACTIVE", p["status"])

    status, fetched = call("GET", f"/api/policies/{p['id']}")
    check("P4", "policy retrievable", 200, status)
    check("P4", "retrieved id matches", p["id"], fetched["policy"]["id"])

    status, bad = new_policy(agent["id"], approval_threshold=5000, max_per_transaction=2000)
    check("P4", "incoherent policy rejected (threshold > limit)", 422, status)

    # ---------------------------------------------------------------- P5
    phase("PHASE 5 — SCENARIO A: AUTO APPROVAL (SoundBeat Lite ₹1,299)")
    a = new_agent("qa-auto")
    new_policy(a["id"])
    status, r = buy(a["token"], LITE, "qa_auto_0001")
    t = r["transaction"]
    check("P5", "HTTP 200", 200, status)
    check("P5", "decision", "APPROVED", t["decision"])
    check("P5", "state", "APPROVED", t["state"])
    check("P5", "reason_code", "WITHIN_POLICY", t["reason_code"])
    check("P5", "amount", 129900, t["requested_amount_paise"])
    checks = {c["name"]: c["status"] for c in t["checks"]}
    for name in [
        "Authorization Exists", "Agent Status", "Agent Identity", "Authorization Active",
        "Validity Window", "Merchant", "Category", "Per-Transaction Limit", "Approval Threshold",
    ]:
        check("P5", f"check '{name}' PASS", "PASS", checks.get(name))
    check("P5", "explanation present", True, bool(t["explanation"]))

    status, audit = call("GET", f"/api/transactions/{t['id']}/audit")
    kinds = {e["event_type"] for e in audit["entries"]}
    check("P5", "audit has REQUEST_RECEIVED", True, "REQUEST_RECEIVED" in kinds)
    check("P5", "audit has DECISION_MADE", True, "DECISION_MADE" in kinds)
    check("P5", "audit chain valid", True, audit["integrity"]["valid"])

    status, paid = call("POST", f"/api/transactions/{t['id']}/payment", {"force_failure": False})
    check("P5", "payment allowed for APPROVED", 200, status)
    check("P5", "state after payment", "PAYMENT_CREATED", paid["transaction"]["state"])

    # ---------------------------------------------------------------- P6
    phase("PHASE 6 — SCENARIO B: HUMAN APPROVAL (SoundBeat Pro ₹1,799)")
    b = new_agent("qa-approve")
    new_policy(b["id"])
    status, r = buy(b["token"], PRO, "qa_pend_0001")
    t = r["transaction"]
    check("P6", "decision", "PENDING_APPROVAL", t["decision"])
    check("P6", "state", "PENDING_APPROVAL", t["state"])
    check("P6", "reason_code", "APPROVAL_THRESHOLD_EXCEEDED", t["reason_code"])
    check("P6", "no payment order created", None, t["payment_order_id"])
    check("P6", "hard limit still PASS",
          "PASS", {c["name"]: c["status"] for c in t["checks"]}["Per-Transaction Limit"])

    status, _ = call("POST", f"/api/transactions/{t['id']}/payment", {"force_failure": False})
    check("P6", "payment REFUSED while pending", 409, status)

    status, queue = call("GET", "/api/approvals")
    check("P6", "appears in approval centre", True, any(i["transaction_id"] == t["id"] for i in queue))

    status, appr = call("POST", f"/api/transactions/{t['id']}/approve", {})
    check("P6", "approve succeeds", 200, status)
    check("P6", "state after approval", "APPROVED", appr["transaction"]["state"])
    check("P6", "decision preserved as gate verdict",
          "PENDING_APPROVAL", appr["transaction"]["decision"])

    status, paid = call("POST", f"/api/transactions/{t['id']}/payment", {"force_failure": False})
    check("P6", "payment allowed after approval", 200, status)
    check("P6", "state", "PAYMENT_CREATED", paid["transaction"]["state"])

    status, done = call("POST", "/api/webhooks/simulate", {"transaction_id": t["id"], "succeed": True})
    check("P6", "payment success via webhook", "PAYMENT_SUCCESS", done["transaction"]["state"])

    # reject path, separate agent
    b2 = new_agent("qa-reject")
    new_policy(b2["id"])
    _, r2 = buy(b2["token"], PRO, "qa_rej_0001")
    t2 = r2["transaction"]
    status, rej = call("POST", f"/api/transactions/{t2['id']}/reject", {"note": "QA reject"})
    check("P6", "reject succeeds", 200, status)
    check("P6", "state after reject", "REJECTED", rej["transaction"]["state"])
    status, _ = call("POST", f"/api/transactions/{t2['id']}/payment", {"force_failure": False})
    check("P6", "payment REFUSED after reject", 409, status)
    _, pol = call("GET", "/api/policies")
    rejected_policy = [x for x in pol if x["policy"]["agent_id"] == b2["id"]][0]
    check("P6", "budget released on reject", 0, rejected_policy["policy"]["amount_reserved_paise"])
    check("P6", "txn slot returned on reject", 0, rejected_policy["policy"]["transactions_used"])

    # ---------------------------------------------------------------- P7
    phase("PHASE 7 — SCENARIO C: HARD BLOCK (Premium Audio Max ₹2,499)")
    c = new_agent("qa-block")
    new_policy(c["id"])
    status, r = buy(c["token"], PREMIUM, "qa_block_0001")
    t = r["transaction"]
    check("P7", "decision", "BLOCKED", t["decision"])
    check("P7", "state", "BLOCKED", t["state"])
    check("P7", "reason_code", "MAX_AMOUNT_EXCEEDED", t["reason_code"])
    check("P7", "no payment order", None, t["payment_order_id"])
    status, _ = call("POST", f"/api/transactions/{t['id']}/payment", {"force_failure": False})
    check("P7", "payment REFUSED for blocked", 409, status)
    _, pol = call("GET", "/api/policies")
    blocked_policy = [x for x in pol if x["policy"]["agent_id"] == c["id"]][0]
    check("P7", "no budget reserved", 0, blocked_policy["policy"]["amount_reserved_paise"])
    check("P7", "no quota consumed", 0, blocked_policy["policy"]["transactions_used"])
    _, audit = call("GET", f"/api/transactions/{t['id']}/audit")
    codes = {e["reason_code"] for e in audit["entries"]}
    check("P7", "audit records the reason", True, "MAX_AMOUNT_EXCEEDED" in codes)

    # ---------------------------------------------------------------- P8
    phase("PHASE 8 — SCENARIO D: CATEGORY BLOCK (Gaming Subscription ₹999)")
    d = new_agent("qa-category")
    new_policy(d["id"])
    status, r = buy(d["token"], SUB, "qa_cat_0001")
    t = r["transaction"]
    check("P8", "decision", "BLOCKED", t["decision"])
    check("P8", "reason_code", "CATEGORY_NOT_ALLOWED", t["reason_code"])
    check("P8", "amount check still PASS (only scope failed)",
          "PASS", {x["name"]: x["status"] for x in t["checks"]}["Per-Transaction Limit"])
    status, _ = call("POST", f"/api/transactions/{t['id']}/payment", {"force_failure": False})
    check("P8", "payment REFUSED", 409, status)

    # ---------------------------------------------------------------- P9
    phase("PHASE 9 — MERCHANT RESTRICTION (AudioHouse ₹1,499)")
    e = new_agent("qa-merchant")
    new_policy(e["id"])
    status, r = buy(e["token"], HOUSE, "qa_merch_0001")
    t = r["transaction"]
    check("P9", "decision", "BLOCKED", t["decision"])
    check("P9", "reason_code", "MERCHANT_NOT_ALLOWED", t["reason_code"])

    # ---------------------------------------------------------------- P10
    phase("PHASE 10 — EXPIRED AUTHORIZATION")
    f = new_agent("qa-expiry")
    _, fview = new_policy(f["id"])
    expire_policy(fview["policy"]["id"])
    status, r = buy(f["token"], LITE, "qa_exp_0001")
    t = r["transaction"]
    check("P10", "decision", "BLOCKED", t["decision"])
    check("P10", "reason_code", "AUTHORIZATION_EXPIRED", t["reason_code"])

    # ---------------------------------------------------------------- P11
    phase("PHASE 11 — MAX TRANSACTION COUNT (max_transactions=1, not one-time)")
    g = new_agent("qa-count")
    new_policy(g["id"], max_transactions=1, one_time_use=False, total_budget=5000)
    _, r1 = buy(g["token"], LITE, "qa_cnt_0001")
    check("P11", "first transaction approved", "APPROVED", r1["transaction"]["decision"])
    _, r2 = buy(g["token"], LITE, "qa_cnt_0002")
    check("P11", "second transaction blocked", "BLOCKED", r2["transaction"]["decision"])
    check("P11", "reason_code names the transaction cap",
          "MAX_TRANSACTIONS_EXCEEDED", r2["transaction"]["reason_code"])
    _, pol = call("GET", "/api/policies")
    counted = [x for x in pol if x["policy"]["agent_id"] == g["id"]][0]
    check("P11", "counter accurate", 1, counted["policy"]["transactions_used"])

    # ---------------------------------------------------------------- P12
    phase("PHASE 12 — ONE-TIME USE")
    h = new_agent("qa-onetime")
    new_policy(h["id"], one_time_use=True, max_transactions=5, total_budget=10000)
    _, r1 = buy(h["token"], LITE, "qa_one_0001")
    check("P12", "first use approved", "APPROVED", r1["transaction"]["decision"])
    _, r2 = buy(h["token"], LITE, "qa_one_0002")
    check("P12", "reuse blocked", "BLOCKED", r2["transaction"]["decision"])
    check("P12", "reason_code", "AUTHORIZATION_ALREADY_USED", r2["transaction"]["reason_code"])

    # ---------------------------------------------------------------- P13
    phase("PHASE 13 — IDEMPOTENCY & DUPLICATE PAYMENTS")
    i = new_agent("qa-idem")
    new_policy(i["id"])
    KEY = "agent_123_purchase_456"
    _, first = buy(i["token"], LITE, KEY)
    _, second = buy(i["token"], LITE, KEY)
    check("P13", "same transaction returned", first["transaction"]["id"], second["transaction"]["id"])
    check("P13", "replay flagged", True, second["replayed"])
    _, pol = call("GET", "/api/policies")
    idem_policy = [x for x in pol if x["policy"]["agent_id"] == i["id"]][0]
    check("P13", "quota consumed once only", 1, idem_policy["policy"]["transactions_used"])

    status, conflict = buy(i["token"], PRO, KEY)
    check("P13", "same key, different product -> 409", 409, status)

    txn_id = first["transaction"]["id"]
    _, p1 = call("POST", f"/api/transactions/{txn_id}/payment", {"force_failure": False})
    _, p2 = call("POST", f"/api/transactions/{txn_id}/payment", {"force_failure": False})
    check("P13", "duplicate payment returns same order",
          p1["transaction"]["payment_order_id"], p2["transaction"]["payment_order_id"])

    # rapid concurrent duplicates
    j = new_agent("qa-race")
    new_policy(j["id"])
    ids, errors = [], []
    lock = threading.Lock()

    def racer():
        try:
            status, res = buy(j["token"], LITE, "race_same_key_1")
            with lock:
                if isinstance(res, dict) and "transaction" in res:
                    ids.append(res["transaction"]["id"])
                else:
                    errors.append(f"HTTP {status}: {str(res)[:90]}")
        except Exception as exc:  # noqa: BLE001 - reported by the checks below
            with lock:
                errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=racer) for _ in range(5)]
    for th in threads: th.start()
    for th in threads: th.join(timeout=20)
    check("P13", "5 concurrent identical requests: none error", [], errors)
    check("P13", "5 concurrent identical requests: all 5 answered", 5, len(ids))
    check("P13", "5 concurrent identical requests -> 1 transaction", 1, len(set(ids)))
    _, pol = call("GET", "/api/policies")
    race_policy = [x for x in pol if x["policy"]["agent_id"] == j["id"]][0]
    check("P13", "concurrent duplicates consumed one slot", 1,
          race_policy["policy"]["transactions_used"])

    # duplicate webhooks
    _, wpay = call("POST", f"/api/transactions/{txn_id}/payment", {"force_failure": False})
    call("POST", "/api/webhooks/simulate", {"transaction_id": txn_id, "succeed": True})
    _, dup = call("POST", "/api/webhooks/simulate", {"transaction_id": txn_id, "succeed": True})
    check("P13", "duplicate webhook keeps PAYMENT_SUCCESS", "PAYMENT_SUCCESS", dup["transaction"]["state"])
    _, pol = call("GET", "/api/policies")
    settled = [x for x in pol if x["policy"]["agent_id"] == i["id"]][0]["policy"]
    check("P13", "settled exactly once", 129900, settled["amount_settled_paise"])

    # ---------------------------------------------------------------- P14
    phase("PHASE 14 — STATE MACHINE (invalid transitions must be impossible)")
    k = new_agent("qa-states")
    new_policy(k["id"], total_budget=20000, max_transactions=5, one_time_use=False)

    _, blk = buy(k["token"], PREMIUM, "qa_st_block")
    s, _ = call("POST", f"/api/transactions/{blk['transaction']['id']}/payment", {})
    check("P14", "BLOCKED -> PAYMENT_CREATED refused", 409, s)

    _, pend = buy(k["token"], PRO, "qa_st_pend")
    s, _ = call("POST", f"/api/transactions/{pend['transaction']['id']}/payment", {})
    check("P14", "PENDING_APPROVAL -> PAYMENT_CREATED refused", 409, s)
    call("POST", f"/api/transactions/{pend['transaction']['id']}/reject", {})
    s, _ = call("POST", f"/api/transactions/{pend['transaction']['id']}/payment", {})
    check("P14", "REJECTED -> PAYMENT_CREATED refused", 409, s)
    s, _ = call("POST", f"/api/transactions/{pend['transaction']['id']}/approve", {})
    check("P14", "REJECTED -> APPROVED refused", 409, s)

    _, ok = buy(k["token"], LITE, "qa_st_ok")
    tid = ok["transaction"]["id"]
    call("POST", f"/api/transactions/{tid}/payment", {})
    call("POST", "/api/webhooks/simulate", {"transaction_id": tid, "succeed": False})
    _, after = call("GET", f"/api/transactions/{tid}")
    check("P14", "payment failure state", "PAYMENT_FAILED", after["transaction"]["state"])
    s, res = call("POST", "/api/webhooks/simulate", {"transaction_id": tid, "succeed": True})
    check("P14", "PAYMENT_FAILED -> PAYMENT_SUCCESS refused",
          "PAYMENT_FAILED", res["transaction"]["state"] if s == 200 else res)

    # ---------------------------------------------------------------- P15
    phase("PHASE 15 — AUDIT TRAIL COMPLETENESS")
    _, trail = call("GET", f"/api/transactions/{txn_id}/audit")
    entries = trail["entries"]
    check("P15", "chain valid", True, trail["integrity"]["valid"])
    required = ["created_at", "transaction_id", "agent_id", "event_type", "explanation",
                "previous_state", "new_state", "entry_hash"]
    first_entry = entries[0]
    for field in required:
        check("P15", f"entry has '{field}'", True, field in first_entry)
    check("P15", "policy_id recorded on decision", True,
          any(e["policy_id"] for e in entries))
    kinds = {e["event_type"] for e in entries}
    for expected_event in ["REQUEST_RECEIVED", "EVALUATION_STARTED", "CHECK_EVALUATED",
                           "DECISION_MADE", "BUDGET_RESERVED", "PAYMENT_CREATED",
                           "PAYMENT_SUCCEEDED"]:
        check("P15", f"records {expected_event}", True, expected_event in kinds)

    _, trail6 = call("GET", f"/api/transactions/{t2['id']}/audit")
    check("P15", "records HUMAN_REJECTED", True,
          "HUMAN_REJECTED" in {e["event_type"] for e in trail6["entries"]})

    # ---------------------------------------------------------------- P19
    phase("PHASE 19 — ERROR HANDLING")
    s, _ = call("POST", "/api/agent/request", {"product_id": LITE}, token=i["token"])
    check("P19", "missing idempotency_key -> 422", 422, s)
    s, _ = call("POST", "/api/agent/request",
                {"product_id": LITE, "idempotency_key": "short"}, token=i["token"])
    check("P19", "too-short idempotency key -> 422", 422, s)
    s, _ = call("POST", "/api/agent/request", {}, token=i["token"])
    check("P19", "empty body -> 422", 422, s)
    m = new_agent("qa-errors")
    new_policy(m["id"])
    s, r = buy(m["token"], "prd_does_not_exist", "qa_err_0001")
    check("P19", "unknown product -> blocked, not crash", "BLOCKED", r["transaction"]["decision"])
    check("P19", "unknown product reason", "PRODUCT_NOT_FOUND", r["transaction"]["reason_code"])
    s, _ = call("GET", "/api/transactions/txn_nonexistent")
    check("P19", "missing transaction -> 404", 404, s)
    s, _ = call("GET", "/api/policies/pol_nonexistent")
    check("P19", "missing policy -> 404", 404, s)
    s, _ = call("POST", "/api/policies", {"agent_id": m["id"], "max_per_transaction": -100,
                                          "total_budget": 2000, "approval_threshold": 100})
    check("P19", "negative amount rejected", 422, s)
    s, _ = call("POST", "/api/policies", {"agent_id": m["id"], "max_per_transaction": 0,
                                          "total_budget": 2000, "approval_threshold": 100})
    check("P19", "zero amount rejected", 422, s)
    s, _ = call("POST", "/api/agent/request", {"product_id": LITE, "idempotency_key": "qa_noauth_1"})
    check("P19", "no agent token -> 401", 401, s)
    s, _ = call("POST", "/api/agent/request", {"product_id": LITE, "idempotency_key": "qa_badtok_1"},
                token="vla_totally_invalid_token")
    check("P19", "bad agent token -> 401", 401, s)

    n = new_agent("qa-provider-fail")
    new_policy(n["id"])
    _, okr = buy(n["token"], LITE, "qa_provfail_1")
    s, failed = call("POST", f"/api/transactions/{okr['transaction']['id']}/payment",
                     {"force_failure": True})
    check("P19", "provider failure handled", "PAYMENT_CREATION_FAILED", failed["transaction"]["state"])
    check("P19", "authorization decision unchanged by provider failure",
          "APPROVED", failed["transaction"]["decision"])
    _, ptrail = call("GET", f"/api/transactions/{okr['transaction']['id']}/audit")
    check("P19", "audit distinguishes auth success from payment failure", True,
          any("Authorization was successful" in e["explanation"] for e in ptrail["entries"]))
    s, retried = call("POST", f"/api/transactions/{okr['transaction']['id']}/payment",
                      {"force_failure": False})
    check("P19", "provider failure is retryable", "PAYMENT_CREATED", retried["transaction"]["state"])

    # ---------------------------------------------------------------- P18
    phase("PHASE 18 — AUTHORIZATION / IDOR PROBES")
    # Regression: X-User-Id used to select any user, so anyone who guessed a
    # user id could read that user's policies, approve their purchases and
    # create payments on their behalf.
    from app.db import SessionLocal
    from app.models import User as UserModel

    session = SessionLocal()
    try:
        victim_id = session.scalars(select_first_user()).first().id
    finally:
        session.close()

    s, _ = call("GET", "/api/policies", headers={"X-User-Id": victim_id})
    check("P18", "impersonation via X-User-Id refused (read)", 403, s)

    v = new_agent("qa-idor-victim")
    new_policy(v["id"])
    _, vr = buy(v["token"], PRO, "qa_idor_0001")
    victim_txn = vr["transaction"]["id"]
    check("P18", "victim has a pending purchase", "PENDING_APPROVAL", vr["transaction"]["state"])

    s, _ = call("POST", f"/api/transactions/{victim_txn}/approve", {},
                headers={"X-User-Id": victim_id})
    check("P18", "impersonation via X-User-Id refused (approve)", 403, s)
    s, _ = call("POST", f"/api/transactions/{victim_txn}/payment", {"force_failure": False},
                headers={"X-User-Id": victim_id})
    check("P18", "impersonation via X-User-Id refused (pay)", 403, s)

    _, after = call("GET", f"/api/transactions/{victim_txn}")
    check("P18", "victim purchase untouched by the attempt",
          "PENDING_APPROVAL", after["transaction"]["state"])

    # Stub mode must not accept externally-signed webhooks: the stub secret
    # lives in the source tree, so it is forgeable by anyone.
    from app.services.payments.stub import StubPaymentProvider as Stub
    body = json.dumps(Stub.capture_payload("order_stub_forged", succeeded=True)).encode()
    req = urllib.request.Request(BASE + "/api/webhooks/payment", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Velora-Signature", Stub.sign(body))
    try:
        with urllib.request.urlopen(req) as res:
            forged_status = res.status
    except urllib.error.HTTPError as exc:
        forged_status = exc.code
    check("P18", "forged stub webhook refused", 404, forged_status)

    # cross-agent identity claim
    s, r = call("POST", "/api/agent/request",
                {"product_id": LITE, "idempotency_key": "qa_spoof_0001",
                 "agent_id": "agt_someone_else"}, token=m["token"])
    check("P18", "spoofed agent_id in body is blocked", "BLOCKED", r["transaction"]["decision"])
    check("P18", "spoof reason", "AGENT_IDENTITY_MISMATCH", r["transaction"]["reason_code"])

    # ------------------------------------------------------------- SUMMARY
    phase("SUMMARY")
    failed = [r for r in RESULTS if not r[4]]
    by_phase = {}
    for ph, _, _, _, ok in RESULTS:
        agg = by_phase.setdefault(ph, [0, 0])
        agg[0 if ok else 1] += 1
    for ph in sorted(by_phase, key=lambda x: int(x[1:])):
        passed, failures = by_phase[ph]
        flag = "OK  " if failures == 0 else "FAIL"
        print(f"  {flag} {ph}: {passed} passed, {failures} failed")
    print(f"\n  TOTAL: {len(RESULTS) - len(failed)} passed, {len(failed)} failed")
    if failed:
        print("\n  FAILURES:")
        for ph, what, exp, act, _ in failed:
            print(f"    {ph} {what}\n       expected {exp!r}, got {act!r}")
    return 1 if failed else 0


def expire_policy(policy_id):
    """Backdate a policy's expiry directly. No API does this by design."""
    from datetime import timedelta

    from app.db import SessionLocal
    from app.models import AuthorizationPolicy, utcnow

    db = SessionLocal()
    try:
        policy = db.get(AuthorizationPolicy, policy_id)
        policy.expires_at = utcnow() - timedelta(minutes=1)
        policy.valid_from = utcnow() - timedelta(minutes=10)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
