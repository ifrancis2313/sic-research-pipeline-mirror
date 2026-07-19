"""PM queue-publication controls preserving engine proposal and human edits."""

from __future__ import annotations

from qepm.contracts import QueuePublication

__all__ = ["validate_queue_publication"]


def validate_queue_publication(publication: QueuePublication) -> None:
    """Allow PM reordering, suppression, and additions with an explicit audit rationale."""
    if len(publication.published_factors) > 5:
        raise ValueError("the published research queue may contain at most five briefs")
    if len(set(publication.published_factors)) != len(publication.published_factors):
        raise ValueError("the published research queue cannot contain duplicate briefs")
    if not publication.rationale.strip():
        raise ValueError("queue publication requires a rationale for PM edits")
