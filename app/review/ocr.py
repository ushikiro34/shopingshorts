"""리뷰 스크린샷에서 텍스트를 추출한다 — Claude의 이미지 인식(vision)을 사용한다.

쿠팡 크롤링과 무관하다 — 사용자가 직접 캡처해 업로드한 이미지 파일을 읽을 뿐이다.
"""

from __future__ import annotations

import base64
import io
import time

import anthropic
from PIL import Image

from app.config import ANTHROPIC_API_KEY

MODEL = "claude-sonnet-4-5"

# 작은 스크린샷(특히 좁은 배너형 캡처)은 실제 사용해보니 글자 오독이 잦았다 — 짧은 변이
# 이 값보다 작으면 확대해서 보낸다. 실측: 세로 40px 리뷰 캡처에서 여러 단어를 잘못 읽던
# 문제가, 확대 후엔 거의 완벽하게 교정됐다(체감상 vision 모델이 작은 글자를 실제로 읽기보다
# 비슷한 모양으로 추측해버리는 것으로 보임).
OCR_MIN_DIMENSION_PX = 800
OCR_MAX_UPSCALE = 4

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


def _maybe_upscale(image_bytes: bytes, media_type: str) -> tuple[bytes, str]:
    """짧은 변이 OCR_MIN_DIMENSION_PX보다 작은 이미지를 확대해서 돌려준다.

    이미지를 열 수 없으면(지원 안 하는 포맷 등) 원본을 그대로 돌려주고 Claude에게 맡긴다.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception:
        return image_bytes, media_type

    shorter_side = min(image.width, image.height)
    if shorter_side == 0 or shorter_side >= OCR_MIN_DIMENSION_PX:
        return image_bytes, media_type

    scale = min(OCR_MIN_DIMENSION_PX / shorter_side, OCR_MAX_UPSCALE)
    new_size = (round(image.width * scale), round(image.height * scale))
    upscaled = image.convert("RGB").resize(new_size, Image.LANCZOS)
    buf = io.BytesIO()
    upscaled.save(buf, "PNG")
    return buf.getvalue(), "image/png"


def extract_review_text(
    image_bytes: bytes, media_type: str, client: anthropic.Anthropic | None = None
) -> str:
    active_client = client or _client()
    image_bytes, media_type = _maybe_upscale(image_bytes, media_type)
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
