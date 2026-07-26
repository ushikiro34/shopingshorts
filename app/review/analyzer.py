"""2호 직원 — AI 후기 분석.

reviews_raw(리뷰 원문)를 감정/불만/칭찬으로 재구성한다. AGENTS.md 절대 규칙 2에 따라
원문을 그대로 옮기지 않고 요약·범주화한 JSON만 반환한다 (docs/03_interfaces.md 3번 스키마).
"""

from __future__ import annotations

import json
import time

import anthropic

from app.config import ANTHROPIC_API_KEY
from app.llm_utils import parse_json_response

MODEL = "claude-sonnet-4-5"

REQUIRED_ANALYSIS_FIELDS = [
    "positives",
    "complaints",
    "surprises",
    "repurchase_reasons",
    "emotional_keywords",
    "target_segments",
    "suggested_hook_angle",
]

SYSTEM_PROMPT = """너는 쿠팡 상품 후기를 분석하는 AI 직원이다.
사용자가 붙여넣은 리뷰 원문 여러 개를 읽고, 아래 JSON 스키마로만 응답한다.

규칙:
- 리뷰 문장을 그대로 옮기지 말고 반드시 요약·재구성한다 (원문 재배포 금지).
- 각 배열 필드는 리뷰 전반에서 반복되는 패턴을 2~5개씩 뽑는다.
- emotional_keywords는 리뷰에 반복적으로 나타나는 감정 표현 단어/짧은 구를 뽑는다.
- suggested_hook_angle은 대본 훅 문장을 만들 때 쓸 한 문장짜리 소재다.
- 어떤 필드에도 "2만원", "3만원대"처럼 구체적 가격 숫자를 넣지 않는다 (가격은 변동될 수
  있어 대본에서 절대 언급하지 않는 규칙이 있다 — 이 분석 결과가 그대로 대본 소재로 쓰이므로,
  가격 비교가 리뷰의 핵심이더라도 "저가 제품", "가성비 좋은 제품"처럼 숫자 없이 표현한다).
- 다른 설명 없이 JSON 객체 하나만 출력한다.

스키마:
{
  "positives": ["..."],
  "complaints": ["..."],
  "surprises": ["..."],
  "repurchase_reasons": ["..."],
  "emotional_keywords": ["..."],
  "target_segments": ["..."],
  "suggested_hook_angle": "..."
}"""


class ReviewAnalysisError(RuntimeError):
    """분석 실패(파싱 실패, API 오류 포함)를 감싸는 명확한 예외."""


def _client() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise ReviewAnalysisError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _validate_shape(data: dict) -> None:
    missing = [field for field in REQUIRED_ANALYSIS_FIELDS if field not in data]
    if missing:
        raise ReviewAnalysisError(f"분석 결과에 필드 누락: {missing}")


def analyze_reviews(reviews_raw: str, client: anthropic.Anthropic | None = None) -> dict:
    active_client = client or _client()

    last_error: Exception | None = None
    for attempt in range(2):  # 최초 시도 + 재시도 1회 (AGENTS.md 코딩 컨벤션)
        try:
            message = active_client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": reviews_raw}],
            )
            text = message.content[0].text
            data = parse_json_response(text)
            _validate_shape(data)
            return data
        except (json.JSONDecodeError, ReviewAnalysisError, anthropic.APIError) as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.5)
                continue

    raise ReviewAnalysisError(f"후기 분석 실패: {last_error}") from last_error
