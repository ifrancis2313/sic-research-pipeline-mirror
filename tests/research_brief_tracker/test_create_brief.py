from qepm.contracts import Direction
from qepm.exposure_optimizer import generate_exposure_targets
from qepm.research_brief_tracker import create_brief


def _find(targets, **dimension_fields):
    return next(
        t
        for t in targets
        if all(getattr(t.dimension, field) == value for field, value in dimension_fields.items())
    )


def test_buy_side_sector_and_factor_prompt_is_readable(snapshot, scores, holdings):
    targets = generate_exposure_targets(snapshot, scores, holdings)
    target = _find(targets, sector="Energy", factor="momentum")

    brief = create_brief(target)

    assert brief.id == f"RB-{target.id}"
    assert brief.status == "open"
    assert "Find a buy candidate" in brief.prompt
    assert "$21,882" in brief.prompt
    assert "sector=Energy" in brief.prompt
    assert "factor=momentum" in brief.prompt
    assert target.rationale in brief.prompt


def test_buy_side_sector_alone_prompt_names_only_the_sector(snapshot, scores, holdings):
    targets = generate_exposure_targets(snapshot, scores, holdings)
    target = _find(targets, sector="Energy", factor=None, screen=None)

    brief = create_brief(target)

    assert "sector=Energy" in brief.prompt
    assert "factor=" not in brief.prompt
    assert "screen=" not in brief.prompt


def test_buy_side_sector_and_screen_prompt_names_the_screen(snapshot, scores, holdings):
    targets = generate_exposure_targets(snapshot, scores, holdings)
    target = next(t for t in targets if t.dimension.screen is not None)

    brief = create_brief(target)

    assert "Find a buy candidate" in brief.prompt
    assert "screen=" in brief.prompt
    assert target.dimension.screen in brief.prompt


def test_sell_side_prompt_surfaces_the_specific_holdings_to_choose_among(snapshot, scores, holdings):
    targets = generate_exposure_targets(snapshot, scores, holdings)
    target = _find(targets, sector="Industrials", factor="momentum")
    assert target.direction is Direction.SELL
    assert target.source_bucket  # sanity: this scenario actually has a bucket to surface

    brief = create_brief(target)

    assert "Pick a holding to trim" in brief.prompt
    for figi in target.source_bucket:
        assert figi in brief.prompt


def test_pm_can_publish_a_brief_in_a_non_active_sleeve(snapshot, scores, holdings):
    target = _find(generate_exposure_targets(snapshot, scores, holdings), sector="Industrials", factor="momentum")

    assert create_brief(target, sleeve="core").target.sleeve == "core"
    assert create_brief(target, sleeve="experimental").target.sleeve == "experimental"
