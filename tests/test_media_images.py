from io import BytesIO

import pytest
from PIL import Image

from app.media.images import CANVAS_SIZE, ImageFetchError, compose_scene_image, download_image


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


def test_download_image_reads_local_upload_path(tmp_path):
    local_file = tmp_path / "uploaded.jpg"
    local_file.write_bytes(_synthetic_image_bytes())
    relative_url = "/" + str(local_file).replace("\\", "/")
    assert download_image(relative_url) == local_file.read_bytes()


def test_download_image_local_path_missing_raises_image_fetch_error():
    with pytest.raises(ImageFetchError):
        download_image("/renders/product_images/does-not-exist/x.jpg")
