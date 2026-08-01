"""5호 직원 — render_jobs 폴링 워커 (Phase 3).

queued -> generating_images -> generating_audio -> assembling -> done/failed
상태 전이를 관리하며, 실제 이미지/TTS/FFmpeg 조립을 오케스트레이션한다.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from app.db import get_client
from app.media.graphics import compose_educational_note_scene
from app.media.image_generator import ImageGenerationError, generate_scene_image
from app.media.images import compose_scene_image, download_image, guess_media_type, save_jpeg
from app.media.render import (
    CAPTION_BOTTOM_MARGIN,
    CAPTION_FONTSIZE,
    CTA_CAPTION_BOTTOM_MARGIN,
    CTA_CAPTION_FONTSIZE,
    CTA_CAPTION_LINE_HEIGHT,
    HEIGHT,
    TEXT_LINE_HEIGHT,
    WIDTH,
    RenderError,
    calc_narration_speed,
    concat_clips_with_transitions,
    mix_bgm,
    pad_audio_with_silence,
    pick_bgm_track,
    render_scene_clip,
    render_video_scene_clip,
    resolve_font_path,
    speed_up_audio,
)
from app.media.tts import TTSError, synthesize_script_audio
from app.media.video_generator import VideoGenerationError, generate_scene_video

WORK_ROOT_DEFAULT = "renders"
# 씬(단락)이 곧바로 이어져 나레이션이 부자연스럽던 문제 — 각 씬 사이에 숨 고를 무음
# 구간을 넣는다. 크로스페이드 전환 시간(TRANSITION_DURATION_SEC=0.4)보다 커야 실제
# 목소리끼리 겹치지 않는다.
SCENE_GAP_SEC = 1.0

# 대본 구조(app/script/prompts.py) 중 아직 상품이 등장하면 안 되는 "문제 상황" 단계 —
# 이 단계 씬은 상품 참고 이미지를 넘기지 않는다(사용자 피드백: 광고 대상 상품이 문제
# 상황 장면에 잘못 등장함). solution 단계부터가 실제 상품이 해결책으로 "공개"되는 지점.
PRE_REVEAL_STAGES = {"empathy", "emotion", "problem"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scene_uses_educational_graphic(scene_narration: str, educational_note_text: str) -> bool:
    """이 씬의 narration이 사실설명(educational_note) 내용을 담고 있는지 대략 판별한다.

    Phase 2 대본은 educational_note를 별도 scene으로 분리하지 않고 problem 단계
    scene의 narration에 자연스럽게 녹여 쓰는 경우가 많다(실제 생성 샘플로 확인).
    그 scene을 실사 상품 사진 대신 2D 그래픽(사실 카드)으로 렌더링한다.
    """
    if not educational_note_text or not scene_narration:
        return False
    snippet = educational_note_text[:20]
    return snippet in scene_narration or scene_narration in educational_note_text


def build_scene_image(
    scene: dict,
    product: dict,
    script_json: dict,
    work_dir: str,
    character_ref: tuple[bytes, str] | None = None,
) -> tuple[str, tuple[bytes, str] | None]:
    """씬 하나의 배경 이미지를 결정해 JPEG로 저장하고, (경로, 갱신된 character_ref)를 반환한다.

    character_ref는 이 영상에서 처음 생성에 성공한 이미지를 담아뒀다가 이후 씬 생성 때마다
    함께 참고 이미지로 넘긴다 — 씬마다 독립적으로 생성하면 등장인물이 매번 다른 사람으로
    바뀌는 문제(사용자 피드백)가 있어서, 같은 인물이 이어지도록 유도한다.

    scene["stage"]가 PRE_REVEAL_STAGES(공감/문제 단계)에 속하면 상품 참고 이미지를 넘기지
    않는다 — 광고 대상 상품이 아직 해결책으로 등장하면 안 되는 "문제 상황" 장면에 그대로
    나와버리는 문제(사용자 피드백)가 있었다.
    """
    educational_text = (script_json.get("educational_note") or {}).get("text", "")
    use_graphic = _scene_uses_educational_graphic(scene.get("narration", ""), educational_text)

    image_urls = product.get("image_urls") or []
    category = product.get("category")
    is_pre_reveal = scene.get("stage") in PRE_REVEAL_STAGES

    if use_graphic or not image_urls:
        composed = compose_educational_note_scene((WIDTH, HEIGHT), category=category)
    else:
        idx = scene.get("image_index", 0) % len(image_urls)
        reference_bytes = download_image(image_urls[idx])
        product_reference = None if is_pre_reveal else (reference_bytes, guess_media_type(reference_bytes))
        # 실사 사진을 참고 이미지로 Gemini에 넣어, 상품의 실제 모습은 유지하면서 그 씬의
        # 화면 연출(visual)에 맞는 장면으로 재구성한다 — 실사 사진 그대로 쓰면 판매
        # 리스팅에 이미 박힌 타 마케팅 문구가 함께 찍히고, 화면 연출과 안 맞는 경우가 많아서
        # 도입했다(사용자 피드백).
        try:
            image_bytes, media_type = generate_scene_image(
                scene.get("visual", ""),
                scene.get("narration", ""),
                product.get("product_name", ""),
                product_reference=product_reference,
                character_reference=character_ref,
            )
            if character_ref is None:
                character_ref = (image_bytes, media_type)
            composed = compose_scene_image(image_bytes)
        except ImageGenerationError:
            if is_pre_reveal:
                # 생성 실패 폴백으로 실사 상품 사진을 쓰면 광고 대상 상품이 "문제 상황"
                # 장면에 등장해버리는 원래 문제가 재발한다 — 2D 그래픽 카드로 대신한다.
                composed = compose_educational_note_scene((WIDTH, HEIGHT), category=category)
            else:
                composed = compose_scene_image(reference_bytes)

    path = os.path.join(work_dir, f"scene_{scene['seq']}.jpg")
    return save_jpeg(composed, path), character_ref


def build_scene_video(scene: dict, image_path: str, work_dir: str) -> str | None:
    """이미 만든 씬 스틸컷(image_path)을 시작 프레임으로 Veo 영상을 생성해 저장한다.

    실패하면(시간 초과, API 오류 등) None을 반환한다 — 호출부가 기존 정지 이미지+Ken Burns
    방식으로 폴백한다. 몇 분씩 걸릴 수 있는 작업 전체를 재시도하면 렌더링이 너무 오래 걸려서
    generate_scene_video 자체엔 재시도가 없다. 어느 씬에 적용할지는 호출부(render_script)가
    정한다 — 정지 사진+팬만으로는 일부 씬이 어색해 보인다는 피드백으로, 우선 임팩트가 가장
    큰 후킹(첫 씬)에만 시범 적용하기로 했다(사용자와 논의해 범위 확정).
    """
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    try:
        video_bytes = generate_scene_video(image_bytes, "image/jpeg", scene.get("visual", ""), scene.get("narration", ""))
    except VideoGenerationError:
        return None
    path = os.path.join(work_dir, f"scene_{scene['seq']}.mp4")
    with open(path, "wb") as f:
        f.write(video_bytes)
    return path


def render_script(
    script_json: dict,
    product: dict,
    work_dir: str,
    status_callback=None,
    tts_client=None,
    font_path: str | None = None,
) -> str:
    """script_json + product 정보로 완성 mp4를 만들어 경로를 반환한다."""
    os.makedirs(work_dir, exist_ok=True)
    font = font_path or resolve_font_path()
    scenes = script_json["scenes"]

    if status_callback:
        status_callback("generating_images")
    last_seq = scenes[-1]["seq"]
    first_seq = scenes[0]["seq"]
    image_paths = {}
    character_ref: tuple[bytes, str] | None = None
    for scene in scenes:
        path, character_ref = build_scene_image(scene, product, script_json, work_dir, character_ref)
        image_paths[scene["seq"]] = path

    # 후킹(첫 씬)만 시범적으로 실제 영상(Veo)으로 애니메이션한다 — 몇 분 걸릴 수 있어 별도
    # 상태 단계로 알린다. 실패하면 video_paths에 안 담기고, 아래 조립 루프가 기존 정지
    # 이미지+Ken Burns 방식으로 자동 폴백한다.
    if status_callback:
        status_callback("generating_video")
    video_paths: dict[int, str] = {}
    first_scene = scenes[0]
    video_path = build_scene_video(first_scene, image_paths[first_seq], work_dir)
    if video_path:
        video_paths[first_seq] = video_path

    if status_callback:
        status_callback("generating_audio")
    audio_results = synthesize_script_audio(scenes, work_dir, client=tts_client)
    audio_by_seq = {a["seq"]: a for a in audio_results}

    if status_callback:
        status_callback("assembling")
    clip_paths = []
    clip_durations = []
    # 마지막 씬 caption은 이미 CTA 문구로 각색돼 있다 — 3단 레이아웃 절충안(사용자 피드백)의
    # 하단 상시노출 CTA 배너에 그대로 재사용한다.
    sticky_cta_source_text = scenes[-1]["caption"]
    for scene in scenes:
        seq = scene["seq"]
        clip_path = os.path.join(work_dir, f"clip_{seq}.mp4")
        actual_audio_duration = audio_by_seq[seq]["duration_sec"]
        # 대본이 이 씬에 계획한 시간(scene["duration_sec"])에 맞춰 배속을 조절한다 — 실제
        # 렌더링 길이가 대본작성 단계에서 잡은 씬별 시간 배분을 반영하게 하기 위함이다.
        # 계획과 실제 TTS 길이 차이가 너무 크면 부자연스러워지므로 자연스러운 범위로 clamp한다.
        speed = calc_narration_speed(actual_audio_duration, scene.get("duration_sec"))
        sped_path = os.path.join(work_dir, f"scene_{seq}_sped.mp3")
        audio_path = speed_up_audio(audio_by_seq[seq]["path"], sped_path, speed=speed)
        # atempo는 재생 속도를 정확히 배율만큼 바꾸는 결정적 필터라, ffprobe로 다시 재는
        # 대신 원래 길이를 배율로 나눠서 바로 계산한다.
        raw_duration = actual_audio_duration / speed

        if seq == last_seq:
            duration = raw_duration
        else:
            # 마지막 씬 뒤엔 이어질 나레이션이 없으니 패딩할 필요가 없다. 그 앞 씬들은
            # 끝에 무음을 붙여서, 다음 씬 목소리와 곧바로 이어붙지 않고 숨 고를 틈을 준다.
            padded_path = os.path.join(work_dir, f"scene_{seq}_padded.mp3")
            audio_path = pad_audio_with_silence(audio_path, SCENE_GAP_SEC, padded_path)
            duration = raw_duration + SCENE_GAP_SEC

        # 자막은 나레이션 원문이 아니라 짧게 각색된 caption 문구를 보여준다. 마지막 씬은
        # CTA 문구라 일반 자막보다 작게, 화면 더 아래쪽에 배치한다(사용자 피드백). 첫 씬은
        # 상단 후킹 문구로 같은 caption을 이미 보여주므로 하단 자막은 생략한다 — 위아래에
        # 똑같은 문장이 중복으로 뜨는 게 어색하다는 피드백.
        is_last = seq == last_seq
        is_first = seq == first_seq
        is_pre_reveal = scene.get("stage") in PRE_REVEAL_STAGES
        caption_text = "" if is_first else scene["caption"]
        hook_text = scene["caption"] if is_first else None
        # 상단(후킹+제품명)/중간(영상)/하단(자막+상시CTA) 3단 레이아웃 절충안(사용자 피드백).
        # 제품명은 후킹 씬에만, 상시 CTA 배너는 상품이 아직 등장하지 않는 pre-reveal 단계와
        # 이미 자체 CTA 자막인 마지막 씬을 제외한 나머지 씬에만 보여준다.
        product_name = product.get("product_name") if is_first else None
        sticky_cta_text = None if (is_first or is_last or is_pre_reveal) else sticky_cta_source_text
        caption_kwargs = dict(
            caption_fontsize=CTA_CAPTION_FONTSIZE if is_last else CAPTION_FONTSIZE,
            caption_bottom_margin=CTA_CAPTION_BOTTOM_MARGIN if is_last else CAPTION_BOTTOM_MARGIN,
            caption_line_height=CTA_CAPTION_LINE_HEIGHT if is_last else TEXT_LINE_HEIGHT,
        )
        if seq in video_paths:
            render_video_scene_clip(
                video_paths[seq],
                audio_path,
                duration,
                caption_text,
                clip_path,
                work_dir,
                font_path=font,
                hook_text=hook_text,
                product_name=product_name,
                sticky_cta_text=sticky_cta_text,
                **caption_kwargs,
            )
        else:
            render_scene_clip(
                image_paths[seq],
                audio_path,
                duration,
                caption_text,
                clip_path,
                work_dir,
                font_path=font,
                disclosure_text=script_json["disclosure"] if is_last else None,
                hook_text=hook_text,
                product_name=product_name,
                sticky_cta_text=sticky_cta_text,
                **caption_kwargs,
            )
        clip_paths.append(clip_path)
        clip_durations.append(duration)

    concatenated = concat_clips_with_transitions(
        clip_paths, clip_durations, os.path.join(work_dir, "concatenated.mp4")
    )
    bgm_path = pick_bgm_track()
    return mix_bgm(concatenated, bgm_path, os.path.join(work_dir, "final.mp4"))


def process_render_job(
    job_id: str, client=None, work_root: str = WORK_ROOT_DEFAULT, tts_client=None
) -> dict:
    """render_jobs 레코드 하나를 끝까지 처리한다 (성공/실패 모두 상태를 기록).

    tts_client는 테스트/개발 환경에서 ElevenLabs 대신 가짜 클라이언트를 주입하기 위한 것.
    """
    active_client = client or get_client()

    job_res = active_client.table("render_jobs").select("*").eq("id", job_id).execute()
    if not job_res.data:
        raise ValueError(f"render_job {job_id}를 찾을 수 없습니다.")
    job = job_res.data[0]

    script_res = active_client.table("scripts").select("*").eq("id", job["script_id"]).execute()
    if not script_res.data:
        raise ValueError(f"script {job['script_id']}를 찾을 수 없습니다.")
    script = script_res.data[0]

    product_res = active_client.table("products").select("*").eq("id", script["product_id"]).execute()
    if not product_res.data:
        raise ValueError(f"product {script['product_id']}를 찾을 수 없습니다.")
    product = product_res.data[0]

    work_dir = os.path.join(work_root, job_id)

    def _set_status(status: str) -> None:
        active_client.table("render_jobs").update({"status": status}).eq("id", job_id).execute()

    try:
        final_path = render_script(
            script["script_json"], product, work_dir, status_callback=_set_status, tts_client=tts_client
        )
        active_client.table("render_jobs").update(
            {"status": "done", "output_path": final_path, "finished_at": _now_iso()}
        ).eq("id", job_id).execute()
        active_client.table("products").update({"status": "media_generated"}).eq("id", product["id"]).execute()
        return {"status": "done", "output_path": final_path}
    except (RenderError, TTSError, Exception) as exc:  # noqa: BLE001 — 어떤 실패든 failed로 기록 후 재전파
        active_client.table("render_jobs").update(
            {"status": "failed", "error_message": str(exc)[:2000], "finished_at": _now_iso()}
        ).eq("id", job_id).execute()
        # products는 재시도 가능하도록 직전 단계로 롤백 (docs/phase3_checklist.md 8번)
        active_client.table("products").update({"status": "script_approved"}).eq("id", product["id"]).execute()
        raise


def poll_and_process_once(client=None, work_root: str = WORK_ROOT_DEFAULT) -> str | None:
    """queued 상태인 render_jobs 1건을 찾아 처리한다. 처리한 job_id 또는 None을 반환한다."""
    active_client = client or get_client()
    result = (
        active_client.table("render_jobs")
        .select("id")
        .eq("status", "queued")
        .order("created_at")
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    job_id = result.data[0]["id"]
    process_render_job(job_id, client=active_client, work_root=work_root)
    return job_id


def run_worker_loop(poll_interval_sec: int = 5, client=None, work_root: str = WORK_ROOT_DEFAULT) -> None:
    """Railway 등에서 별도 프로세스로 띄우는 폴링 루프 (Phase 4 배포 대상)."""
    active_client = client or get_client()
    while True:
        try:
            processed = poll_and_process_once(client=active_client, work_root=work_root)
            if not processed:
                time.sleep(poll_interval_sec)
        except Exception:  # noqa: BLE001 — 워커 프로세스는 개별 실패로 죽지 않아야 한다
            time.sleep(poll_interval_sec)


if __name__ == "__main__":
    run_worker_loop()
