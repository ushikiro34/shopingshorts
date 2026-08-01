"""4호 직원 — 상품 이미지 가공 (Phase 3).

docs/phase3_spec.md의 C안: products.image_urls(파트너스 API 실사진)를 그대로 쓰고,
AI로 재생성하지 않는다. 1080x1920 캔버스에 블러 확대 배경 + 원본 이미지를 배치하고,
자막이 들어갈 안전영역을 비워둔다.
"""

from __future__ import annotations

import time
from io import BytesIO

import httpx
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920
CANVAS_SIZE = (CANVAS_WIDTH, CANVAS_HEIGHT)

# 상품 이미지가 프레임을 꽉 채우게 하는 안전영역 비율. 자막은 반투명 박스로 이미지 위에
# 얹히므로(겹쳐도 가독성 문제 없음) 예전처럼 0.62로 작게 잡을 필요가 없었다 — 위아래로
# 블러 여백이 크게 남아 "상품 사진에 액자를 끼운 슬라이드"처럼 보이던 문제를 해결한다.
SAFE_WIDTH_RATIO = 0.94
SAFE_HEIGHT_RATIO = 0.90

BACKGROUND_BLUR_RADIUS = 40
BACKGROUND_BRIGHTNESS = 0.7


class ImageFetchError(RuntimeError):
    """상품 이미지 다운로드 실패를 감싸는 명확한 예외."""


def guess_media_type(image_bytes: bytes) -> str:
    """매직 바이트로 이미지 포맷을 추정한다 — vision/이미지 생성 API에 media_type을 넘길 때 쓴다."""
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def download_image(url: str) -> bytes:
    if not url.startswith("http://") and not url.startswith("https://"):
        # 직접 업로드한 이미지(/renders/product_images/...) — 서버가 떠 있지 않아도
        # 워커가 같은 파일시스템에서 바로 읽을 수 있게 HTTP 왕복 없이 로컬 파일로 처리한다.
        try:
            with open(url.lstrip("/"), "rb") as f:
                return f.read()
        except OSError as exc:
            raise ImageFetchError(f"로컬 이미지 파일을 읽을 수 없습니다: {url} ({exc})") from exc

    last_error: Exception | None = None
    for attempt in range(2):  # 최초 시도 + 재시도 1회 (AGENTS.md 코딩 컨벤션)
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(url)
            if response.status_code >= 400:
                raise ImageFetchError(f"이미지 다운로드 실패 (status={response.status_code}): {url}")
            return response.content
        except (httpx.HTTPError, ImageFetchError) as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.5)
                continue
    raise ImageFetchError(f"이미지 다운로드 실패: {last_error}") from last_error


# 화면 연출 이미지를 9:16으로 명시적으로 생성하기 시작한 뒤로는(app/media/image_generator.py의
# aspectRatio 지정) 대부분 이미 이 비율에 가깝게 나온다 — 그런데도 안전영역(0.94/0.90)에 맞춰
# 다시 축소하면 불필요한 블러 여백이 남는다는 피드백이 있었다. 원본 비율이 캔버스 비율과
# 충분히 가까우면(허용 오차 이내) 축소·블러 없이 캔버스를 꽉 채우도록 크롭만 한다.
ASPECT_RATIO_TOLERANCE = 0.05


def compose_scene_image(image_bytes: bytes, canvas_size: tuple[int, int] = CANVAS_SIZE) -> Image.Image:
    """블러 확대 배경 + 원본(비율 유지) 상품 이미지를 합성한 1080x1920 캔버스를 반환한다.

    원본이 이미 캔버스 비율에 충분히 가까우면 블러 배경 없이 꽉 채워 크롭한다.
    """
    original = Image.open(BytesIO(image_bytes)).convert("RGB")

    target_ratio = canvas_size[0] / canvas_size[1]
    original_ratio = original.width / original.height
    if abs(original_ratio - target_ratio) / target_ratio <= ASPECT_RATIO_TOLERANCE:
        return ImageOps.fit(original, canvas_size, method=Image.LANCZOS)

    background = ImageOps.fit(original, canvas_size, method=Image.LANCZOS)
    background = background.filter(ImageFilter.GaussianBlur(BACKGROUND_BLUR_RADIUS))
    background = ImageEnhance.Brightness(background).enhance(BACKGROUND_BRIGHTNESS)

    canvas = background.copy()

    safe_w = int(canvas_size[0] * SAFE_WIDTH_RATIO)
    safe_h = int(canvas_size[1] * SAFE_HEIGHT_RATIO)
    fitted = ImageOps.contain(original, (safe_w, safe_h), method=Image.LANCZOS)

    x = (canvas_size[0] - fitted.width) // 2
    y = (canvas_size[1] - fitted.height) // 2
    canvas.paste(fitted, (x, y))

    return canvas


def save_jpeg(image: Image.Image, path: str, quality: int = 90) -> str:
    image.convert("RGB").save(path, "JPEG", quality=quality)
    return path
