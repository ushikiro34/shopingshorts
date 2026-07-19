"""리뷰 스크린샷에서 텍스트를 추출한다 — Claude의 이미지 인식(vision)을 사용한다.

쿠팡 크롤링과 무관하다 — 사용자가 직접 캡처해 업로드한 이미지 파일을 읽을 뿐이다.
"""

from __future__ import annotations

import base64
import time

import anthropic

from app.config import ANTHROPIC_API_KEY

MODEL = "claude-sonnet-4-5"

SYSTEM_PROMPT = """너는 상품 후기 스크린샷에서 텍스트를 추출하는 AI 직원이다.
이미지 안에 보이는 리뷰 본문 텍스트를 있는 그대로 옮겨 적어라 (요약하거나 각색하지 않는다).
여러 리뷰가 보이면 리뷰별로 줄바꿈해서 전부 옮겨 적는다.
별점, 작성일, 작성자 닉네임 같은 부가 정보는 제외하고 리뷰 본문 텍스트만 추출한다.
다른 설명 없이 추출한 텍스트만 출력한다. 리뷰 텍스트가 보이지 않으면 빈 문자열만 출력한다."""


class ReviewOcrError(RuntimeError):
    """스크린샷 텍스트 추출 실패(인증 오류 포함)를 감싸는 명확한 예외."""


def _client() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise ReviewOcrError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def extract_review_text(
    image_bytes: bytes, media_type: str, client: anthropic.Anthropic | None = None
) -> str:
    active_client = client or _client()
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    last_error: Exception | None = None
    for attempt in range(2):  # 최초 시도 + 재시도 1회 (AGENTS.md 코딩 컨벤션)
        try:
            message = active_client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {"type": "base64", "media_type": media_type, "data": b64},
                            },
                            {"type": "text", "text": "이 스크린샷에서 리뷰 텍스트를 추출해줘."},
                        ],
                    }
                ],
            )
            return message.content[0].text.strip()
        except anthropic.APIError as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.5)
                continue

    raise ReviewOcrError(f"스크린샷 텍스트 추출 실패: {last_error}") from last_error
