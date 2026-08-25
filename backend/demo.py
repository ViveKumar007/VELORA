"""End-to-end walkthrough of every Velora decision path.

Start the API, then:  python demo.py

Rebuilds the demo world first, so it is re-runnable and always tells the same
story. Everything after that goes over real HTTP against a real database, so
what it prints is what the system actually did.

Order matters: the refusals run first, because the demo policy is single-use
and the successful purchase consumes it.
"""

import io
import json
import sys
import urllib.error
import urllib.request
from contextlib import redirect_stdout

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000"  # not "localhost": IPv6-first resolution costs ~2s/request on Windows
MARK = {"PASS": "PASS", "FAIL": "FAIL", "REVIEW": "REVW", "SKIP": "skip"}


def reseed() -> str:
    """Rebuild the demo world in-process and return the fresh agent token."""
    from app.seed import seed

    captured = io.StringIO()
    with redirect_stdout(captured):
        seed(reset=True)

    for line in captured.getvalue().splitlines():
        token = line.strip()
        if token.startswith("vla_"):
            return token
    raise SystemExit("Seed did not produce an agent token:\n" + captured.getvalue())


def call(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null")
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"Could not reach {BASE}. Start the API first:\n"
            f"  python -m uvicorn app.main:app --reload\n({exc})"
        ) from exc


def expect(status, payload, what):
    """Fail loudly rather than KeyError-ing three lines later."""
    if not (200 <= status < 300) or not isinstance(payload, dict):
        raise SystemExit(f"{what} failed -> HTTP {status}: {payload}")
    return payload


def rule(title):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def show(txn, checks=True):
    t = txn["transaction"]
    print(f"  {t['product_name']}   {txn['amount_display']}")
    print(f"  decision : {t['decision']}    state: {t['state']}")
    print(f"  reason   : {t['reason_code']}")
    print(f"  why      : {t['explanation']}")
    if checks:
        for c in t["checks"]:
            if c["status"] == "SKIP":
                continue
            print(f"      [{MARK[c['status']]}] {c['name']}: {c['detail']}")
    return t["id"]


def buy(catalog, name, key, token):
    return call(
        "POST", "/api/agent/request",
        {"product_id": catalog[name]["id"], "idempotency_key": key},
        token=token,
    )[1]


def main():
    token = sys.argv[1] if len(sys.argv) > 1 else reseed()
    print(f"Demo world rebuilt. Agent token: {token[:16]}...")

    _, products = call("GET", "/api/products")
    catalog = {p["name"]: p for p in products}

    rule("CATALOG  (Velora owns this data -- the agent cannot describe a product)")
    for p in products:
        print(f"  {p['price_display']:>8}  {p['name']:<34} [{p['category']} / {p['merchant']}]")

    rule("1. BLOCKED -- exceeds the per-transaction limit")
    blocked_id = show(buy(catalog, "Premium Audio Max", "demo_premium_1", token))
    status, refusal = call("POST", f"/api/transactions/{blocked_id}/payment", {})
    print(f"\n  trying to pay it anyway -> HTTP {status}")
    print(f"    {refusal.get('detail')}")

    rule("2. BLOCKED -- category outside the authorization")
    show(buy(catalog, "Gaming Subscription (3 months)", "demo_sub_1", token))

    rule("3. BLOCKED -- merchant outside the authorization")
    show(buy(catalog, "AudioHouse Studio Buds", "demo_house_1", token))

    rule("4. PENDING APPROVAL -- within the limit, over the auto-approve threshold")
    pending = buy(catalog, "SoundBeat Pro", "demo_pro_1", token)
    pro_id = show(pending)

    _, queue = call("GET", "/api/approvals")
    print(f"\n  approval queue: {len(queue)} item(s) awaiting a human")
    for item in queue:
        print(f"    {item['transaction']['product_name']}  {item['amount_display']}")
        print(f"    prompt: {item['prompt']}")

    print("\n  -- trying to pay before the human decides --")
    status, refusal = call("POST", f"/api/transactions/{pro_id}/payment", {})
    print(f"    HTTP {status}: {refusal.get('detail')}")

    rule("5. HUMAN APPROVES -> PAYMENT")
    approved = expect(*call("POST", f"/api/transactions/{pro_id}/approve", {}), "Approve")
    t = approved["transaction"]
    print(f"  state now : {t['state']}")
    print(f"  decision  : {t['decision']}   <- the gate's original verdict, never rewritten")

    _, paid = call("POST", f"/api/transactions/{pro_id}/payment", {"force_failure": False})
    print(f"  payment   : {paid['transaction']['state']}  order {paid['transaction']['payment_order_id']}")

    _, settled = call("POST", "/api/webhooks/simulate", {"transaction_id": pro_id, "succeed": True})
    print(f"  webhook   : {settled['transaction']['state']}")

    rule("6. IDEMPOTENCY")
    replay = buy(catalog, "SoundBeat Pro", "demo_pro_1", token)
    print(f"  same key replayed -> same transaction : {replay['transaction']['id'] == pro_id}")
    print(f"                       replayed flag    : {replay['replayed']}")
    print(f"                       state unchanged  : {replay['transaction']['state']}")
    status, conflict = call(
        "POST", "/api/agent/request",
        {"product_id": catalog["SoundBeat Lite"]["id"], "idempotency_key": "demo_pro_1"},
        token=token,
    )
    print(f"  same key, different product -> HTTP {status}")
    print(f"    {conflict.get('detail')}")

    rule("7. AUTHORIZATION SPENT -- the single-use policy is now exhausted")
    show(buy(catalog, "SoundBeat Lite", "demo_lite_1", token), checks=False)

    rule("8. AUDIT TRAIL of the completed purchase")
    _, trail = call("GET", f"/api/transactions/{pro_id}/audit")
    for e in trail["entries"]:
        move = f"{e['previous_state'] or '-'} -> {e['new_state'] or '-'}"
        print(f"  {e['seq']:>2}. {e['event_type']:<24} {move}")
        print(f"      {e['explanation'][:92]}")
    print(f"\n  integrity check: {trail['integrity']}")

    rule("9. AGENT CONSOLE -- plain-language goal, end to end")
    _, run = call(
        "POST", "/api/agent/run",
        {"goal": "Buy me wireless headphones under 2000 with good battery life", "auto_submit": False},
        token=token,
    )
    rec = run["recommendation"]
    print(f"  goal      : {run['goal']}")
    print(f"  parsed    : {json.dumps(rec['intent'], ensure_ascii=False)}")
    print(f"  chose     : {rec['chosen']['name']} ({rec['chosen']['price_display']})")
    print(f"  rationale : {rec['rationale']}")
    print("  considered:")
    for alt in rec["alternatives"]:
        print(f"      {alt['price_display']:>8}  {alt['name']:<32} score {alt['score']}")

    rule("10. DASHBOARD")
    _, stats = call("GET", "/api/dashboard")
    for key, value in stats.items():
        print(f"  {key:<26} {value}")

    print("\nDone.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
