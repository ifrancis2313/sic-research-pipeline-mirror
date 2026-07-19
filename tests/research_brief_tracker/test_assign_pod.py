from datetime import date

import pytest

from qepm.exposure_optimizer import generate_exposure_targets
from qepm.research_brief_tracker import assign_pod, create_brief


def _any_brief(snapshot, scores, holdings):
    target = generate_exposure_targets(snapshot, scores, holdings)[0]
    return create_brief(target)


def test_assign_pod_records_exactly_the_pod_given_no_inference(snapshot, scores, holdings):
    brief = _any_brief(snapshot, scores, holdings)

    assign_pod(brief, "Pod A", claimed_on=date(2026, 7, 17))

    assert brief.assigned_pods == ["Pod A"]
    assert brief.claimed_on == date(2026, 7, 17)


def test_same_brief_can_be_assigned_to_more_than_one_pod(snapshot, scores, holdings):
    brief = _any_brief(snapshot, scores, holdings)
    brief.pod_capacity = 2

    assign_pod(brief, "Pod A", claimed_on=date(2026, 7, 17))
    assign_pod(brief, "Pod B", claimed_on=date(2026, 7, 18))

    assert brief.assigned_pods == ["Pod A", "Pod B"]
    assert brief.claimed_on == date(2026, 7, 17)


def test_pod_assignment_cannot_exceed_the_briefs_configured_capacity(snapshot, scores, holdings):
    brief = _any_brief(snapshot, scores, holdings)
    brief.pod_capacity = 1
    assign_pod(brief, "Pod A", claimed_on=date(2026, 7, 17))

    with pytest.raises(ValueError, match="capacity"):
        assign_pod(brief, "Pod B", claimed_on=date(2026, 7, 17))


def test_assigning_the_same_pod_twice_does_not_duplicate(snapshot, scores, holdings):
    brief = _any_brief(snapshot, scores, holdings)

    assign_pod(brief, "Pod A", claimed_on=date(2026, 7, 17))
    assign_pod(brief, "Pod A", claimed_on=date(2026, 7, 18))

    assert brief.assigned_pods == ["Pod A"]
