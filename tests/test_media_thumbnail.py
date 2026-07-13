from io import BytesIO

from PIL import Image

from app.media.images import CANVAS_SIZE
from app.media.thumbnail import generate_thumbnail


def _synthetic_image_bytes(size=(600, 800), color=(80, 120, 200)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def test_generate_thumbnail_with_product_image(tmp_path):
    output_path = str(tmp_path / "thumb.jpg")
    result = generate_thumbnail(
        "요즘 자꾸 새벽에 깨시나요?",
        _synthetic_image_bytes(),
        category="생활용품",
        output_path=output_path,
    )
    assert result == output_path
    with Image.open(output_path) as img:
        assert img.size == CANVAS_SIZE
        assert img.format == "JPEG"


def test_generate_thumbnail_without_product_image_uses_graphic_fallback(tmp_path):
    output_path = str(tmp_path / "thumb.jpg")
    generate_thumbnail(
        "제품정보는 본문에 있어요, 확인해보세요.",
        None,
        category="자외선차단제",
        output_path=output_path,
    )
    with Image.open(output_path) as img:
        assert img.size == CANVAS_SIZE


def test_generate_thumbnail_wraps_long_hook_text(tmp_path):
    output_path = str(tmp_path / "thumb.jpg")
    long_hook = "이것은 매우 길어서 한 줄에 절대 들어가지 않을 것으로 예상되는 훅 문장입니다 정말로 깁니다"
    generate_thumbnail(long_hook, None, category=None, output_path=output_path)
    with Image.open(output_path) as img:
        assert img.size == CANVAS_SIZE
