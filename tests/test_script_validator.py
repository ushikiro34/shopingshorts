import pytest

from app.config import PARTNERS_DISCLOSURE
from app.script.validator import (
    ScriptValidationError,
    has_verbatim_overlap,
    validate_cta_redirects_to_description,
    validate_disclosure_placement,
    validate_educational_note,
    validate_no_price_mention,
    validate_script,
)


def _base_script(**overrides) -> dict:
    script = {
        "structure": {
            "empathy": "요즘 자꾸 새벽에 깨시나요?",
            "emotion": "낮에도 피곤하고 짜증나셨죠.",
            "problem": "잠을 설치면 하루종일 컨디션이 무너져요.",
            "solution": "숙면 루틴을 도와주는 도구가 필요해요.",
            "product": "이 수면 안대 하나로 편하게 주무세요. 제품정보는 본문에 있어요, 확인해보세요.",
        },
        "educational_note": {"included": False, "text": ""},
        "tone": "생활팁",
        "scenes": [
            {"seq": 1, "narration": "요즘 자꾸 새벽에 깨시나요", "caption": "공감", "image_index": 0, "duration_sec": 8},
            {"seq": 2, "narration": "낮에도 피곤하고 짜증나셨죠", "caption": "감정", "image_index": 0, "duration_sec": 8},
            {"seq": 3, "narration": "잠을 설치면 하루가 무너져요", "caption": "문제", "image_index": 1, "duration_sec": 8},
            {"seq": 4, "narration": "숙면 루틴이 필요해요", "caption": "해결", "image_index": 1, "duration_sec": 8},
            {"seq": 5, "narration": "이 수면 안대로 시작해보세요", "caption": "상품", "image_index": 2, "duration_sec": 8},
        ],
        "disclosure": PARTNERS_DISCLOSURE,
        "estimated_duration_sec": 40,
        "youtube": {
            "title": "t",
            "description": f"편안한 수면을 위한 선택. 구매 링크는 본문 더보기에서 확인해 주세요.\n\n{PARTNERS_DISCLOSURE}",
            "tags": ["tag"],
        },
    }
    script.update(overrides)
    return script


def test_valid_script_passes():
    validate_script(_base_script(), reviews_raw="이 상품 정말 좋아요 잘 쓰고 있습니다", needs_education=False)


def test_missing_structure_field_rejected():
    script = _base_script()
    script["structure"]["emotion"] = ""
    with pytest.raises(ScriptValidationError) as exc:
        validate_script(script, reviews_raw="", needs_education=False)
    assert any("emotion" in e for e in exc.value.errors)


def test_invalid_tone_rejected():
    script = _base_script(tone="화남")
    with pytest.raises(ScriptValidationError) as exc:
        validate_script(script, reviews_raw="", needs_education=False)
    assert any("tone" in e for e in exc.value.errors)


def test_disclosure_mismatch_rejected():
    script = _base_script(disclosure="다른 문구")
    with pytest.raises(ScriptValidationError) as exc:
        validate_script(script, reviews_raw="", needs_education=False)
    assert any("disclosure" in e for e in exc.value.errors)


def test_too_few_scenes_rejected():
    script = _base_script(scenes=_base_script()["scenes"][:2])
    with pytest.raises(ScriptValidationError) as exc:
        validate_script(script, reviews_raw="", needs_education=False)
    assert any("scenes" in e for e in exc.value.errors)


def test_duration_out_of_range_rejected():
    script = _base_script(estimated_duration_sec=90)
    with pytest.raises(ScriptValidationError) as exc:
        validate_script(script, reviews_raw="", needs_education=False)
    assert any("estimated_duration_sec" in e for e in exc.value.errors)


def test_verbatim_leak_detected():
    reviews_raw = "이 제품 정말 부드럽고 편안해서 매일 밤 잘 쓰고 있고 재구매도 할 예정입니다"
    narration = "이 제품 정말 부드럽고 편안해서 매일 밤 잘 쓰고 있고 재구매도"
    assert has_verbatim_overlap(narration, reviews_raw) is True


