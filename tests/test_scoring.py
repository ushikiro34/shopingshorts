from app.discovery.scoring import (
    MAX_CONTENT_FIT_SCORE,
    MAX_IMPULSE_SCORE,
    MAX_PRICE_SCORE,
    MAX_REVIEW_COUNT_SCORE,
    MAX_REVIEW_GROWTH_SCORE,
    MAX_SEASONALITY_SCORE,
    MAX_STORY_SCORE,
    MAX_TOTAL_SCORE,
    ScoreInputs,
    calculate_score,
    score_content_fit,
    score_impulse,
    score_price,
    score_review_count,
    score_review_growth,
    score_seasonality,
    score_story,
)


def test_review_count_score_never_exceeds_max():
    assert score_review_count(None) == 0
    assert score_review_count(0) == 0
    assert score_review_count(9) < MAX_REVIEW_COUNT_SCORE
    assert score_review_count(1_000_000) == MAX_REVIEW_COUNT_SCORE


def test_review_growth_score_bounds():
    assert score_review_growth(0, 100) == 0
    assert score_review_growth(50, 100) == MAX_REVIEW_GROWTH_SCORE
    assert score_review_growth(10, 0) == 0  # review_count 0이면 분모 오류 방지


def test_price_score_bounds():
    assert score_price(None) == 0
    assert score_price(-100) == 0
    assert score_price(5_000) == MAX_PRICE_SCORE
    assert score_price(1_000_000) == 0


def test_impulse_score_never_exceeds_max():
    assert score_impulse(5_000, True) <= MAX_IMPULSE_SCORE
    assert score_impulse(5_000, True) == MAX_IMPULSE_SCORE
    assert score_impulse(None, False) == 0


def test_seasonality_score_bounds():
    assert score_seasonality(True) == MAX_SEASONALITY_SCORE
    assert score_seasonality(False, is_evergreen=True) == 5
    assert score_seasonality(False, is_evergreen=False) == 0


def test_content_fit_score_clamped():
    assert score_content_fit(-5) == 0
    assert score_content_fit(999) == MAX_CONTENT_FIT_SCORE
    assert score_content_fit(7) == 7


def test_story_score_zero_before_reviews():
    assert score_story(0) == 0
    assert score_story(5) == MAX_STORY_SCORE


def test_total_score_never_exceeds_100():
    # 모든 항목을 최대치로 밀어붙여도 100을 넘지 않는지 확인 (checklist 4번)
    inputs = ScoreInputs(
        review_count=10_000,
        reviews_last_30d=5_000,
        price=1_000,
        is_consumable=True,
        is_in_season=True,
        is_evergreen=True,
        content_fit_manual=999,
        emotional_keyword_count=999,
    )
    breakdown = calculate_score(inputs)
    assert breakdown.total_score <= MAX_TOTAL_SCORE
    assert breakdown.total_score == MAX_TOTAL_SCORE


def test_total_score_zero_when_no_data():
    breakdown = calculate_score(ScoreInputs())
    assert breakdown.total_score == 0


def test_score_breakdown_component_ranges():
    inputs = ScoreInputs(
        review_count=800,
        reviews_last_30d=200,
        price=15_000,
        is_consumable=True,
        is_in_season=False,
        is_evergreen=True,
        content_fit_manual=12,
        emotional_keyword_count=4,
    )
    breakdown = calculate_score(inputs)
    assert 0 <= breakdown.review_growth_score <= MAX_REVIEW_GROWTH_SCORE
    assert 0 <= breakdown.price_score <= MAX_PRICE_SCORE
    assert 0 <= breakdown.impulse_score <= MAX_IMPULSE_SCORE
    assert 0 <= breakdown.seasonality_score <= MAX_SEASONALITY_SCORE
    assert 0 <= breakdown.content_fit_score <= MAX_CONTENT_FIT_SCORE
    assert 0 <= breakdown.story_score <= MAX_STORY_SCORE
    assert breakdown.total_score <= MAX_TOTAL_SCORE
