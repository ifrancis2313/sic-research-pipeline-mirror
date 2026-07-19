from datetime import date

import pytest

from qepm.contracts import HoldingOwnership
from qepm.holding_ownership import ownership_refresh_due, validate_holding_ownership


def test_inherited_active_holding_needs_legacy_review_before_owner_record_is_complete():
    record = HoldingOwnership("FIGI", "Pod A", "active", date(2026, 7, 17), inherited=True)
    with pytest.raises(ValueError, match="legacy review"):
        validate_holding_ownership(record)


def test_ownership_refresh_flags_unrecorded_earnings_and_overdue_quarterly_review():
    record = HoldingOwnership("FIGI", "Pod A", "active", date(2026, 1, 1), last_quarterly_review=date(2026, 4, 1))

    assert ownership_refresh_due(record, date(2026, 7, 17)) == ("earnings-review-unrecorded", "quarterly-review-due")
