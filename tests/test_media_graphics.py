from app.media.graphics import (
    DEFAULT_GRADIENT,
    compose_educational_note_scene,
    draw_icon,
    get_category_gradient,
    get_category_icon_name,
    make_gradient_background,
    rounded_rect,
)


def test_gradient_matches_known_category_keyword():
    assert get_category_gradient("자외선차단제") != DEFAULT_GRADIENT


def test_gradient_falls_back_to_default_for_unknown_category():
    assert get_category_gradient("생소한카테고리") == DEFAULT_GRADIENT
    assert get_category_gradient(None) == DEFAULT_GRADIENT


def test_icon_name_matches_known_keyword():
    assert get_category_icon_name("정수 필터 카트리지") == "droplet"
    assert get_category_icon_name("자외선차단제") == "sun"


def test_icon_name_falls_back_to_check():
    assert get_category_icon_name("휴지") == "check"
    assert get_category_icon_name(None) == "check"


def test_make_gradient_background_size():
    bg = make_gradient_background((300, 500), category="자외선")
    assert bg.size == (300, 500)
    assert bg.mode == "RGB"


def test_draw_icon_returns_rgba_of_requested_size():
    for name in ["sun", "droplet", "moon", "leaf", "check", "unknown-name"]:
        icon = draw_icon(name, size=100)
        assert icon.size == (100, 100)
        assert icon.mode == "RGBA"


def test_rounded_rect_has_alpha_channel():
    card = rounded_rect((200, 80), radius=16, fill=(0, 0, 0, 140))
    assert card.mode == "RGBA"
    assert card.size == (200, 80)


def test_compose_educational_note_scene_size_and_mode():
    scene = compose_educational_note_scene((1080, 1920), category="자외선차단제")
    assert scene.size == (1080, 1920)
    assert scene.mode == "RGB"
