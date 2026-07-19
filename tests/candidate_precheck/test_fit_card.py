from qepm.candidate_precheck import create_candidate_fit_card
from qepm.contracts import CompetingPitch, DimensionSpec, Direction, ExposureTarget, PortfolioPolicy
from qepm.research_brief_tracker import create_brief


def test_candidate_precheck_is_advisory_and_does_not_reserve_capacity(snapshot, scores, holdings):
    target = ExposureTarget(
        id="CAP", direction=Direction.BUY, dollar_amount=50_000,
        dimension=DimensionSpec(factor="momentum"), rationale="test",
    )
    brief = create_brief(target)
    pitch = CompetingPitch("P", brief.id, "Pod", "BBG-FIXTURE-007", "test")

    card = create_candidate_fit_card(
        pitch, brief, holdings, scores, snapshot, snapshot.as_of, PortfolioPolicy(portfolio_nav=100_000)
    )

    assert card.research_permitted is True
    assert card.fit.passed is False
    assert brief.status == "open"
    assert card.available_name_room == 0.01
    assert card.crowding_status == "not-measured-v1"
    assert holdings.positions.loc["BBG-FIXTURE-007", "dollar_value"] == 9_000
