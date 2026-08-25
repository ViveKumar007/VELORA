"""Lifecycle tests.

The first test in this file is the one that matters most in the whole
project: a refused transaction must have no route to a successful payment.
"""

import pytest

from app.models import TERMINAL_STATES, TxnState
from app.services.state_machine import (
    ALLOWED,
    IllegalTransition,
    assert_transition,
    can_transition,
    is_payable,
    is_terminal,
)


def reachable_from(start: TxnState) -> set[TxnState]:
    """Every state reachable from `start` by any number of legal moves."""
    seen: set[TxnState] = set()
    frontier = [start]
    while frontier:
        current = frontier.pop()
        for nxt in ALLOWED[current]:
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return seen


def test_blocked_can_never_reach_payment_success():
    """The core invariant of the product."""
    assert reachable_from(TxnState.BLOCKED) == set()
    assert TxnState.PAYMENT_SUCCESS not in reachable_from(TxnState.BLOCKED)


@pytest.mark.parametrize("state", [TxnState.BLOCKED, TxnState.REJECTED, TxnState.EXPIRED])
def test_refusals_are_dead_ends(state):
    assert ALLOWED[state] == set()
    assert is_terminal(state)
    assert not is_payable(state)


def test_only_approved_states_can_pay():
    payable = {s for s in TxnState if is_payable(s)}
    assert payable == {TxnState.APPROVED, TxnState.PAYMENT_CREATION_FAILED}


def test_payment_requires_passing_through_approval():
    """There is no edge into PAYMENT_CREATED except from an approved state."""
    sources = {s for s, targets in ALLOWED.items() if TxnState.PAYMENT_CREATED in targets}
    assert sources == {TxnState.APPROVED, TxnState.PAYMENT_CREATION_FAILED}


def test_escalation_paths():
    assert can_transition(TxnState.PENDING_APPROVAL, TxnState.APPROVED)
    assert can_transition(TxnState.PENDING_APPROVAL, TxnState.REJECTED)
    assert can_transition(TxnState.PENDING_APPROVAL, TxnState.EXPIRED)
    # A pending item cannot skip the human and pay directly.
    assert not can_transition(TxnState.PENDING_APPROVAL, TxnState.PAYMENT_CREATED)


def test_provider_outage_is_retryable_but_does_not_re_open_authorization():
    assert can_transition(TxnState.PAYMENT_CREATION_FAILED, TxnState.PAYMENT_CREATED)
    assert not can_transition(TxnState.PAYMENT_CREATION_FAILED, TxnState.APPROVED)


def test_illegal_transition_raises_rather_than_no_ops():
    with pytest.raises(IllegalTransition):
        assert_transition(TxnState.BLOCKED, TxnState.PAYMENT_SUCCESS)
    with pytest.raises(IllegalTransition):
        assert_transition(TxnState.CREATED, TxnState.APPROVED)


def test_every_state_is_covered_by_the_table():
    assert set(ALLOWED) == set(TxnState)


def test_terminal_set_matches_the_transition_table():
    computed = {s for s, targets in ALLOWED.items() if not targets}
    assert computed == TERMINAL_STATES


def test_unknown_states_fail_closed():
    assert not can_transition("NONSENSE", TxnState.PAYMENT_SUCCESS)
    assert not is_payable("NONSENSE")
