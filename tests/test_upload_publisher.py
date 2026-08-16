import pytest

from app.upload import publisher


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._json


class _FakeHttpxClient:
    def __init__(self):
        self.calls = []
        self.upload_init_json = None

    def post(self, url, headers=None, json=None, data=None, content=None):
        self.calls.append(("POST", url))
        if url == publisher.TOKEN_URL:
            return _FakeResponse(200, {"access_token": "fake-access-token"})
        if url.startswith(publisher.UPLOAD_URL):
            self.upload_init_json = json
            return _FakeResponse(200, headers={"Location": "https://upload.example/session123"})
        if url.startswith(publisher.THUMBNAIL_URL):
            return _FakeResponse(200, {})
        raise AssertionError(f"unexpected POST url: {url}")

    def put(self, url, headers=None, content=None):
        self.calls.append(("PUT", url))
        assert url == "https://upload.example/session123"
        return _FakeResponse(200, {"id": "yt_video_123"})


@pytest.fixture(autouse=True)
def _fake_youtube_credentials(monkeypatch):
    monkeypatch.setattr(publisher, "YOUTUBE_CLIENT_ID", "fake-client-id")
    monkeypatch.setattr(publisher, "YOUTUBE_CLIENT_SECRET", "fake-client-secret")
    monkeypatch.setattr(publisher, "YOUTUBE_REFRESH_TOKEN", "fake-refresh-token")


def test_publish_video_returns_video_id(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"FAKE_VIDEO_BYTES")
    thumb_path = tmp_path / "thumb.jpg"
    thumb_path.write_bytes(b"FAKE_THUMB_BYTES")

    client = _FakeHttpxClient()
    video_id = publisher.publish_video(
        str(video_path), "제목", "설명", thumbnail_path=str(thumb_path), client=client
    )

    assert video_id == "yt_video_123"
    urls_called = [url for _, url in client.calls]
    assert publisher.TOKEN_URL in urls_called
    assert any(url.startswith(publisher.UPLOAD_URL) for url in urls_called)
    assert any(url.startswith(publisher.THUMBNAIL_URL) for url in urls_called)
    # AGENTS.md 절대 규칙 4 — 실제 공개는 유튜브 스튜디오에서 사람이 별도로 진행해야 하므로
    # 이 앱은 항상 비공개로만 업로드해야 한다.
    assert client.upload_init_json["status"]["privacyStatus"] == "private"
    # AGENTS.md 절대 규칙 4 — 실제 공개는 유튜브 스튜디오에서 사람이 별도로 진행해야 하므로
    # 이 앱은 항상 비공개로만 업로드해야 한다.
    assert client.upload_init_json["status"]["privacyStatus"] == "private"


def test_publish_video_without_thumbnail_skips_thumbnail_call(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"FAKE_VIDEO_BYTES")

    client = _FakeHttpxClient()
    video_id = publisher.publish_video(str(video_path), "제목", "설명", client=client)

    assert video_id == "yt_video_123"
    urls_called = [url for _, url in client.calls]
    assert not any(url.startswith(publisher.THUMBNAIL_URL) for url in urls_called)


def test_missing_credentials_raises_clear_error(monkeypatch, tmp_path):
    monkeypatch.setattr(publisher, "YOUTUBE_CLIENT_ID", "")
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"x")

    with pytest.raises(publisher.PublishError, match="YOUTUBE_CLIENT_ID"):
        publisher.publish_video(str(video_path), "t", "d", client=_FakeHttpxClient())


def test_upload_failure_raises_publish_error(tmp_path):
    class _FailingUploadClient(_FakeHttpxClient):
        def put(self, url, headers=None, content=None):
            return _FakeResponse(500, text="server error")

    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"x")

    with pytest.raises(publisher.PublishError, match="영상 업로드 실패"):
        publisher.publish_video(str(video_path), "t", "d", client=_FailingUploadClient())
