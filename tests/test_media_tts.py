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


class _FakeCommunicate:
    """edge_tts.Communicate를 흉내내는 가짜 — 실제 네트워크 호출 없이 파일만 쓴다."""

    instances: list["_FakeCommunicate"] = []

    def __init__(self, text, voice):
        self.text = text
        self.voice = voice
        _FakeCommunicate.instances.append(self)

    async def save(self, path):
        with open(path, "wb") as f:
            f.write(b"FAKE_EDGE_AUDIO")


class _FailingCommunicate:
    def __init__(self, text, voice):
        pass

    async def save(self, path):
        raise RuntimeError("edge-tts 서버 오류(가짜)")


@pytest.fixture(autouse=True)
def _fake_elevenlabs_credentials(monkeypatch):
    monkeypatch.setattr(tts, "ELEVENLABS_API_KEY", "fake-key")
    monkeypatch.setattr(tts, "ELEVENLABS_VOICE_ID", "fake-voice")


@pytest.fixture(autouse=True)
def _reset_fake_communicate_log():
    _FakeCommunicate.instances.clear()
    yield
    _FakeCommunicate.instances.clear()


# --- ElevenLabs 경로 ---


def test_elevenlabs_synthesize_scene_audio_writes_file(tmp_path):
    client = _FakeHttpxClient([_FakeResponse(200, content=b"FAKE_MP3_BYTES")])
    output_path = str(tmp_path / "scene_1.mp3")

    result_path = tts.synthesize_scene_audio(
        "안녕하세요", output_path, client=client, provider="elevenlabs"
    )

    assert result_path == output_path
    assert open(output_path, "rb").read() == b"FAKE_MP3_BYTES"
    assert client.calls == 1


def test_elevenlabs_retries_once_then_succeeds(tmp_path):
    client = _FakeHttpxClient(
        [_FakeResponse(500, text="server error"), _FakeResponse(200, content=b"OK")]
    )
    output_path = str(tmp_path / "scene_1.mp3")

    tts.synthesize_scene_audio(
        "텍스트", output_path, client=client, provider="elevenlabs"
    )

    assert client.calls == 2


def test_elevenlabs_raises_after_two_failures(tmp_path):
    client = _FakeHttpxClient([_FakeResponse(500, text="err"), _FakeResponse(500, text="err")])
    output_path = str(tmp_path / "scene_1.mp3")

    with pytest.raises(tts.TTSError):
        tts.synthesize_scene_audio("텍스트", output_path, client=client, provider="elevenlabs")

    assert client.calls == 2


def test_elevenlabs_missing_api_key_raises_clear_error(monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "ELEVENLABS_API_KEY", "")
    with pytest.raises(tts.TTSError, match="ELEVENLABS_API_KEY"):
        tts.synthesize_scene_audio("텍스트", str(tmp_path / "out.mp3"), provider="elevenlabs")


# --- edge-tts 경로 ---


def test_edge_synthesize_scene_audio_writes_file(tmp_path):
    output_path = str(tmp_path / "scene_1.mp3")

    result_path = tts.synthesize_scene_audio(
        "안녕하세요", output_path, provider="edge", communicate_factory=_FakeCommunicate
    )

    assert result_path == output_path
    assert open(output_path, "rb").read() == b"FAKE_EDGE_AUDIO"
    assert len(_FakeCommunicate.instances) == 1
    assert _FakeCommunicate.instances[0].voice == "ko-KR-SunHiNeural"  # config 기본값


def test_edge_uses_voice_id_as_voice_name(tmp_path):
    output_path = str(tmp_path / "scene_1.mp3")

    tts.synthesize_scene_audio(
        "안녕하세요",
        output_path,
        voice_id="ko-KR-InJoonNeural",
        provider="edge",
        communicate_factory=_FakeCommunicate,
    )

    assert _FakeCommunicate.instances[0].voice == "ko-KR-InJoonNeural"


def test_edge_retries_once_then_raises_after_two_failures(tmp_path):
    output_path = str(tmp_path / "scene_1.mp3")
    with pytest.raises(tts.TTSError, match="edge-tts"):
        tts.synthesize_scene_audio(
            "텍스트", output_path, provider="edge", communicate_factory=_FailingCommunicate
        )


def test_default_provider_is_edge(tmp_path):
    # app.config.TTS_PROVIDER 기본값이 "edge" — provider 인자를 생략해도 edge 경로를 탄다.
    output_path = str(tmp_path / "scene_1.mp3")
    tts.synthesize_scene_audio(
        "텍스트", output_path, communicate_factory=_FakeCommunicate
    )
    assert len(_FakeCommunicate.instances) == 1


def test_unknown_provider_raises_clear_error(tmp_path):
    with pytest.raises(tts.TTSError, match="TTS_PROVIDER"):
        tts.synthesize_scene_audio(
            "텍스트", str(tmp_path / "out.mp3"), provider="not-a-real-provider"
        )


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


@pytest.mark.skipif(
    subprocess.run(["ffprobe", "-version"], capture_output=True).returncode != 0,
    reason="ffprobe not available in this environment",
)
def test_edge_tts_real_call_produces_playable_audio(tmp_path):
    """실제 edge-tts 서버로 한국어 문장을 합성해 진짜 오디오가 나오는지 확인한다 (네트워크 필요, API 키 불필요)."""
    output_path = str(tmp_path / "real.mp3")
    tts.synthesize_scene_audio("안녕하세요, 테스트 음성입니다.", output_path, provider="edge")

    duration = tts.get_audio_duration_sec(output_path)
    assert duration > 0.5