def test_no_verbatim_leak_when_reworded():
    reviews_raw = "이 제품 정말 부드럽고 편안해서 매일 밤 잘 쓰고 있고 재구매도 할 예정입니다"
    narration = "밤마다 포근하게 감싸주는 느낌이 좋아서 계속 손이 가요"
    assert has_verbatim_overlap(narration, reviews_raw) is False


def test_script_rejected_when_narration_leaks_review():
    reviews_raw = "이 제품 정말 부드럽고 편안해서 매일 밤 잘 쓰고 있고 재구매도 할 예정입니다"
    script = _base_script()
    script["scenes"][0]["narration"] = "이 제품 정말 부드럽고 편안해서 매일 밤 잘 쓰고 있고 재구매도"
    with pytest.raises(ScriptValidationError) as exc:
        validate_script(script, reviews_raw=reviews_raw, needs_education=False)
    assert any("연속 일치" in e for e in exc.value.errors)


def test_needs_education_true_requires_note():
    script = _base_script(educational_note={"included": False, "text": ""})
    errors = validate_educational_note(script, needs_education=True)
    assert errors


def test_needs_education_true_with_valid_note_passes():
    script = _base_script(
        educational_note={"included": True, "text": "자외선은 피부 노화를 유발할 수 있어요."}
    )
    errors = validate_educational_note(script, needs_education=True)
    assert errors == []


def test_needs_education_false_with_included_note_rejected():
    script = _base_script(
        educational_note={"included": True, "text": "자외선은 피부 노화를 유발할 수 있어요."}
    )
    errors = validate_educational_note(script, needs_education=False)
    assert errors


def test_educational_note_forbidden_keyword_rejected():
    script = _base_script(
        educational_note={"included": True, "text": "이 성분은 질병을 완치시켜줍니다."}
    )
    errors = validate_educational_note(script, needs_education=True)
    assert any("금지어" in e for e in errors)


def test_educational_note_tempered_language_passes():
    script = _base_script(
        educational_note={"included": True, "text": "자외선은 피부 노화를 유발할 수 있어요."}
    )
    errors = validate_educational_note(script, needs_education=True)
    assert errors == []


# v2.2: 가격 미표기 + 본문 유도 CTA + 고지문구 위치 (사용자 피드백 반영)


def test_price_in_product_field_rejected():
    script = _base_script()
    script["structure"]["product"] = "이 안대는 18,900원이에요. 본문에서 확인하세요."
    errors = validate_no_price_mention(script)
    assert any("18,900원" in e for e in errors)


def test_price_manwon_style_rejected():
    script = _base_script()
    script["structure"]["product"] = "이 안대는 2만원대라 부담없어요. 본문에서 확인하세요."
    errors = validate_no_price_mention(script)
    assert errors


def test_price_in_scene_narration_rejected():
    script = _base_script()
    script["scenes"][-1]["narration"] = "12000원에 만나보세요"
    errors = validate_no_price_mention(script)
    assert errors


def test_price_in_youtube_description_rejected():
    script = _base_script()
    script["youtube"]["description"] = f"18,900원 특가! 본문 확인.\n\n{PARTNERS_DISCLOSURE}"
    errors = validate_no_price_mention(script)
    assert errors


def test_no_price_mention_passes_when_absent():
    errors = validate_no_price_mention(_base_script())
    assert errors == []


def test_cta_missing_redirect_hint_rejected():
    script = _base_script()
    script["structure"]["product"] = "이 안대 정말 좋아요. 꼭 사보세요."
    errors = validate_cta_redirects_to_description(script)
    assert errors


def test_cta_with_redirect_hint_passes():
    errors = validate_cta_redirects_to_description(_base_script())
    assert errors == []


def test_disclosure_in_narration_rejected():
    script = _base_script()
    script["structure"]["product"] += f" {PARTNERS_DISCLOSURE}"
    errors = validate_disclosure_placement(script)
    assert any("narration" in e for e in errors)


def test_description_not_ending_with_disclosure_rejected():
    script = _base_script()
    script["youtube"]["description"] = "그냥 설명입니다"
    errors = validate_disclosure_placement(script)
    assert any("고지문구로 끝나지" in e for e in errors)


def test_disclosure_placement_passes_when_correct():
    errors = validate_disclosure_placement(_base_script())
    assert errors == []
