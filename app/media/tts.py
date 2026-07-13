"""4호 직원 — TTS (Phase 3).

ElevenLabs로 scene별 내레이션을 mp3로 생성하고, ffprobe로 실제 길이를 측정한다.
렌더링 타이밍 기준은 대본의 duration_sec이 아니라 이 실측값이다(docs/phase3_spec.md).
"""

from __future__ import annotations

import subprocess
import time

import httpx

from app.config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID

BASE_URL = "https://api.elevenlabs.io/v1/text-to-speech"
DEFAULT_MODEL_ID = "eleven_multilingual_v2"


class TTSError(RuntimeError):
    """TTS 생성/길이 측정 실패를 감싸는 명확한 예외."""


def synthesize_scene_audio(
    text: str,
    output_path: str,
    voice_id: str | None = None,
    client: httpx.Client | None = None,
) -> str:
    """텍스트를 mp3로 합성해 output_path에 저장하고 경로를 반환한다."""
    active_voice_id = voice_id or ELEVENLABS_VOICE_ID
    if not ELEVENLABS_API_KEY:
        raise TTSError("ELEVENLABS_API_KEY가 설정되지 않았습니다.")
    if not active_voice_id:
        raise TTSError("ELEVENLABS_VOICE_ID가 설정되지 않았습니다.")

    url = f"{BASE_URL}/{active_voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    body = {
        "text": text,
        "model_id": DEFAULT_MODEL_ID,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
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
            with open(output_path, "wb") as f:
                f.write(response.content)
            return output_path
        except (httpx.HTTPError, TTSError) as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.5)
                continue

    raise TTSError(f"TTS 생성 실패: {last_error}") from last_error


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
) -> list[dict]:
    """scenes 각각을 mp3로 합성하고 실측 길이를 붙여 반환한다.

    반환값: [{"seq": int, "path": str, "duration_sec": float}, ...]
    """
    results = []
    for scene in scenes:
        seq = scene["seq"]
        output_path = f"{output_dir}/scene_{seq}.mp3"
        synthesize_scene_audio(scene["narration"], output_path, voice_id=voice_id, client=client)
        duration = get_audio_duration_sec(output_path)
        results.append({"seq": seq, "path": output_path, "duration_sec": duration})
    return results
