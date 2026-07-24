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

# 자막 안전영역 — 상품 이미지를 이 비율 안쪽으로만 배치해 자막(하단)·훅 텍스트(상단)와 겹치지 않게 한다.
SAFE_WIDTH_RATIO = 0.86
SAFE_HEIGHT_RATIO = 0.62

BACKGROUND_BLUR_RADIUS = 40
BACKGROUND_BRIGHTNESS = 0.7


class ImageFetchError(RuntimeError):
    """상품 이미지 다운로드 실패를 감싸는 명확한 예외."""


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


def compose_scene_image(image_bytes: bytes, canvas_size: tuple[int, int] = CANVAS_SIZE) -> Image.Image:
    """블러 확대 배경 + 원본(비율 유지) 상품 이미지를 합성한 1080x1920 캔버스를 반환한다."""
    original = Image.open(BytesIO(image_bytes)).convert("RGB")

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
