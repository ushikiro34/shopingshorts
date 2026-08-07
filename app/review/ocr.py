"""리뷰 스크린샷에서 텍스트를 추출한다 — Claude의 이미지 인식(vision)을 사용한다.

쿠팡 크롤링과 무관하다 — 사용자가 직접 캡처해 업로드한 이미지 파일을 읽을 뿐이다.
"""

from __future__ import annotations

import base64
import io
import time

import anthropic
from PIL import Image, ImageFilter

from app.config import ANTHROPIC_API_KEY

MODEL = "claude-sonnet-4-5"

# 작은 스크린샷(특히 좁은 배너형 캡처)은 실제 사용해보니 글자 오독이 잦았다 — 짧은 변이
# 이 값보다 작으면 확대해서 보낸다. 실측: 세로 40px 리뷰 캡처에서 여러 단어를 잘못 읽던
# 문제가, 확대 후엔 거의 완벽하게 교정됐다(체감상 vision 모델이 작은 글자를 실제로 읽기보다
# 비슷한 모양으로 추측해버리는 것으로 보임).
OCR_MIN_DIMENSION_PX = 800
OCR_MAX_UPSCALE = 4

# 확대해도 여전히 인식률이 낮다는 피드백(사용자) — 캡처 특유의 리사이즈/압축 흐림은
# 크기와 무관하게 발생하므로, 이미 충분히 큰 이미지에도 약한 선명화(unsharp mask)를
# 항상 적용한다. radius/percent는 자글자글한 노이즈를 만들지 않는 선에서 보수적으로 잡았다.
OCR_SHARPEN_RADIUS = 1.5
OCR_SHARPEN_PERCENT = 60
OCR_SHARPEN_THRESHOLD = 2

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


def _preprocess_for_ocr(image_bytes: bytes, media_type: str) -> tuple[bytes, str]:
    """OCR 정확도를 높이기 위해 확대 + 선명화를 적용한다.

    짧은 변이 작으면 OCR_MIN_DIMENSION_PX까지 확대하고, 크기와 무관하게 약한 선명화를
    항상 적용한다(화면 캡처 특유의 리사이즈/압축 흐림은 이미 큰 이미지에도 있을 수 있다).
    이미지를 열 수 없으면(지원 안 하는 포맷 등) 원본을 그대로 돌려주고 Claude에게 맡긴다.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception:
        return image_bytes, media_type

    image = image.convert("RGB")
    shorter_side = min(image.width, image.height)
    if 0 < shorter_side < OCR_MIN_DIMENSION_PX:
        scale = min(OCR_MIN_DIMENSION_PX / shorter_side, OCR_MAX_UPSCALE)
        new_size = (round(image.width * scale), round(image.height * scale))
        image = image.resize(new_size, Image.LANCZOS)

    image = image.filter(
        ImageFilter.UnsharpMask(radius=OCR_SHARPEN_RADIUS, percent=OCR_SHARPEN_PERCENT, threshold=OCR_SHARPEN_THRESHOLD)
    )

    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue(), "image/png"


def extract_review_text(
    image_bytes: bytes, media_type: str, client: anthropic.Anthropic | None = None
) -> str:
    active_client = client or _client()
    image_bytes, media_type = _preprocess_for_ocr(image_bytes, media_type)
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    last_error: Exception | None = None
    for attempt in range(2):  # 최초 시도 + 재시도 1회 (AGENTS.md 코딩 컨벤션)
        try:
            # 길고 상세한 리뷰(섹션 제목, 이모지, 여러 문단)는 예전 2048 한도에서 중간에
            # 잘릴 수 있었다 — 사용자가 "인식 실패"라 보고한 리뷰가 실제로는 텍스트 자체는
            # 또렷했고 분량만 많았던 사례가 있어 여유 있게 올렸다.
            message = active_client.messages.create(
                model=MODEL,
                max_tokens=4096,
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
