"""Phase 1 임시 휴리스틱 — 리뷰 원문에서 감정 키워드 개수를 세어 story_score 재계산에 쓴다.

정식 AI 후기 분석(2호 직원, docs/03_interfaces.md의 analysis_json.emotional_keywords)은
Phase 2 범위다. Phase 1은 리뷰 입력 직후 status 전환과 story_score 재계산이라는
"뼈대"만 갖추면 되므로, 리뷰 원문 재배포 없이(단순 키워드 카운트) 점수만 재계산한다.
"""

from __future__ import annotations

EMOTIONAL_KEYWORDS_HEURISTIC = [
    "안심", "든든", "최고", "힐링", "편해", "만족",
    "후회", "답답", "불편", "힘들", "감동", "믿음",
    "재구매", "강추",
]


def count_emotional_keywords(reviews_raw: str) -> int:
    if not reviews_raw:
        return 0
    return sum(1 for keyword in EMOTIONAL_KEYWORDS_HEURISTIC if keyword in reviews_raw)
