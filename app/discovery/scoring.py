"""1호 직원 — 상품 스코어링.

docs/00_project_overview.md의 배점표를 구현한다.
합계 100점, 항목별 상한을 넘지 않도록 각 score_* 함수가 자체적으로 clamp한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import IMPULSE_PRICE_THRESHOLD

MAX_REVIEW_COUNT_SCORE = 20
MAX_REVIEW_GROWTH_SCORE = 20
MAX_PRICE_SCORE = 10
MAX_IMPULSE_SCORE = 15
MAX_SEASONALITY_SCORE = 10
MAX_CONTENT_FIT_SCORE = 15
MAX_STORY_SCORE = 10
MAX_TOTAL_SCORE = 100


def score_review_count(review_count: int | None) -> int:
    """리뷰 개수 — 신뢰도 지표 (최대 20점)."""
    if not review_count or review_count <= 0:
        return 0
    if review_count >= 1000:
        return 20
    if review_count >= 500:
        return 16
    if review_count >= 200:
        return 12
    if review_count >= 50:
        return 8
    if review_count >= 10:
        return 4
    return 0


def score_review_growth(reviews_last_30d: int, review_count: int | None) -> int:
    """최근 리뷰 증가속도 — 트렌드성 (최대 20점).

    최근 30일 리뷰 수가 전체 리뷰 수에서 차지하는 비율로 판단한다.
    """
    if not review_count or review_count <= 0 or reviews_last_30d <= 0:
        return 0
    ratio = reviews_last_30d / review_count
    if ratio >= 0.3:
        return 20
    if ratio >= 0.15:
        return 15
    if ratio >= 0.05:
        return 10
    return 5


def score_price(price: int | None) -> int:
    """가격 — 충동구매 임계값 이하일수록 가점 (최대 10점)."""
    if price is None or price < 0:
        return 0
    if price <= 10000:
        return 10
    if price <= 20000:
        return 8
    if price <= IMPULSE_PRICE_THRESHOLD:
        return 5
    if price <= 50000:
        return 2
    return 0


def score_impulse(price: int | None, is_consumable: bool) -> int:
    """충동구매 가능성 — 생활 밀착 소모품 여부 (최대 15점)."""
    score = 0
    if price is not None and 0 <= price <= IMPULSE_PRICE_THRESHOLD:
        score += 8
    if is_consumable:
        score += 7
    return min(score, MAX_IMPULSE_SCORE)


def score_seasonality(is_in_season: bool, is_evergreen: bool = False) -> int:
    """계절성 매칭 — 현재 시즌 적합도 (최대 10점)."""
    if is_in_season:
        return MAX_SEASONALITY_SCORE
    if is_evergreen:
        return 5
    return 0


def score_content_fit(content_fit_manual: int) -> int:
    """쇼츠 소재 적합성 — 시각적으로 보여줄 거리가 있는가 (최대 15점, 사람 1차 입력값을 clamp)."""
    return max(0, min(content_fit_manual, MAX_CONTENT_FIT_SCORE))


def score_story(emotional_keyword_count: int) -> int:
    """공감 스토리 가능성 — 리뷰 분석의 emotional_keywords 개수 기반 (최대 10점).

    리뷰 입력 전에는 0점, 리뷰 입력(분석) 후 재계산된다.
    """
    if emotional_keyword_count >= 5:
        return 10
    if emotional_keyword_count >= 3:
        return 7
    if emotional_keyword_count >= 1:
        return 3
    return 0


@dataclass
class ScoreInputs:
    review_count: int | None = None
    reviews_last_30d: int = 0
    price: int | None = None
    is_consumable: bool = False
    is_in_season: bool = False
    is_evergreen: bool = False
    content_fit_manual: int = 0
    emotional_keyword_count: int = 0


@dataclass
class ScoreBreakdown:
    review_count_score: int
    review_growth_score: int
    price_score: int
    impulse_score: int
    seasonality_score: int
    content_fit_score: int
    story_score: int

    @property
    def total_score(self) -> int:
        total = (
            self.review_count_score
            + self.review_growth_score
            + self.price_score
            + self.impulse_score
            + self.seasonality_score
            + self.content_fit_score
            + self.story_score
        )
        return min(total, MAX_TOTAL_SCORE)

    def as_dict(self) -> dict:
        return {
            "review_growth_score": self.review_growth_score,
            "price_score": self.price_score,
            "impulse_score": self.impulse_score,
            "seasonality_score": self.seasonality_score,
            "content_fit_score": self.content_fit_score,
            "story_score": self.story_score,
            "total_score": self.total_score,
        }


def calculate_score(inputs: ScoreInputs) -> ScoreBreakdown:
    return ScoreBreakdown(
        review_count_score=score_review_count(inputs.review_count),
        review_growth_score=score_review_growth(inputs.reviews_last_30d, inputs.review_count),
        price_score=score_price(inputs.price),
        impulse_score=score_impulse(inputs.price, inputs.is_consumable),
        seasonality_score=score_seasonality(inputs.is_in_season, inputs.is_evergreen),
        content_fit_score=score_content_fit(inputs.content_fit_manual),
        story_score=score_story(inputs.emotional_keyword_count),
    )
