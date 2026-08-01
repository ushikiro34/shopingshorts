import pytest

from app.media import video_generator
from app.media.video_generator import VideoGenerationError, generate_scene_video


class _FakeResponse:
    def __init__(self, status_code=200, json_body=None, content=b"", text=""):
        self.status_code = status_code
        self._json_body = json_body
        self.content = content
        self.text = text

    def json(self):
        return self._json_body


class _FakeClient:
    def __init__(self, post_responses=None, get_responses=None):
        self._post_responses = list(post_responses or [])
        self._get_responses = list(get_responses or [])
        self.post_calls: list[dict] = []
        self.get_calls: list[dict] = []

    def post(self, url, params=None, json=None):
        self.post_calls.append({"url": url, "params": params, "json": json})
        return self._post_responses.pop(0)

    def get(self, url, params=None, follow_redirects=None):
        self.get_calls.append({"url": url, "params": params, "follow_redirects": follow_redirects})
        return self._get_responses.pop(0)


def _submit_ok(op_name="models/veo-3.1-fast-generate-preview/operations/abc123"):
    return _FakeResponse(200, {"name": op_name})


def _done_response(video_uri="https://generativelanguage.googleapis.com/v1beta/files/xyz:download?alt=media"):
    return _FakeResponse(
        200,
        {
            "done": True,
            "response": {
                "generateVideoResponse": {"generatedSamples": [{"video": {"uri": video_uri}}]}
            },
        },
    )


def _not_done_response():
    return _FakeResponse(200, {"done": False})


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    # POLL_INTERVAL_SEC(10초)만큼 실제로 자면 테스트가 느려지니 무력화한다.
    monkeypatch.setattr(video_generator.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(video_generator, "GEMINI_API_KEY", "fake-key")


def test_generate_scene_video_returns_bytes_on_first_poll():
    client = _FakeClient(
        post_responses=[_submit_ok()],
        get_responses=[_done_response(), _FakeResponse(200, content=b"fakevideobytes")],
    )

    result = generate_scene_video(b"reference-image", "image/jpeg", "고민", "나레이션", client=client)

    assert result == b"fakevideobytes"
    assert len(client.post_calls) == 1
    sent_body = client.post_calls[0]["json"]
    assert sent_body["instances"][0]["image"]["mimeType"] == "image/jpeg"
    assert sent_body["parameters"]["aspectRatio"] == "9:16"


def test_generate_scene_video_polls_until_done():
    client = _FakeClient(
        post_responses=[_submit_ok()],
        get_responses=[_not_done_response(), _not_done_response(), _done_response(), _FakeResponse(200, content=b"video-bytes")],
    )

    result = generate_scene_video(b"reference-image", "image/jpeg", "고민", "나레이션", client=client)

    assert result == b"video-bytes"
    assert len(client.get_calls) == 4  # 폴링 3회 + 다운로드 1회


def test_generate_scene_video_retries_once_then_succeeds():
    # 후킹(첫 씬)은 반드시 영상으로 나가야 해서(사용자 피드백), Veo의 비결정적 실패(콘텐츠
    # 안전 필터 등)에 대비해 AGENTS.md 컨벤션대로 재시도 1회를 거친다.
    client = _FakeClient(
        post_responses=[_FakeResponse(500, text="server error"), _submit_ok()],
        get_responses=[_done_response(), _FakeResponse(200, content=b"recovered-bytes")],
    )

    result = generate_scene_video(b"reference-image", "image/jpeg", "고민", "나레이션", client=client)

    assert result == b"recovered-bytes"
    assert len(client.post_calls) == 2


def test_generate_scene_video_raises_on_submit_failure_after_retry():
    client = _FakeClient(post_responses=[_FakeResponse(500, text="server error"), _FakeResponse(500, text="err2")])

    with pytest.raises(VideoGenerationError):
        generate_scene_video(b"reference-image", "image/jpeg", "고민", "나레이션", client=client)


def test_generate_scene_video_raises_on_poll_failure_after_retry():
    client = _FakeClient(
        post_responses=[_submit_ok(), _submit_ok()],
        get_responses=[_FakeResponse(500, text="poll error"), _FakeResponse(500, text="poll error 2")],
    )

    with pytest.raises(VideoGenerationError):
        generate_scene_video(b"reference-image", "image/jpeg", "고민", "나레이션", client=client)


def test_generate_scene_video_raises_when_done_response_missing_video_after_retry():
    client = _FakeClient(
        post_responses=[_submit_ok(), _submit_ok()],
        get_responses=[
            _FakeResponse(200, {"done": True, "response": {}}),
            _FakeResponse(200, {"done": True, "response": {}}),
        ],
    )

    with pytest.raises(VideoGenerationError):
        generate_scene_video(b"reference-image", "image/jpeg", "고민", "나레이션", client=client)


def test_generate_scene_video_raises_on_download_failure_after_retry():
    client = _FakeClient(
        post_responses=[_submit_ok(), _submit_ok()],
        get_responses=[_done_response(), _FakeResponse(500), _done_response(), _FakeResponse(500)],
    )

    with pytest.raises(VideoGenerationError):
        generate_scene_video(b"reference-image", "image/jpeg", "고민", "나레이션", client=client)


def test_generate_scene_video_raises_after_max_poll_attempts_on_both_tries(monkeypatch):
    monkeypatch.setattr(video_generator, "MAX_POLL_ATTEMPTS", 3)
    client = _FakeClient(
        post_responses=[_submit_ok(), _submit_ok()],
        get_responses=[
            _not_done_response(), _not_done_response(), _not_done_response(),
            _not_done_response(), _not_done_response(), _not_done_response(),
        ],
    )

    with pytest.raises(VideoGenerationError):
        generate_scene_video(b"reference-image", "image/jpeg", "고민", "나레이션", client=client)


def test_generate_scene_video_raises_without_api_key(monkeypatch):
    monkeypatch.setattr(video_generator, "GEMINI_API_KEY", "")

    with pytest.raises(VideoGenerationError):
        generate_scene_video(b"reference-image", "image/jpeg", "고민", "나레이션", client=_FakeClient())
