"""Transaction lifecycle.

The whole point of this module is one invariant:

    A BLOCKED transaction can never become PAYMENT_SUCCESS.

BLOCKED, REJECTED and EXPIRED have no outgoing edges at all, so there is no
path -- accidental, concurrent, or malicious -- from a refusal to a payment.
Every state change in the system goes through transition(), and anything
illegal raises rather than silently doing nothing.
"""

from app.models import TERMINAL_STATES, TxnState

#: state -> the states it may legally move to.
ALLOWED: dict[TxnState, set[TxnState]] = {
    TxnState.CREATED: {TxnState.EVALUATING},
    TxnState.EVALUATING: {
        TxnState.BLOCKED,
        TxnState.PENDING_APPROVAL,
        TxnState.APPROVED,
    },
    TxnState.PENDING_APPROVAL: {
        TxnState.APPROVED,
        TxnState.REJECTED,
        TxnState.EXPIRED,
    },
    TxnState.APPROVED: {
        TxnState.PAYMENT_CREATED,
        TxnState.PAYMENT_CREATION_FAILED,
    },
    # A provider outage is not the user's fault: creating the order may be
    # retried. Authorization is not re-litigated, because it already passed.
    TxnState.PAYMENT_CREATION_FAILED: {
        TxnState.PAYMENT_CREATED,
    },
    TxnState.PAYMENT_CREATED: {
        TxnState.PAYMENT_SUCCESS,
        TxnState.PAYMENT_FAILED,
    },
    # Terminal.
    TxnState.BLOCKED: set(),
    TxnState.REJECTED: set(),
    TxnState.EXPIRED: set(),
    TxnState.PAYMENT_SUCCESS: set(),
    TxnState.PAYMENT_FAILED: set(),
}

#: States from which a payment may be created. Deliberately a separate,
#: explicit set rather than "not blocked" -- an allowlist fails closed.
PAYABLE_STATES = {TxnState.APPROVED, TxnState.PAYMENT_CREATION_FAILED}

#: States that mean "this cleared authorization at some point", whether the
#: gate approved it outright or a human did. Reporting counts these, because
#: a user who approved a purchase considers it approved -- transaction.decision
#: still records which of the two routes it took.
AUTHORIZED_STATES = {
    TxnState.APPROVED,
    TxnState.PAYMENT_CREATED,
    TxnState.PAYMENT_CREATION_FAILED,
    TxnState.PAYMENT_SUCCESS,
    TxnState.PAYMENT_FAILED,
}


class IllegalTransition(Exception):
    """Raised when code attempts a state change the lifecycle forbids."""

    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Cannot move transaction from {current} to {target}.")


def can_transition(current: str, target: str) -> bool:
    try:
        return TxnState(target) in ALLOWED[TxnState(current)]
    except (KeyError, ValueError):
        return False


def assert_transition(current: str, target: str) -> None:
    if not can_transition(current, target):
        raise IllegalTransition(current, target)


def is_terminal(state: str) -> bool:
    try:
        return TxnState(state) in TERMINAL_STATES
    except ValueError:
        return False


def is_payable(state: str) -> bool:
    try:
        return TxnState(state) in PAYABLE_STATES
    except ValueError:
        return False
