"""1호 직원 — 상품 스코어링.

docs/00_project_overview.md의 배점표를 구현한다.
합계 40점, 항목별 상한을 넘지 않도록 각 score_* 함수가 자체적으로 clamp한다.

v2.5부터 리뷰수/가격/스토리 3개 항목만 남긴다 — 증가속도/충동구매/계절성/소재적합은
쿠팡 파트너스 API도, 대시보드 UI도 실제 값을 채워 넣는 경로가 하나도 없어(항상 0점
고정) 사실상 죽은 배점이었다(사용자 피드백으로 확인 후 정리).
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_REVIEW_COUNT_SCORE = 20
MAX_PRICE_SCORE = 10
MAX_STORY_SCORE = 10
MAX_TOTAL_SCORE = 40

# 가격이 낮을수록(=충동구매하기 쉬울수록) 가점 — 예전 "충동구매" 항목이 쓰던 임계값을
# 그대로 가져왔다(그 항목 자체는 삭제됐지만, 가격 배점 구간 기준으로는 여전히 유효).
PRICE_LOW_THRESHOLD = 30000


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


def score_price(price: int | None) -> int:
    """가격 — 낮을수록 가점 (최대 10점)."""
    if price is None or price < 0:
        return 0
    if price <= 10000:
        return 10
    if price <= 20000:
        return 8
    if price <= PRICE_LOW_THRESHOLD:
        return 5
    if price <= 50000:
        return 2
    return 0


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
    price: int | None = None
    emotional_keyword_count: int = 0


@dataclass
class ScoreBreakdown:
    review_count_score: int
    price_score: int
    story_score: int

    @property
    def total_score(self) -> int:
        total = self.review_count_score + self.price_score + self.story_score
        return min(total, MAX_TOTAL_SCORE)

    def as_dict(self) -> dict:
        return {
            "price_score": self.price_score,
            "story_score": self.story_score,
            "total_score": self.total_score,
        }


def calculate_score(inputs: ScoreInputs) -> ScoreBreakdown:
    return ScoreBreakdown(
        review_count_score=score_review_count(inputs.review_count),
        price_score=score_price(inputs.price),
        story_score=score_story(inputs.emotional_keyword_count),
    )
