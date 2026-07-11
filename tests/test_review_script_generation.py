import json

import pytest

from app.review.analyzer import ReviewAnalysisError, analyze_reviews
from app.script.generator import generate_script


class _FakeContentBlock:
    def __init__(self, text: str):
        self.text = text


class _FakeMessage:
    def __init__(self, text: str):
        self.content = [_FakeContentBlock(text)]


class _FakeMessages:
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        text = self._responses.pop(0)
        return _FakeMessage(text)


class _FakeClient:
    def __init__(self, responses: list[str]):
        self.messages = _FakeMessages(responses)


VALID_ANALYSIS = {
    "positives": ["부드러운 원단"],
    "complaints": ["얇게 느껴질 수 있음"],
    "surprises": ["가성비 대비 만족도가 높다"],
    "repurchase_reasons": ["대용량이라 쟁여두기 좋음"],
    "emotional_keywords": ["안심", "든든함"],
    "target_segments": ["생필품 재구매층"],
    "suggested_hook_angle": "믿고 쓰는 브랜드로 갈아탄 이유",
}


def test_analyze_reviews_parses_valid_json():
    client = _FakeClient([json.dumps(VALID_ANALYSIS, ensure_ascii=False)])
    result = analyze_reviews("아주 좋아요 부드럽고 편해요", client=client)
    assert result == VALID_ANALYSIS
    assert client.messages.calls == 1


def test_analyze_reviews_retries_once_on_bad_json_then_succeeds():
    client = _FakeClient(["이건 JSON이 아님", json.dumps(VALID_ANALYSIS, ensure_ascii=False)])
    result = analyze_reviews("리뷰", client=client)
    assert result == VALID_ANALYSIS
    assert client.messages.calls == 2


def test_analyze_reviews_raises_after_two_failures():
    client = _FakeClient(["이건 JSON이 아님", "여전히 JSON이 아님"])
    with pytest.raises(ReviewAnalysisError):
        analyze_reviews("리뷰", client=client)
    assert client.messages.calls == 2


def test_analyze_reviews_rejects_missing_fields():
    incomplete = {"positives": ["좋아요"]}
    client = _FakeClient([json.dumps(incomplete), json.dumps(incomplete)])
    with pytest.raises(ReviewAnalysisError):
        analyze_reviews("리뷰", client=client)


VALID_SCRIPT = {
    "structure": {
        "empathy": "e",
        "emotion": "e2",
        "problem": "p",
        "solution": "s",
        "product": "prod",
    },
    "educational_note": {"included": False, "text": ""},
    "tone": "생활팁",
    "scenes": [{"seq": 1, "narration": "n", "caption": "c", "image_index": 0, "duration_sec": 5}],
    "disclosure": "d",
    "estimated_duration_sec": 40,
    "youtube": {"title": "t", "description": "d", "tags": []},
}


def test_generate_script_parses_valid_json():
    client = _FakeClient([json.dumps(VALID_SCRIPT, ensure_ascii=False)])
    result = generate_script(
        analysis_json=VALID_ANALYSIS,
        product={"product_name": "테스트 상품", "price": 10000, "category": "생활용품"},
        tone="생활팁",
        needs_education=False,
        client=client,
    )
    assert result == VALID_SCRIPT
