"""4호 직원 — TTS (Phase 3).

scene별 내레이션을 mp3로 생성하고, ffprobe로 실제 길이를 측정한다.
렌더링 타이밍 기준은 대본의 duration_sec이 아니라 이 실측값이다(docs/phase3_spec.md).

두 공급자를 지원한다 (app.config.TTS_PROVIDER로 선택):
- "elevenlabs": 공식 REST API. 계정 플랜에 따라 라이브러리 보이스가 API로 막힐 수 있다
  (docs/01_plan.md 2026-07-13 이력 참조).
- "edge" (기본값): Microsoft Edge 읽어주기 기능의 비공식 클라이언트(edge-tts 패키지).
  키가 필요 없고 한국어 뉴럴 보이스 품질도 준수하지만, 공식 API가 아니므로 공지 없이
  막힐 수 있다는 리스크가 있다 — 다만 TTS 실패는 쿠팡 계정 정지 같은 치명적 리스크와는
  무관해 Suno를 배제한 것과 같은 수준의 금지 사유는 아니라고 판단해 기본값으로 채택했다.
"""

from __future__ import annotations

import asyncio
import base64
import subprocess
import time

import httpx

from app.config import (
    EDGE_TTS_VOICE,
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
    TTS_PROVIDER,
)

ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1/text-to-speech"
ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"

WordTiming = tuple[str, float, float]


class TTSError(RuntimeError):
    """TTS 생성/길이 측정 실패를 감싸는 명확한 예외."""


def _group_word_timings(alignment: dict) -> list[WordTiming]:
    """ElevenLabs의 글자 단위 정렬 데이터를 단어 단위 (word, start, end) 리스트로 묶는다."""
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []

    words: list[WordTiming] = []
    word = ""
    word_start: float | None = None
    word_end: float | None = None
    for ch, start, end in zip(chars, starts, ends):
        if ch.isspace():
            if word:
                words.append((word, word_start, word_end))
                word = ""
                word_start = None
        else:
            if word_start is None:
                word_start = start
            word += ch
            word_end = end
    if word:
        words.append((word, word_start, word_end))
    return words


def _synthesize_with_elevenlabs(
    text: str,
    output_path: str,
    voice_id: str | None = None,
    client: httpx.Client | None = None,
) -> tuple[str, list[WordTiming] | None]:
    """ElevenLabs로 합성한다. /with-timestamps 엔드포인트를 써서 실제 단어별 타이밍도
    함께 받아온다 — edge-tts(문장 단위만 지원)와 달리 자막을 실제 발화에 정확히 맞출 수 있다.
    """
    active_voice_id = voice_id or ELEVENLABS_VOICE_ID
    if not ELEVENLABS_API_KEY:
        raise TTSError("ELEVENLABS_API_KEY가 설정되지 않았습니다.")
    if not active_voice_id:
        raise TTSError("ELEVENLABS_VOICE_ID가 설정되지 않았습니다.")

    url = f"{ELEVENLABS_BASE_URL}/{active_voice_id}/with-timestamps"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    body = {
        "text": text,
        "model_id": ELEVENLABS_MODEL_ID,
        # stability를 낮추고 style을 살짝 줘서 억양 기복이 있는 더 자연스러운 낭독 톤으로
        # 조정했다(기존 stability=0.5/style 없음은 다소 단조롭게 들렸다).
        "voice_settings": {
            "stability": 0.45,
            "similarity_boost": 0.8,
            "style": 0.35,
            "use_speaker_boost": True,
        },
    }

    last_error: Exception | None = None
    for attempt in range(2):  # 최초 시도 + 재시도 1회 (AGENTS.md 코딩 컨벤션)
        try:
            if client is not None:
                response = client.post(url, headers=headers, json=body)
            else:
                with httpx.Client(timeout=30.0) as default_client:
                    response = default_client.post(url, headers=headers, json=body)
            if response.status_code >= 400:
                raise TTSError(f"ElevenLabs TTS 오류 (status={response.status_code}): {response.text[:300]}")
            data = response.json()
            audio_bytes = base64.b64decode(data["audio_base64"])
            with open(output_path, "wb") as f:
                f.write(audio_bytes)
            word_timings = _group_word_timings(data.get("alignment") or {}) or None
            return output_path, word_timings
        except (httpx.HTTPError, TTSError, KeyError, ValueError) as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.5)
                continue

    raise TTSError(f"ElevenLabs TTS 생성 실패: {last_error}") from last_error


