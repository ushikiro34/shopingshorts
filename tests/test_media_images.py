from io import BytesIO

from PIL import Image

from app.media.images import CANVAS_SIZE, compose_scene_image


def _synthetic_image_bytes(size=(600, 800), color=(200, 50, 50)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def test_compose_scene_image_returns_canvas_size():
    composed = compose_scene_image(_synthetic_image_bytes())
    assert composed.size == CANVAS_SIZE


def test_compose_scene_image_handles_wide_source():
    composed = compose_scene_image(_synthetic_image_bytes(size=(1200, 400)))
    assert composed.size == CANVAS_SIZE


def test_compose_scene_image_is_rgb():
    composed = compose_scene_image(_synthetic_image_bytes())
    assert composed.mode == "RGB"
