import io

from PIL import Image

from app.review.ocr import OCR_MAX_UPSCALE, OCR_MIN_DIMENSION_PX, _maybe_upscale


def _png_bytes(size: tuple[int, int]) -> bytes:
    img = Image.new("RGB", size, "white")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_small_image_gets_upscaled_to_min_dimension():
    # 짧은 변(300)에 필요한 배율(800/300≈2.67)이 OCR_MAX_UPSCALE(4) 이내라 목표 크기까지 커진다.
    original = _png_bytes((900, 300))
    upscaled_bytes, media_type = _maybe_upscale(original, "image/png")

    upscaled = Image.open(io.BytesIO(upscaled_bytes))
    assert media_type == "image/png"
    assert min(upscaled.width, upscaled.height) >= OCR_MIN_DIMENSION_PX - 1  # 반올림 오차 허용
    assert upscaled.width > 900


def test_large_image_passes_through_unchanged():
    original = _png_bytes((1000, 1000))
    result_bytes, media_type = _maybe_upscale(original, "image/jpeg")
    assert result_bytes == original
    assert media_type == "image/jpeg"


def test_tiny_image_upscale_is_capped():
    original = _png_bytes((20, 20))
    upscaled_bytes, _ = _maybe_upscale(original, "image/png")
    upscaled = Image.open(io.BytesIO(upscaled_bytes))
    assert upscaled.width == 20 * OCR_MAX_UPSCALE


def test_unparseable_bytes_pass_through_without_crashing():
    garbage = b"not an image"
    result_bytes, media_type = _maybe_upscale(garbage, "image/png")
    assert result_bytes == garbage
    assert media_type == "image/png"
