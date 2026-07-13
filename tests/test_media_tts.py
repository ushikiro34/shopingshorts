import subprocess

import pytest

from app.media import tts


class _FakeResponse:
    def __init__(self, status_code: int, content: bytes = b"", text: str = ""):
        self.status_code = status_code
        self.content = content
        self.text = text


class _FakeHttpxClient:
    def __init__(self, responses: list[_FakeResponse]):
        self._responses = list(responses)
        self.calls = 0

    def post(self, url, headers=None, json=None):
        self.calls += 1
        return self._responses.pop(0)


@pytest.fixture(autouse=True)
def _fake_credentials(monkeypatch):
    monkeypatch.setattr(tts, "ELEVENLABS_API_KEY", "fake-key")
    monkeypatch.setattr(tts, "ELEVENLABS_VOICE_ID", "fake-voice")


def test_synthesize_scene_audio_writes_file(tmp_path):
    client = _FakeHttpxClient([_FakeResponse(200, content=b"FAKE_MP3_BYTES")])
    output_path = str(tmp_path / "scene_1.mp3")

    result_path = tts.synthesize_scene_audio("안녕하세요", output_path, client=client)

    assert result_path == output_path
    assert open(output_path, "rb").read() == b"FAKE_MP3_BYTES"
    assert client.calls == 1


def test_synthesize_scene_audio_retries_once_then_succeeds(tmp_path):
    client = _FakeHttpxClient(
        [_FakeResponse(500, text="server error"), _FakeResponse(200, content=b"OK")]
    )
    output_path = str(tmp_path / "scene_1.mp3")

    tts.synthesize_scene_audio("텍스트", output_path, client=client)

    assert client.calls == 2


def test_synthesize_scene_audio_raises_after_two_failures(tmp_path):
    client = _FakeHttpxClient([_FakeResponse(500, text="err"), _FakeResponse(500, text="err")])
    output_path = str(tmp_path / "scene_1.mp3")

    with pytest.raises(tts.TTSError):
        tts.synthesize_scene_audio("텍스트", output_path, client=client)

    assert client.calls == 2


def test_missing_api_key_raises_clear_error(monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "ELEVENLABS_API_KEY", "")
    with pytest.raises(tts.TTSError, match="ELEVENLABS_API_KEY"):
        tts.synthesize_scene_audio("텍스트", str(tmp_path / "out.mp3"))


@pytest.mark.skipif(
    subprocess.run(["ffprobe", "-version"], capture_output=True).returncode != 0,
    reason="ffprobe not available in this environment",
)
def test_get_audio_duration_sec_measures_real_file(tmp_path):
    silent_path = str(tmp_path / "silence.wav")
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
            "-t", "2", silent_path,
        ],
        capture_output=True,
        check=True,
    )

    duration = tts.get_audio_duration_sec(silent_path)

    assert 1.9 <= duration <= 2.1
