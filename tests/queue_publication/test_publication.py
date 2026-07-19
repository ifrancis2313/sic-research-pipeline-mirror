from qepm.contracts import QueuePublication
from qepm.queue_publication import validate_queue_publication


def test_pm_can_reorder_suppress_and_add_briefs_with_audit_rationale():
    publication = QueuePublication(
        proposed_factors=("quality", "value"),
        published_factors=("momentum", "quality"),
        rationale="Momentum is time-sensitive; Value brief is covered by an active campaign.",
    )

    validate_queue_publication(publication)
