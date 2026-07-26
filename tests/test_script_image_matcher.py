import httpx
import pytest

from app.script import image_matcher
from app.script.image_matcher import ImageMatchError, select_scene_images

SCENES = [
    {"seq": 1, "narration": "긴장되는 순간", "caption": "긴장감", "image_index": 0},
    {"seq": 2, "narration": "만족스러운 결과", "caption": "만족감", "image_index": 1},
]


class _FakeTextBlock:
    def __init__(self, text: str):
        self.text = text


class _FakeMessage:
    def __init__(self, text: str):
        self.content = [_FakeTextBlock(text)]


class _FakeMessagesClient:
    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return _FakeMessage(response)


class _FakeClient:
    def __init__(self, responses: list):
        self.messages = _FakeMessagesClient(responses)


def _fake_request() -> httpx.Request:
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def test_zero_or_one_candidate_images_skips_api_call_and_maps_to_zero():
    result = select_scene_images(SCENES, [], client=_FakeClient([]))
    assert result == {1: 0, 2: 0}

    result = select_scene_images(SCENES, ["https://example.com/a.jpg"], client=_FakeClient([]))
    assert result == {1: 0, 2: 0}


def test_parses_valid_json_mapping(monkeypatch):
    monkeypatch.setattr(image_matcher, "download_image", lambda url: b"\xff\xd8\xff" + b"0" * 10)
    client = _FakeClient(['{"1": 0, "2": 2}'])

    result = select_scene_images(SCENES, ["a.jpg", "b.jpg", "c.jpg"], client=client)

    assert result == {1: 0, 2: 2}
    # 후보 이미지 3장 + 안내 텍스트가 한 번의 메시지에 모두 담겼는지 확인.
    sent_content = client.messages.calls[0]["messages"][0]["content"]
    image_blocks = [b for b in sent_content if b["type"] == "image"]
    assert len(image_blocks) == 3


def test_retries_once_then_succeeds(monkeypatch):
    monkeypatch.setattr(image_matcher, "download_image", lambda url: b"\xff\xd8\xff123")
    client = _FakeClient(
        [
            image_matcher.anthropic.APIConnectionError(request=_fake_request()),
            '{"1": 1, "2": 0}',
        ]
    )

    result = select_scene_images(SCENES, ["a.jpg", "b.jpg"], client=client)

    assert result == {1: 1, 2: 0}
    assert len(client.messages.calls) == 2


def test_raises_image_match_error_after_two_failures(monkeypatch):
    monkeypatch.setattr(image_matcher, "download_image", lambda url: b"\xff\xd8\xff123")
    client = _FakeClient(["이건 JSON이 아니다", "여전히 JSON이 아니다"])

    with pytest.raises(ImageMatchError):
        select_scene_images(SCENES, ["a.jpg", "b.jpg"], client=client)


def test_download_failure_raises_image_match_error(monkeypatch):
    def _boom(url):
        raise RuntimeError("network down")

    monkeypatch.setattr(image_matcher, "download_image", _boom)

    with pytest.raises(ImageMatchError):
        select_scene_images(SCENES, ["a.jpg", "b.jpg"], client=_FakeClient([]))
