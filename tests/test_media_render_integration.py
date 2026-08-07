"""실제 ffmpeg/ffprobe로 2-scene 영상을 끝까지 조립해 규격을 검증한다.

ElevenLabs API 키가 없어 실제 TTS 대신 ffmpeg의 무음(anullsrc) 클립을 오디오로 쓴다 —
Ken Burns/자막 번인/규격(해상도·코덱·fps)·고지 오버레이 타이밍은 오디오 출처와 무관하게
동일한 파이프라인을 타므로 이 부분의 검증에는 지장이 없다. 실제 TTS 연동 자체는
tests/test_media_tts.py에서 fake client로 별도 검증한다.
"""

import json
import subprocess

import pytest

from app.media.graphics import compose_educational_note_scene
from app.media.images import compose_scene_image, save_jpeg
from app.media.render import (
    compute_scene_windows,
    concat_clips,
    concat_clips_with_transitions,
    mix_bgm,
    pad_audio_with_silence,
    recomposite_captions,
    render_scene_clip,
    resolve_font_path,
    speed_up_audio,
)
from PIL import Image

FFMPEG_AVAILABLE = subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode == 0


def _make_silence(path: str, duration_sec: float) -> str:
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
            "-t", str(duration_sec), path,
        ],
        capture_output=True,
        check=True,
    )
    return path


def _ffprobe_json(path: str) -> dict:
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not available in this environment")
def test_full_two_scene_render_matches_spec(tmp_path):
    work_dir = str(tmp_path)

    scene1_img = compose_scene_image(_synthetic_jpeg_bytes((255, 120, 80)))
    scene1_path = save_jpeg(scene1_img, f"{work_dir}/scene1.jpg")

    scene2_img = compose_educational_note_scene((1080, 1920), category="자외선차단제")
    scene2_path = save_jpeg(scene2_img, f"{work_dir}/scene2.jpg")

    audio1 = _make_silence(f"{work_dir}/audio1.wav", 2.0)
    audio2 = _make_silence(f"{work_dir}/audio2.wav", 3.0)

    clip1 = render_scene_clip(
        scene1_path, audio1, 2.0, "요즘 자꾸 새벽에 깨시나요?", f"{work_dir}/clip1.mp4", work_dir,
    )
    clip2 = render_scene_clip(
        scene2_path, audio2, 3.0, "제품정보는 본문에 있어요, 확인해보세요.",
        f"{work_dir}/clip2.mp4", work_dir,
        disclosure_text="이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.",
    )

    concatenated = concat_clips(
        [clip1, clip2], f"{work_dir}/list.txt", f"{work_dir}/concatenated.mp4"
    )
    final_path = mix_bgm(concatenated, None, f"{work_dir}/final.mp4")

    probe = _ffprobe_json(final_path)
    video_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    audio_stream = next(s for s in probe["streams"] if s["codec_type"] == "audio")

    assert video_stream["width"] == 1080
    assert video_stream["height"] == 1920
    assert video_stream["codec_name"] == "h264"
    assert video_stream["pix_fmt"] == "yuv420p"
    assert audio_stream is not None

    total_duration = float(probe["format"]["duration"])
    assert 4.7 <= total_duration <= 5.3  # 2s + 3s 씬 합계 ±0.3


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not available in this environment")
def test_base_video_then_recomposite_matches_original_render_spec(tmp_path):
    """캡션 없는 base.mp4를 만들고 recomposite_captions로 자막을 입히는 2단계 파이프라인이,
    기존 단일 패스(render_scene_clip이 자막까지 바로 굽던 방식)와 동일한 규격(h264/yuv420p/
    1080x1920/30fps)의 영상을 만드는지 확인한다 — 캡션 편집기 재합성 경로의 회귀 가드."""
    work_dir = str(tmp_path)

    scene1_img = compose_scene_image(_synthetic_jpeg_bytes((255, 120, 80)))
    scene1_path = save_jpeg(scene1_img, f"{work_dir}/scene1.jpg")
    scene2_img = compose_educational_note_scene((1080, 1920), category="자외선차단제")
    scene2_path = save_jpeg(scene2_img, f"{work_dir}/scene2.jpg")

    audio1 = _make_silence(f"{work_dir}/audio1.wav", 2.0)
    audio2 = _make_silence(f"{work_dir}/audio2.wav", 3.0)

    # 씬 클립은 자막 없이(빈 문자열) 만든다 — render_script()가 실제로 하는 것과 동일.
    clip1 = render_scene_clip(scene1_path, audio1, 2.0, "", f"{work_dir}/clip1.mp4", work_dir)
    clip2 = render_scene_clip(scene2_path, audio2, 3.0, "", f"{work_dir}/clip2.mp4", work_dir)

    base_video = concat_clips_with_transitions([clip1, clip2], [2.0, 3.0], f"{work_dir}/base.mp4")
    base_video = mix_bgm(base_video, None, f"{work_dir}/base_bgm.mp4")

    scenes = [
        {"seq": 1, "stage": "empathy", "caption": "요즘 자꾸 새벽에 깨시나요?"},
        {"seq": 2, "stage": "product", "caption": "제품정보는 본문에 있어요, 확인해보세요."},
    ]
    timeline = compute_scene_windows([2.0, 3.0], [1, 2])
    final_path = recomposite_captions(
        base_video, timeline, scenes,
        "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.",
        resolve_font_path(), work_dir, f"{work_dir}/final.mp4",
    )

    probe = _ffprobe_json(final_path)
    video_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    audio_stream = next(s for s in probe["streams"] if s["codec_type"] == "audio")

    assert video_stream["width"] == 1080
    assert video_stream["height"] == 1920
    assert video_stream["codec_name"] == "h264"
    assert video_stream["pix_fmt"] == "yuv420p"
    assert audio_stream is not None

    total_duration = float(probe["format"]["duration"])
    assert 4.2 <= total_duration <= 5.3  # 크로스페이드로 살짝 짧아질 수 있음


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not available in this environment")
def test_pad_audio_with_silence_extends_duration_by_gap(tmp_path):
    work_dir = str(tmp_path)
    audio = _make_silence(f"{work_dir}/audio.wav", 2.0)
    padded = pad_audio_with_silence(audio, 1.0, f"{work_dir}/padded.wav")

    probe = _ffprobe_json(padded)
    duration = float(probe["format"]["duration"])
    assert 2.9 <= duration <= 3.1  # 2s 원본 + 1s 패딩


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not available in this environment")
def test_speed_up_audio_shortens_duration_by_speed_factor(tmp_path):
    work_dir = str(tmp_path)
    audio = _make_silence(f"{work_dir}/audio.wav", 5.0)
    sped = speed_up_audio(audio, f"{work_dir}/sped.wav", speed=1.1)

    probe = _ffprobe_json(sped)
    duration = float(probe["format"]["duration"])
    assert 4.4 <= duration <= 4.6  # 5s / 1.1 ≈ 4.545s


def _synthetic_jpeg_bytes(color) -> bytes:
    from io import BytesIO

    img = Image.new("RGB", (1200, 900), color)
    buf = BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()
