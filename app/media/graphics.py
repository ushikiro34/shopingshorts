"""4호 직원 — 2D 그래픽 레이어 (Phase 3, C안).

배경 그라디언트, 카테고리 아이콘, 강조 카드, educational_note용 다이어그램을
전부 벡터/도형 기반(PIL ImageDraw)으로 생성한다. AI 이미지 생성 API는 쓰지 않는다
(docs/phase3_spec.md C안, AGENTS.md 리스크 원칙 참조). 텍스트 번인은 render.py가
ffmpeg drawtext로 일괄 처리하므로, 여기서는 텍스트가 없는 배경/아이콘/카드만 만든다.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

RGB = tuple[int, int, int]

DEFAULT_GRADIENT: tuple[RGB, RGB] = ((99, 102, 241), (168, 85, 247))  # indigo -> purple

# 카테고리 키워드 매칭 기반 그라디언트 프리셋 (초기값, 운영하며 보강)
CATEGORY_GRADIENTS: dict[str, tuple[RGB, RGB]] = {
    "자외선": ((251, 191, 36), (249, 115, 22)),
    "선크림": ((251, 191, 36), (249, 115, 22)),
    "정수": ((59, 130, 246), (6, 182, 212)),
    "필터": ((59, 130, 246), (6, 182, 212)),
    "살균": ((16, 185, 129), (5, 150, 105)),
    "항균": ((16, 185, 129), (5, 150, 105)),
    "수면": ((79, 70, 229), (30, 27, 75)),
    "안대": ((79, 70, 229), (30, 27, 75)),
    "유산균": ((236, 72, 153), (219, 39, 119)),
}

# 카테고리 키워드 매칭 기반 아이콘 프리셋 (초기값, 운영하며 보강)
CATEGORY_ICONS: dict[str, str] = {
    "자외선": "sun",
    "선크림": "sun",
    "정수": "droplet",
    "필터": "droplet",
    "살균": "check",
    "항균": "check",
    "수면": "moon",
    "안대": "moon",
    "유산균": "leaf",
}


def _match_category(category: str | None, mapping: dict[str, str]) -> str | None:
    if not category:
        return None
    for keyword, value in mapping.items():
        if keyword in category:
            return value
    return None


def get_category_gradient(category: str | None) -> tuple[RGB, RGB]:
    for keyword, gradient in CATEGORY_GRADIENTS.items():
        if category and keyword in category:
            return gradient
    return DEFAULT_GRADIENT


def get_category_icon_name(category: str | None) -> str:
    return _match_category(category, CATEGORY_ICONS) or "check"


def make_gradient_background(size: tuple[int, int], category: str | None = None) -> Image.Image:
    """세로 방향 선형 그라디언트 배경을 생성한다."""
    top_color, bottom_color = get_category_gradient(category)
    width, height = size
    column = Image.new("RGB", (1, height))
    for y in range(height):
        ratio = y / max(height - 1, 1)
        pixel = tuple(
            int(top_color[i] * (1 - ratio) + bottom_color[i] * ratio) for i in range(3)
        )
        column.putpixel((0, y), pixel)
    return column.resize((width, height))


def rounded_rect(
    size: tuple[int, int], radius: int, fill: tuple[int, int, int, int]
) -> Image.Image:
    """카드/강조 박스용 반투명 둥근 사각형(RGBA)을 생성한다."""
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([(0, 0), (size[0] - 1, size[1] - 1)], radius=radius, fill=fill)
    return image


def draw_icon(name: str, size: int = 160, color: tuple[int, int, int, int] = (255, 255, 255, 230)) -> Image.Image:
    """도형 기반 카테고리 아이콘(RGBA, 투명 배경)을 생성한다."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    pad = size * 0.12

    if name == "sun":
        r = size * 0.22
        cx = cy = size / 2
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
        for i in range(8):
            import math

            angle = math.radians(i * 45)
            x1 = cx + math.cos(angle) * (r + size * 0.08)
            y1 = cy + math.sin(angle) * (r + size * 0.08)
            x2 = cx + math.cos(angle) * (r + size * 0.22)
            y2 = cy + math.sin(angle) * (r + size * 0.22)
            draw.line([(x1, y1), (x2, y2)], fill=color, width=int(size * 0.045))
    elif name == "droplet":
        cx = size / 2
        draw.polygon(
            [(cx, pad), (size - pad, size * 0.62), (cx, size - pad), (pad, size * 0.62)],
            fill=color,
        )
        r = size * 0.32
        draw.ellipse([cx - r, size * 0.4, cx + r, size * 0.4 + 2 * r], fill=color)
    elif name == "moon":
        r = size * 0.34
        cx = cy = size / 2
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
        cut_r = r * 1.05
        draw.ellipse(
            [cx - r * 0.35, cy - cut_r, cx + cut_r, cy + cut_r], fill=(0, 0, 0, 0)
        )
    elif name == "leaf":
        draw.pieslice([pad, pad, size - pad, size - pad], start=200, end=20, fill=color)
    else:  # "check" 및 그 외 알 수 없는 이름의 기본값
        r = size * 0.42
        cx = cy = size / 2
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=int(size * 0.06))
        draw.line(
            [(cx - r * 0.4, cy), (cx - r * 0.05, cy + r * 0.35), (cx + r * 0.45, cy - r * 0.35)],
            fill=color,
            width=int(size * 0.07),
            joint="curve",
        )

    return image


def compose_educational_note_scene(
    size: tuple[int, int], category: str | None = None
) -> Image.Image:
    """사실설명(educational_note) 장면용 2D 그래픽 캔버스 — 실사 이미지를 쓰지 않는다."""
    canvas = make_gradient_background(size, category).convert("RGBA")
    icon = draw_icon(get_category_icon_name(category), size=int(size[0] * 0.32))
    x = (size[0] - icon.width) // 2
    y = int(size[1] * 0.28)
    canvas.alpha_composite(icon, (x, y))

    card_size = (int(size[0] * 0.86), int(size[1] * 0.28))
    card = rounded_rect(card_size, radius=32, fill=(0, 0, 0, 140))
    cx = (size[0] - card_size[0]) // 2
    cy = int(size[1] * 0.62)
    canvas.alpha_composite(card, (cx, cy))

    return canvas.convert("RGB")
