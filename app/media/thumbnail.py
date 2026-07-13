"""5호 직원 — 썸네일 생성 (Phase 4).

대본의 훅 텍스트(structure.empathy 또는 suggested_hook_angle) + 상품 실사 이미지로
유튜브 쇼츠 커버용 썸네일(1080x1920)을 만든다. AI 이미지 생성은 쓰지 않는다
(로드맵에서 완전 제외 — docs/00_project_overview.md 리스크 원칙 참조).
"""

from __future__ import annotations

from PIL import ImageDraw, ImageFont

from app.media.graphics import compose_educational_note_scene
from app.media.images import CANVAS_SIZE, compose_scene_image
from app.media.render import resolve_font_path, wrap_text_lines

HOOK_FONTSIZE = 72
HOOK_MAX_WIDTH_RATIO = 0.86
HOOK_LINE_HEIGHT = 90
HOOK_BOX_PADDING = 32
HOOK_BOX_TOP_RATIO = 0.06  # 썸네일은 위쪽 훅 텍스트가 잘 보이도록 상단에 배치


def generate_thumbnail(
    hook_text: str,
    product_image_bytes: bytes | None,
    category: str | None,
    output_path: str,
    font_path: str | None = None,
) -> str:
    """훅 텍스트를 큼직하게 얹은 썸네일 JPEG를 저장하고 경로를 반환한다.

    product_image_bytes가 있으면 실사 상품 이미지를, 없으면 2D 그래픽 배경을 쓴다.
    """
    if product_image_bytes:
        canvas = compose_scene_image(product_image_bytes).convert("RGBA")
    else:
        canvas = compose_educational_note_scene(CANVAS_SIZE, category=category).convert("RGBA")

    active_font_path = font_path or resolve_font_path()
    max_width = int(CANVAS_SIZE[0] * HOOK_MAX_WIDTH_RATIO)
    lines = wrap_text_lines(hook_text, active_font_path, HOOK_FONTSIZE, max_width)

    box_height = HOOK_LINE_HEIGHT * len(lines) + HOOK_BOX_PADDING * 2
    box_top = int(CANVAS_SIZE[1] * HOOK_BOX_TOP_RATIO)

    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle([(0, box_top), (CANVAS_SIZE[0], box_top + box_height)], fill=(0, 0, 0, 150))

    font = ImageFont.truetype(active_font_path, HOOK_FONTSIZE)
    for i, line in enumerate(lines):
        text_width = font.getlength(line)
        x = (CANVAS_SIZE[0] - text_width) / 2
        y = box_top + HOOK_BOX_PADDING + i * HOOK_LINE_HEIGHT
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

    canvas.convert("RGB").save(output_path, "JPEG", quality=92)
    return output_path