def _default_edge_communicate_factory():
    import edge_tts

    return edge_tts.Communicate


def _synthesize_with_edge(
    text: str,
    output_path: str,
    voice: str | None = None,
    communicate_factory=None,
) -> str:
    active_voice = voice or EDGE_TTS_VOICE
    factory = communicate_factory or _default_edge_communicate_factory()

    last_error: Exception | None = None
    for attempt in range(2):  # 최초 시도 + 재시도 1회 (AGENTS.md 코딩 컨벤션)
        try:
            communicate = factory(text, active_voice)
            asyncio.run(communicate.save(output_path))
            return output_path
        except Exception as exc:  # noqa: BLE001 — edge-tts는 다양한 예외를 던져 넓게 잡는다
            last_error = exc
            if attempt == 0:
                time.sleep(0.5)
                continue

    raise TTSError(f"edge-tts 생성 실패: {last_error}") from last_error


def _synthesize_scene_audio_with_timings(
    text: str,
    output_path: str,
    voice_id: str | None = None,
    client: httpx.Client | None = None,
    provider: str | None = None,
    communicate_factory=None,
) -> tuple[str, list[WordTiming] | None]:
    """provider별 합성을 실행하고 (경로, 단어별 타이밍) 튜플로 통일해서 돌려준다.

    edge-tts는 단어 타이밍을 안 주므로 항상 None. 현재 렌더 파이프라인(app/media/worker.py,
    render.py)은 word_timings를 자막 표시에 쓰지 않지만(문장 전체를 한 번에 보여주는
    방식으로 바뀜), 이 함수는 duration_sec을 함께 반환하는 통일된 인터페이스라 그대로 둔다.
    """
    active_provider = provider or TTS_PROVIDER
    if active_provider == "edge":
        path = _synthesize_with_edge(text, output_path, voice=voice_id, communicate_factory=communicate_factory)
        return path, None
    if active_provider == "elevenlabs":
        return _synthesize_with_elevenlabs(text, output_path, voice_id=voice_id, client=client)
    raise TTSError(f"알 수 없는 TTS_PROVIDER: {active_provider!r} (elevenlabs 또는 edge만 지원)")


def synthesize_scene_audio(
    text: str,
    output_path: str,
    voice_id: str | None = None,
    client: httpx.Client | None = None,
    provider: str | None = None,
    communicate_factory=None,
) -> str:
    """텍스트를 mp3로 합성해 output_path에 저장하고 경로를 반환한다.

    provider가 없으면 app.config.TTS_PROVIDER를 따른다. voice_id는 공급자별 의미가
    다르다(ElevenLabs: voice_id, edge: "ko-KR-SunHiNeural" 같은 보이스 이름).
    """
    path, _ = _synthesize_scene_audio_with_timings(
        text, output_path, voice_id=voice_id, client=client, provider=provider, communicate_factory=communicate_factory
    )
    return path


def get_audio_duration_sec(path: str) -> float:
    """ffprobe로 오디오 파일의 실제 길이(초)를 측정한다."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError) as exc:
        raise TTSError(f"오디오 길이 측정 실패 ({path}): {exc}") from exc


def synthesize_script_audio(
    scenes: list[dict],
    output_dir: str,
    voice_id: str | None = None,
    client: httpx.Client | None = None,
    provider: str | None = None,
    communicate_factory=None,
) -> list[dict]:
    """scenes 각각을 mp3로 합성하고 실측 길이 + (있으면) 단어별 타이밍을 붙여 반환한다.

    반환값: [{"seq": int, "path": str, "duration_sec": float, "word_timings": list | None}, ...]
    word_timings는 ElevenLabs일 때만 채워진다(edge-tts는 단어 단위 타임스탬프 미지원).
    """
    results = []
    for scene in scenes:
        seq = scene["seq"]
        output_path = f"{output_dir}/scene_{seq}.mp3"
        _, word_timings = _synthesize_scene_audio_with_timings(
            scene["narration"],
            output_path,
            voice_id=voice_id,
            client=client,
            provider=provider,
            communicate_factory=communicate_factory,
        )
        duration = get_audio_duration_sec(output_path)
        results.append({"seq": seq, "path": output_path, "duration_sec": duration, "word_timings": word_timings})
    return results
