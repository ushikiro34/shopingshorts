import pytest

from app.script.formats import (
    SCRIPT_FORMATS,
    active_tone_choices,
    all_known_tones,
    get_format,
)
from app.script.prompts import build_system_prompt


def test_get_format_returns_known_format():
    fmt = get_format("생활팁")
    assert fmt.label == "생활팁"
    assert fmt.legacy is True
    assert fmt.stage_keys == ["empathy", "emotion", "problem", "solution", "result", "product"]


def test_get_format_falls_back_for_unknown_tone():
    fmt = get_format("존재하지않는톤")
    assert fmt.legacy is True
    assert fmt.stage_keys == ["empathy", "emotion", "problem", "solution", "result", "product"]


def test_get_format_falls_back_for_none():
    fmt = get_format(None)
    assert fmt.label == "생활팁"


def test_active_tone_choices_excludes_legacy():
    legacy_labels = {"불편해결", "우월감", "보상", "생활팁", "사실형", "생활형", "실리적"}
    active = active_tone_choices()
    assert len(active) == 7
    assert legacy_labels.isdisjoint(active)


def test_all_known_tones_includes_legacy_and_active():
    known = all_known_tones()
    assert len(known) == 14
    assert "생활팁" in known  # legacy, still resolvable
    assert "썸쇼츠형" in known  # new


def test_registry_cta_stage_and_educational_note_stage_are_valid():
    """cta_stage/educational_note_after_stage에 오타가 있으면 그 형식의 CTA 검증/
    사실설명 삽입이 항상 조용히 실패한다 — 레지스트리 전체를 자체 점검한다."""
    for tone, fmt in SCRIPT_FORMATS.items():
        assert fmt.cta_stage in fmt.stage_keys, f"{tone}: cta_stage가 stage_keys에 없음"
        assert fmt.educational_note_after_stage in fmt.stage_keys, (
            f"{tone}: educational_note_after_stage가 stage_keys에 없음"
        )


def test_label_for_returns_key_when_unknown():
    fmt = get_format("생활팁")
    assert fmt.label_for("empathy") == "공감"
    assert fmt.label_for("no_such_key") == "no_such_key"


def test_build_system_prompt_works_for_every_registered_format():
    """레지스트리 14개 전부에서 build_system_prompt가 예외 없이 완전한 프롬프트를
    만들어내는지 확인한다 — needs_education True/False 양쪽 다(형식마다 다른
    educational_note_after_stage로 문자열 포맷팅하는 부분의 회귀 테스트)."""
    for tone in all_known_tones():
        for needs_education in (False, True):
            prompt = build_system_prompt(tone, needs_education)
            assert tone in prompt
            assert '"tone"' in prompt or "tone" in prompt


def test_build_system_prompt_rejects_unknown_tone():
    with pytest.raises(ValueError):
        build_system_prompt("존재하지않는톤", False)
