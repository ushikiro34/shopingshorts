from app.discovery.scoring import (
    MAX_PRICE_SCORE,
    MAX_REVIEW_COUNT_SCORE,
    MAX_STORY_SCORE,
    MAX_TOTAL_SCORE,
    ScoreInputs,
    calculate_score,
    score_price,
    score_review_count,
    score_story,
)


def test_review_count_score_never_exceeds_max():
    assert score_review_count(None) == 0
    assert score_review_count(0) == 0
    assert score_review_count(9) < MAX_REVIEW_COUNT_SCORE
    assert score_review_count(1_000_000) == MAX_REVIEW_COUNT_SCORE


def test_price_score_bounds():
    assert score_price(None) == 0
    assert score_price(-100) == 0
    assert score_price(5_000) == MAX_PRICE_SCORE
    assert score_price(1_000_000) == 0


def test_story_score_zero_before_reviews():
    assert score_story(0) == 0
    assert score_story(5) == MAX_STORY_SCORE


def test_total_score_never_exceeds_max():
    # 모든 항목을 최대치로 밀어붙여도 만점(40)을 넘지 않는지 확인
    inputs = ScoreInputs(review_count=10_000, price=1_000, emotional_keyword_count=999)
    breakdown = calculate_score(inputs)
    assert breakdown.total_score <= MAX_TOTAL_SCORE
    assert breakdown.total_score == MAX_TOTAL_SCORE


def test_total_score_zero_when_no_data():
    breakdown = calculate_score(ScoreInputs())
    assert breakdown.total_score == 0


def test_score_breakdown_component_ranges():
    inputs = ScoreInputs(review_count=800, price=15_000, emotional_keyword_count=4)
    breakdown = calculate_score(inputs)
    assert 0 <= breakdown.review_count_score <= MAX_REVIEW_COUNT_SCORE
    assert 0 <= breakdown.price_score <= MAX_PRICE_SCORE
    assert 0 <= breakdown.story_score <= MAX_STORY_SCORE
    assert breakdown.total_score <= MAX_TOTAL_SCORE
