import io

from PIL import Image, ImageDraw

from app.review.ocr import OCR_MAX_UPSCALE, OCR_MIN_DIMENSION_PX, _preprocess_for_ocr


def _png_bytes(size: tuple[int, int]) -> bytes:
    img = Image.new("RGB", size, "white")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _png_bytes_with_edges(size: tuple[int, int]) -> bytes:
    # 완전 단색 이미지는 선명화(unsharp mask)가 적용돼도 바이트가 안 바뀐다(엣지가
    # 없어서) — 순수 흑백(0/255) 엣지도 마찬가지다(보정값이 0~255 범위를 벗어나
    # 클리핑되면서 결국 원래 값으로 되돌아간다). 클리핑 없이 실제로 값이 바뀌는 걸
    # 보려면 중간 톤(회색) 사각형처럼 여유가 있는 대비가 필요하다.
    img = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle(
        [size[0] // 4, size[1] // 4, size[0] * 3 // 4, size[1] * 3 // 4], fill=(180, 180, 180)
    )
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_small_image_gets_upscaled_to_min_dimension():
    # 짧은 변(300)에 필요한 배율(800/300≈2.67)이 OCR_MAX_UPSCALE(4) 이내라 목표 크기까지 커진다.
    original = _png_bytes((900, 300))
    result_bytes, media_type = _preprocess_for_ocr(original, "image/png")

    result = Image.open(io.BytesIO(result_bytes))
    assert media_type == "image/png"
    assert min(result.width, result.height) >= OCR_MIN_DIMENSION_PX - 1  # 반올림 오차 허용
    assert result.width > 900


def test_large_image_is_not_upscaled_but_is_sharpened():
    # 이미 충분히 큰 이미지는 크기를 키우지 않지만, 선명화는 크기와 무관하게 항상
    # 적용한다(사용자 피드백: 확대해도 여전히 인식률이 낮음 — 흐림이 원인일 수 있음).
    original = _png_bytes_with_edges((1000, 1000))
    result_bytes, media_type = _preprocess_for_ocr(original, "image/jpeg")

    result = Image.open(io.BytesIO(result_bytes))
    assert media_type == "image/png"  # 항상 재인코딩되므로 PNG로 통일된다
    assert result.size == (1000, 1000)  # 크기는 그대로
    assert result_bytes != original  # 선명화가 적용돼 바이트는 달라짐


def test_tiny_image_upscale_is_capped():
    original = _png_bytes((20, 20))
    result_bytes, _ = _preprocess_for_ocr(original, "image/png")
    result = Image.open(io.BytesIO(result_bytes))
    assert result.width == 20 * OCR_MAX_UPSCALE


def test_unparseable_bytes_pass_through_without_crashing():
    garbage = b"not an image"
    result_bytes, media_type = _preprocess_for_ocr(garbage, "image/png")
    assert result_bytes == garbage
    assert media_type == "image/png"
