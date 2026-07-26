import base64
import subprocess

import pytest

from app.media import tts


def _fake_alignment_json(audio_bytes: bytes, words: list[str]) -> dict:
    """/with-timestamps 응답 형태(글자 단위 정렬 포함)를 흉내낸다."""
    characters = []
    starts = []
    ends = []
    t = 0.0
    for i, word in enumerate(words):
        for ch in word:
            characters.append(ch)
            starts.append(t)
            t += 0.1
            ends.append(t)
        if i < len(words) - 1:
            characters.append(" ")
            starts.append(t)
            t += 0.05
            ends.append(t)
    return {
        "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
        "alignment": {
            "characters": characters,
            "character_start_times_seconds": starts,
            "character_end_times_seconds": ends,
        },
    }


class _FakeResponse:
    def __init__(self, status_code: int, content: bytes = b"", text: str = "", json_body: dict | None = None):
        self.status_code = status_code
        self.content = content
        self.text = text
        self._json_body = json_body

    def json(self):
        return self._json_body


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
    client = _FakeHttpxClient(
        [_FakeResponse(200, json_body=_fake_alignment_json(b"FAKE_MP3_BYTES", ["안녕하세요"]))]
    )
    output_path = str(tmp_path / "scene_1.mp3")

    result_path = tts.synthesize_scene_audio(
        "안녕하세요", output_path, client=client, provider="elevenlabs"
    )

    assert result_path == output_path
    assert open(output_path, "rb").read() == b"FAKE_MP3_BYTES"
    assert client.calls == 1


def test_elevenlabs_synthesize_script_audio_includes_real_word_timings(monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "get_audio_duration_sec", lambda path: 1.5)
    client = _FakeHttpxClient(
        [_FakeResponse(200, json_body=_fake_alignment_json(b"AUDIO", ["안녕", "반가워요"]))]
    )
    scenes = [{"seq": 1, "narration": "안녕 반가워요", "caption": "인사"}]

    results = tts.synthesize_script_audio(scenes, str(tmp_path), client=client, provider="elevenlabs")

    timings = results[0]["word_timings"]
    assert [w[0] for w in timings] == ["안녕", "반가워요"]
    assert timings[0][1] == 0.0  # 첫 단어는 0초부터 시작


def test_elevenlabs_retries_once_then_succeeds(tmp_path):
    client = _FakeHttpxClient(
        [_FakeResponse(500, text="server error"), _FakeResponse(200, json_body=_fake_alignment_json(b"OK", ["텍스트"]))]
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


def test_omitting_provider_falls_back_to_configured_default(monkeypatch, tmp_path):
    # provider 인자를 생략하면 app.config.TTS_PROVIDER 값을 따른다 — 실행 환경의 .env가
    # 무엇으로 설정돼 있든(edge/elevenlabs) 테스트는 그 값에 영향받지 않도록 여기서
    # 직접 고정한다(전엔 실제 .env의 TTS_PROVIDER를 그대로 흡수해서, 배포 기본값을
    # elevenlabs로 바꾸자 이 테스트가 실제 네트워크를 호출해버리는 버그가 있었다).
    monkeypatch.setattr(tts, "TTS_PROVIDER", "edge")
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


# --- 단어 타이밍 그룹핑 ---


def test_group_word_timings_splits_on_spaces():
    alignment = _fake_alignment_json(b"", ["안녕", "반가워요"])["alignment"]
    words = tts._group_word_timings(alignment)
    assert [w[0] for w in words] == ["안녕", "반가워요"]
    assert words[0][1] == 0.0
    assert words[0][2] < words[1][1]  # 첫 단어 끝 <= 둘째 단어 시작


def test_group_word_timings_empty_alignment_returns_empty_list():
    assert tts._group_word_timings({}) == []
