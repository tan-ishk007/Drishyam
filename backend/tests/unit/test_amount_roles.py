"""A figure is not a transaction just because it is money.

"Your investment balance of INR 29,500" and "Paid to Release Desk 12,000" are both amounts. Only
one of them is money that moved. Projecting every amount into the transaction trail put a balance
quoted in an email beside real payments and added it into the case total, asserting a transfer the
evidence never recorded.
"""

from __future__ import annotations

from app.evidence_intelligence import patterns
from app.evidence_intelligence.schema import AmountRole
from app.services.grounded_projection import _is_transactional


class FakeRecord:
    def __init__(self, role: str | None):
        self.amount_role = role


def _role(text: str, quote: str) -> str:
    return patterns.classify_amount_role(text, quote)


def test_a_balance_is_recognised_as_a_position():
    assert _role("Your balance is now INR 29,500. You can withdraw today.", "INR 29,500") == "balance"
    assert _role("Your investment balance of INR 29,500 is ready for withdrawal", "INR 29,500") == "balance"
    assert _role("Available bal: INR 4,200", "INR 4,200") == "balance"


def test_money_that_moved_is_recognised_as_a_payment():
    assert _role("Paid to Release Desk INR 12,000", "INR 12,000") == "payment"
    assert _role("INR 5,000 debited from your account", "INR 5,000") == "payment"


def test_a_demand_is_a_request_not_a_completed_payment():
    assert _role("Send INR 25,000 to invest.demo@upi.", "INR 25,000") == "request"
    assert _role("Compliance requires an additional INR 18,000", "INR 18,000") == "request"
    assert _role("Pay a refundable release fee of INR 12,000", "INR 12,000") == "fee"


def test_a_figure_with_no_describing_words_stays_unknown():
    assert _role("Py Release Desk =12,000", "=12,000") == "unknown"


def test_only_the_line_carrying_the_figure_is_read():
    """A word describing a different figure elsewhere on the page must not be borrowed."""
    page = "Paid to Release Desk\nYour balance is now INR 29,500"
    assert _role(page, "INR 29,500") == "balance"


def test_a_balance_is_never_projected_as_a_transaction():
    assert _is_transactional(FakeRecord(AmountRole.BALANCE.value)) is False
    for role in (AmountRole.PAYMENT, AmountRole.REQUEST, AmountRole.FEE, AmountRole.UNKNOWN):
        assert _is_transactional(FakeRecord(role.value)) is True
    # A record written before the classification existed carries no role and keeps its old behaviour.
    assert _is_transactional(FakeRecord(None)) is True
