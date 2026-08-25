"""The only code in Velora that may create a payment.

Every path in here re-checks authorization against the database under a row
lock before touching the provider. The gate's earlier decision is not taken
on trust: if the transaction is not in a payable state right now, no order is
created. That is what makes the invariant hold under concurrency, retries and
double-clicks, not merely in the happy path.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Decision, EventType, TransactionRequest, TxnState
from app.services import audit, budget
from app.services.gateway import move_state
from app.services.payments import PaymentError, get_provider
from app.services.state_machine import is_payable
from app.utils.money import format_inr


class PaymentNotAllowed(Exception):
    """An attempt to pay for something Velora has not authorized."""


def _lock_transaction(db: Session, transaction_id: str) -> TransactionRequest:
    txn = db.scalars(
        select(TransactionRequest)
        .where(TransactionRequest.id == transaction_id)
        .with_for_update()
    ).first()
    if txn is None:
        raise PaymentNotAllowed(f"Transaction {transaction_id} does not exist.")
    return txn


def create_payment(
    db: Session, transaction_id: str, *, force_failure: bool = False
) -> TransactionRequest:
    """Create a provider order for an approved transaction."""
    txn = _lock_transaction(db, transaction_id)

    # Idempotency first: a repeat call for an order that already exists must
    # return it, not be re-judged. Checking payability first would reject the
    # repeat, because PAYMENT_CREATED is (correctly) not a payable state.
    if txn.payment_order_id and txn.state == TxnState.PAYMENT_CREATED:
        audit.record(
            db,
            event_type=EventType.DUPLICATE_SUPPRESSED,
            transaction_id=txn.id,
            agent_id=txn.agent_id,
            policy_id=txn.policy_id,
            explanation="Payment order already exists; returned it instead of creating another.",
            previous_state=txn.state,
            new_state=txn.state,
            metadata={"order_id": txn.payment_order_id},
        )
        db.commit()
        return txn

    # Three independent gates, all fail closed.
    #
    # `state` is the authority on whether this is payable *now*: a request the
    # gate escalated becomes payable only once a human moves it to APPROVED.
    if not is_payable(txn.state):
        raise PaymentNotAllowed(
            f"Transaction is {txn.state}. Only an approved transaction can be paid, "
            f"so no payment was created."
        )
    # `decision` is the gate's original verdict and is never rewritten -- a
    # human approval changes the state, not the history of what the gate
    # decided. So this checks only that the gate did not refuse outright.
    if txn.decision == Decision.BLOCKED:
        raise PaymentNotAllowed(
            "Velora blocked this transaction. No payment can ever be created for it."
        )
    # An authorized transaction always holds a budget reservation. If it does
    # not, the accounting and the lifecycle disagree and we refuse rather than
    # spend money against an unreserved budget.
    if not txn.budget_reserved:
        raise PaymentNotAllowed(
            "This transaction holds no budget reservation, so it is not authorized to pay."
        )
    provider = get_provider()
    notes = {
        "transaction_id": txn.id,
        "agent_id": txn.agent_id,
        "policy_id": txn.policy_id or "",
    }
    if force_failure:
        notes["force_failure"] = "true"

    try:
        order = provider.create_order(
            amount_paise=txn.requested_amount_paise,
            currency=txn.currency,
            receipt=txn.id,
            notes=notes,
        )
    except PaymentError as exc:
        # Authorization succeeded; the provider did not. These are different
        # facts and the audit trail must keep them apart.
        txn.payment_error = str(exc)
        move_state(
            db, txn, TxnState.PAYMENT_CREATION_FAILED,
            event_type=EventType.PAYMENT_CREATION_FAILED,
            explanation=(
                f"Authorization was successful, but the payment could not be created: "
                f"{exc} The budget remains reserved so this can be retried."
            ),
            metadata={"provider": getattr(provider, "name", "unknown"), "error": str(exc)},
        )
        db.commit()
        return txn

    txn.payment_order_id = order.order_id
    txn.payment_error = None
    move_state(
        db, txn, TxnState.PAYMENT_CREATED,
        event_type=EventType.PAYMENT_CREATED,
        explanation=(
            f"Payment order {order.order_id} created for "
            f"{format_inr(order.amount_paise)} via {order.provider}."
        ),
        metadata={
            "order_id": order.order_id,
            "provider": order.provider,
            "amount_paise": order.amount_paise,
        },
    )
    db.commit()
    return txn


def handle_webhook_event(db: Session, event: dict[str, Any]) -> TransactionRequest | None:
    """Apply a provider webhook to the transaction it refers to.

    Written to survive the two things webhooks always do: arrive twice, and
    arrive out of order.
    """
    entity = (
        event.get("payload", {}).get("payment", {}).get("entity", {})
        if isinstance(event.get("payload"), dict)
        else {}
    )
    order_id = entity.get("order_id")
    if not order_id:
        return None

    txn = db.scalars(
        select(TransactionRequest)
        .where(TransactionRequest.payment_order_id == order_id)
        .with_for_update()
    ).first()
    if txn is None:
        return None

    succeeded = event.get("event") == "payment.captured" or entity.get("status") == "captured"
    target = TxnState.PAYMENT_SUCCESS if succeeded else TxnState.PAYMENT_FAILED

    if txn.state == target:
        audit.record(
            db,
            event_type=EventType.DUPLICATE_SUPPRESSED,
            transaction_id=txn.id,
            agent_id=txn.agent_id,
            policy_id=txn.policy_id,
            explanation="Duplicate webhook for an already-settled payment; ignored.",
            previous_state=txn.state,
            new_state=txn.state,
            metadata={"order_id": order_id, "event": event.get("event")},
        )
        db.commit()
        return txn

    if txn.state != TxnState.PAYMENT_CREATED:
        # Late or out-of-order delivery for a transaction that has moved on.
        audit.record(
            db,
            event_type=EventType.DUPLICATE_SUPPRESSED,
            transaction_id=txn.id,
            agent_id=txn.agent_id,
            policy_id=txn.policy_id,
            explanation=(
                f"Webhook '{event.get('event')}' arrived while the transaction was "
                f"{txn.state}; no state change applied."
            ),
            previous_state=txn.state,
            new_state=txn.state,
            metadata={"order_id": order_id, "event": event.get("event")},
        )
        db.commit()
        return txn

    txn.payment_id = entity.get("id")
    policy = budget.lock_policy(db, txn.policy_id) if txn.policy_id else None

    if succeeded:
        if policy is not None:
            budget.settle(db, policy, txn)
        move_state(
            db, txn, TxnState.PAYMENT_SUCCESS,
            event_type=EventType.PAYMENT_SUCCEEDED,
            explanation=(
                f"Payment of {format_inr(txn.requested_amount_paise)} confirmed"
                + (f" ({txn.payment_id})." if txn.payment_id else ".")
            ),
            metadata={"order_id": order_id, "payment_id": txn.payment_id},
        )
    else:
        txn.payment_error = entity.get("error_description") or "Payment failed."
        move_state(
            db, txn, TxnState.PAYMENT_FAILED,
            event_type=EventType.PAYMENT_FAILED,
            explanation=(
                f"Authorization was successful, but the payment failed: {txn.payment_error}"
            ),
            metadata={"order_id": order_id, "payment_id": txn.payment_id},
        )
        if policy is not None:
            amount = txn.requested_amount_paise
            budget.release(db, policy, txn)
            audit.record(
                db,
                event_type=EventType.BUDGET_RELEASED,
                transaction_id=txn.id,
                agent_id=txn.agent_id,
                policy_id=policy.id,
                explanation=(
                    f"Released {format_inr(amount)} after the payment failed. "
                    f"{format_inr(policy.remaining_budget_paise)} now available."
                ),
                metadata={"released_paise": amount},
            )

    db.commit()
    return txn
