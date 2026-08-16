"""5호 직원 — render_jobs 폴링 워커 (Phase 3, Phase 6/7에서 kind/target_seq 분기 추가).

render_jobs.kind로 세 종류를 구분한다:
- 'full'(기본값): 전체 렌더. queued -> generating_images -> generating_video ->
  generating_audio -> assembling -> done/failed (process_render_job).
- 'hook_preview': 씬 확인 단계 — `target_seq`(null이면 후킹/scenes[0]) 씬의 스틸컷(후킹이면
  영상까지)만 만들어 scripts 테이블에 저장한다. queued -> generating_images ->
  (후킹이면 generating_video ->) done/failed (process_hook_preview_job).
- 'hook_patch': 이미 완료된 render_job의 씬 하나(`target_seq`, null이면 후킹)만 다시 만든다.
  queued -> generating_images -> (후킹이면 generating_video ->) assembling -> done/failed
  (process_hook_patch_job).

후킹이 아닌 씬을 다루는 두 함수 모두, 인물 참조(character_ref)는 반드시 이미 확정된
후킹 이미지에서만 가져온다 — 씬마다 다른 사람으로 바뀌는 문제(사용자 피드백)를 막기 위해
다른 씬 이미지에서 파생하지 않는다.
"""

from __future__ import annotations

import os
import shutil
import time
from datetime import datetime, timezone

from app.db import get_client
from app.media.graphics import compose_educational_note_scene
from app.media.image_generator import ImageGenerationError, generate_scene_image
from app.media.images import compose_scene_image, download_image, guess_media_type, save_jpeg
from app.media.render import (
    HEIGHT,
    WIDTH,
    RenderError,
    calc_narration_speed,
    compute_scene_windows,
    concat_clips_with_transitions,
    mix_bgm,
    pad_audio_with_silence,
    pick_bgm_track,
    probe_duration_sec,
    recomposite_captions,
    render_scene_clip,
    render_video_scene_clip,
    resolve_font_path,
    speed_up_audio,
)
from app.media.tts import TTSError, synthesize_script_audio
from app.media.video_generator import VideoGenerationError, generate_scene_video
from app.script.formats import get_format

WORK_ROOT_DEFAULT = "renders"
# 씬(단락)이 곧바로 이어져 나레이션이 부자연스럽던 문제 — 각 씬 사이에 숨 고를 무음
# 구간을 넣는다. 크로스페이드 전환 시간(TRANSITION_DURATION_SEC=0.4)보다 커야 실제
# 목소리끼리 겹치지 않는다.
SCENE_GAP_SEC = 1.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scene_uses_educational_graphic(scene_narration: str, educational_note_text: str) -> bool:
    """이 씬의 narration이 사실설명(educational_note) 내용을 담고 있는지 대략 판별한다.

    대본은 educational_note를 별도 scene으로 분리하지 않고 형식(tone)마다 정해진
    educational_note_after_stage 단계의 scene narration에 자연스럽게 녹여 쓰는 경우가
    많다(app/script/formats.py의 ScriptFormat.educational_note_after_stage — 표준
    6단계 형식은 problem, 형식에 따라 다른 단계일 수 있다). 텍스트 내용만으로 판별하므로
    이 함수 자체는 stage 이름에 의존하지 않는다. 매칭되면 그 scene을 실사 상품 사진 대신
    2D 그래픽(사실 카드)으로 렌더링한다.
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

    scene["stage"]가 이 대본 형식(script_json["tone"]으로 조회)의 pre_reveal_stages에
    속하면 상품 참고 이미지를 넘기지 않는다 — 광고 대상 상품이 아직 해결책으로 등장하면
    안 되는 "문제 상황" 장면에 그대로 나와버리는 문제(사용자 피드백)가 있었다.
    """
    educational_text = (script_json.get("educational_note") or {}).get("text", "")
    use_graphic = _scene_uses_educational_graphic(scene.get("narration", ""), educational_text)

    image_urls = product.get("image_urls") or []
    category = product.get("category")
    fmt = get_format(script_json.get("tone"))
    is_pre_reveal = scene.get("stage") in fmt.pre_reveal_stages

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
    hook_preview: dict | None = None,
    scene_previews: dict[int, str] | None = None,
) -> dict:
    """script_json + product 정보로 완성 mp4를 만들어 산출물 경로들을 반환한다.

    캡션(자막/후킹/상시CTA/고지문구)은 씬 클립 단계에서 굽지 않는다 — 크로스페이드+BGM까지
    끝낸 "자막 없는 베이스 영상"(base_video_path)을 먼저 만들고, 그 위에
    recomposite_captions()로 한 번에 입힌다. 이렇게 자막 없는 중간 산출물을 남겨둬야
    캡션 편집기에서 위치/스타일만 바꿔 재편집할 때 Gemini/Veo/TTS를 다시 부를 필요 없이
    이 베이스 위에 빠르게 재합성만 하면 된다(사용자 피드백: 렌더 완료 후 캡션 편집 기능).

    hook_preview({"image_path", "video_path"})가 주어지면 씬0(후킹) 이미지/영상을 새로
    생성하지 않고 그 파일을 그대로 재사용한다 — 후킹 확인 단계에서 사용자가 이미 확정한
    스틸컷/영상을, 같은 대본을 다시 렌더할 때마다 후킹이 매번 달라지는 문제(사용자
    피드백) 없이 그대로 쓰기 위함이다. scene_previews({seq: image_path})가 주어지면
    후킹 외 다른 씬들도 같은 방식으로(이미지만, Veo는 애초에 안 씀) 재사용한다.

    반환값: {"output_path": 최종 mp4, "base_video_path": 자막 없는 합성본,
             "scene_timeline": 씬별 절대 구간(초) 리스트} — render_jobs 테이블에 그대로 저장된다.
    """
    os.makedirs(work_dir, exist_ok=True)
    font = font_path or resolve_font_path()
    scenes = script_json["scenes"]
    last_seq = scenes[-1]["seq"]
    first_seq = scenes[0]["seq"]
    fmt = get_format(script_json.get("tone"))

    if status_callback:
        status_callback("generating_images")
    image_paths = {}
    video_paths: dict[int, str] = {}
    character_ref: tuple[bytes, str] | None = None
    scenes_to_build = scenes

    if hook_preview:
        hook_image_path = os.path.join(work_dir, f"scene_{first_seq}.jpg")
        shutil.copy(hook_preview["image_path"], hook_image_path)
        image_paths[first_seq] = hook_image_path
        with open(hook_image_path, "rb") as f:
            character_ref = (f.read(), "image/jpeg")
        hook_video_path = os.path.join(work_dir, f"scene_{first_seq}.mp4")
        shutil.copy(hook_preview["video_path"], hook_video_path)
        video_paths[first_seq] = hook_video_path
        scenes_to_build = scenes[1:]

    for scene in scenes_to_build:
        seq = scene["seq"]
        preview_path = (scene_previews or {}).get(seq)
        if preview_path:
            # 씬별 확인 단계에서 확정된 스틸컷을 그대로 재사용한다 — Gemini를 다시 부르지
            # 않는다(hook_preview와 같은 재사용 원칙).
            path = os.path.join(work_dir, f"scene_{seq}.jpg")
            shutil.copy(preview_path, path)
            if character_ref is None:
                with open(path, "rb") as f:
                    character_ref = (f.read(), "image/jpeg")
        else:
            path, character_ref = build_scene_image(scene, product, script_json, work_dir, character_ref)
        image_paths[seq] = path

    # 후킹(첫 씬)만 시범적으로 실제 영상(Veo)으로 애니메이션한다 — 몇 분 걸릴 수 있어 별도
    # 상태 단계로 알린다. 실패하면 video_paths에 안 담기고, 아래 조립 루프가 기존 정지
    # 이미지+Ken Burns 방식으로 자동 폴백한다.
    if status_callback:
        status_callback("generating_video")
    if not hook_preview:
        first_scene = scenes[0]
        video_path = build_scene_video(first_scene, image_paths[first_seq], work_dir)
        if video_path:
            video_paths[first_seq] = video_path

    if status_callback:
        status_callback("generating_audio")
    audio_results = synthesize_script_audio(
        scenes, work_dir, client=tts_client, pre_reveal_stages=fmt.pre_reveal_stages
    )
    audio_by_seq = {a["seq"]: a for a in audio_results}

    if status_callback:
        status_callback("assembling")
    clip_paths = []
    clip_durations = []
    seqs = []
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

        # 캡션은 여기서 굽지 않는다("" 빈 자막 = 아무 텍스트도 안 그림) — concat+BGM까지
        # 끝난 뒤 recomposite_captions()가 한 번에 입힌다.
        if seq in video_paths:
            render_video_scene_clip(video_paths[seq], audio_path, duration, "", clip_path, work_dir, font_path=font)
        else:
            render_scene_clip(image_paths[seq], audio_path, duration, "", clip_path, work_dir, font_path=font)
        clip_paths.append(clip_path)
        clip_durations.append(duration)
        seqs.append(seq)

    concatenated = concat_clips_with_transitions(
        clip_paths, clip_durations, os.path.join(work_dir, "concatenated.mp4")
    )
    bgm_path = pick_bgm_track()
    base_video_path = mix_bgm(concatenated, bgm_path, os.path.join(work_dir, "base.mp4"))

    scene_timeline = compute_scene_windows(clip_durations, seqs)
    output_path = recomposite_captions(
        base_video_path,
        scene_timeline,
        scenes,
        script_json["disclosure"],
        font,
        work_dir,
        os.path.join(work_dir, "final.mp4"),
        pre_reveal_stages=fmt.pre_reveal_stages,
    )
    return {"output_path": output_path, "base_video_path": base_video_path, "scene_timeline": scene_timeline}


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

    hook_preview = None
    if script.get("hook_preview_status") == "done" and script.get("hook_preview_image_path") and script.get(
        "hook_preview_video_path"
    ):
        hook_preview = {
            "image_path": script["hook_preview_image_path"],
            "video_path": script["hook_preview_video_path"],
        }

    scene_previews = {
        int(seq): info["image_path"]
        for seq, info in (script.get("scene_preview_images") or {}).items()
        if info.get("status") == "done" and info.get("image_path")
    }

    try:
        result = render_script(
            script["script_json"],
            product,
            work_dir,
            status_callback=_set_status,
            tts_client=tts_client,
            hook_preview=hook_preview,
            scene_previews=scene_previews,
        )
        active_client.table("render_jobs").update(
            {
                "status": "done",
                "output_path": result["output_path"],
                "base_video_path": result["base_video_path"],
                "scene_timeline": result["scene_timeline"],
                "finished_at": _now_iso(),
            }
        ).eq("id", job_id).execute()
        active_client.table("products").update({"status": "media_generated"}).eq("id", product["id"]).execute()
        return {"status": "done", "output_path": result["output_path"]}
    except (RenderError, TTSError, Exception) as exc:  # noqa: BLE001 — 어떤 실패든 failed로 기록 후 재전파
        active_client.table("render_jobs").update(
            {"status": "failed", "error_message": str(exc)[:2000], "finished_at": _now_iso()}
        ).eq("id", job_id).execute()
        # products는 재시도 가능하도록 직전 단계로 롤백 (docs/phase3_checklist.md 8번)
        active_client.table("products").update({"status": "script_approved"}).eq("id", product["id"]).execute()
        raise


def process_hook_preview_job(job_id: str, client=None, work_root: str = WORK_ROOT_DEFAULT) -> dict:
    """씬 확인 단계 전용 job — 대상 씬의 스틸컷(후킹이면 영상까지)을 만들어 scripts에 저장한다.

    render_jobs에 kind='hook_preview'로 큐잉되며, 전체 렌더(process_render_job)와 달리
    TTS/조립 단계 없이 이미지(+후킹이면 영상)만 만든다. `target_seq`(null이면 후킹/scenes[0])
    로 대상 씬을 정한다:
    - 후킹(scenes[0]): 이미지+Veo 영상까지 만들어 scripts.hook_preview_*에 저장(기존 동작).
    - 그 외 씬: 이미지만 만들어 scripts.scene_preview_images[seq]에 저장. character_ref는
      반드시 이미 확정된 후킹 이미지(scripts.hook_preview_image_path)에서 고정해 넘긴다 —
      씬마다 다른 사람처럼 바뀌는 문제(사용자 피드백)를 막기 위해, 다른 씬 이미지에서
      파생하지 않고 항상 같은 기준(후킹)에서만 참조를 가져온다. 후킹이 아직 확정되지
      않았으면 실패 처리한다(라우트에서도 버튼을 막지만 API 레벨에서 이중으로 막는다).
    """
    active_client = client or get_client()

    job_res = active_client.table("render_jobs").select("*").eq("id", job_id).execute()
    if not job_res.data:
        raise ValueError(f"render_job {job_id}를 찾을 수 없습니다.")
    job = job_res.data[0]
    script_id = job["script_id"]
    target_seq = job.get("target_seq")

    script_res = active_client.table("scripts").select("*").eq("id", script_id).execute()
    if not script_res.data:
        raise ValueError(f"script {script_id}를 찾을 수 없습니다.")
    script = script_res.data[0]

    product_res = active_client.table("products").select("*").eq("id", script["product_id"]).execute()
    if not product_res.data:
        raise ValueError(f"product {script['product_id']}를 찾을 수 없습니다.")
    product = product_res.data[0]

    script_json = script["script_json"]
    scenes = script_json["scenes"]
    first_seq = scenes[0]["seq"]
    is_hook = target_seq is None or target_seq == first_seq
    scene = scenes[0] if is_hook else next(s for s in scenes if s["seq"] == target_seq)

    work_dir = os.path.join(work_root, "hook-preview", script_id)
    os.makedirs(work_dir, exist_ok=True)

    if is_hook:
        active_client.table("scripts").update({"hook_preview_status": "generating"}).eq("id", script_id).execute()
    else:
        _update_scene_preview(active_client, script, scene["seq"], {"status": "generating"})

    try:
        active_client.table("render_jobs").update({"status": "generating_images"}).eq("id", job_id).execute()

        if is_hook:
            image_path, _ = build_scene_image(scene, product, script_json, work_dir, character_ref=None)
            active_client.table("render_jobs").update({"status": "generating_video"}).eq("id", job_id).execute()
            video_path = build_scene_video(scene, image_path, work_dir)
            if not video_path:
                raise RenderError("후킹 영상 생성에 실패했습니다(Veo).")
            active_client.table("scripts").update(
                {
                    "hook_preview_image_path": image_path,
                    "hook_preview_video_path": video_path,
                    "hook_preview_status": "done",
                }
            ).eq("id", script_id).execute()
        else:
            character_ref = _load_hook_character_ref(script)
            if character_ref is None:
                raise RenderError("먼저 후킹(첫 장면) 미리보기를 완료해야 다른 장면을 만들 수 있습니다.")
            image_path, _ = build_scene_image(scene, product, script_json, work_dir, character_ref=character_ref)
            _update_scene_preview(active_client, script, scene["seq"], {"image_path": image_path, "status": "done"})

        active_client.table("render_jobs").update(
            {"status": "done", "finished_at": _now_iso()}
        ).eq("id", job_id).execute()
        return {"status": "done", "seq": scene["seq"]}
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 failed로 기록 후 재전파
        if is_hook:
            active_client.table("scripts").update({"hook_preview_status": "failed"}).eq("id", script_id).execute()
        else:
            _update_scene_preview(active_client, script, scene["seq"], {"status": "failed"})
        active_client.table("render_jobs").update(
            {"status": "failed", "error_message": str(exc)[:2000], "finished_at": _now_iso()}
        ).eq("id", job_id).execute()
        raise


def _load_hook_character_ref(script: dict) -> tuple[bytes, str] | None:
    """확정된 후킹 이미지를 인물 참조로 읽어온다 — 없으면 None."""
    hook_image_path = script.get("hook_preview_image_path")
    if not hook_image_path or script.get("hook_preview_status") != "done" or not os.path.exists(hook_image_path):
        return None
    with open(hook_image_path, "rb") as f:
        return f.read(), "image/jpeg"


def _update_scene_preview(client, script: dict, seq: int, patch: dict) -> None:
    """scripts.scene_preview_images[seq]를 부분 갱신한다(jsonb 컬럼 통째로 읽고 다시 쓴다)."""
    current = dict(script.get("scene_preview_images") or {})
    current[str(seq)] = {**current.get(str(seq), {}), **patch}
    script["scene_preview_images"] = current
    client.table("scripts").update({"scene_preview_images": current}).eq("id", script["id"]).execute()


def process_hook_patch_job(job_id: str, client=None, work_root: str = WORK_ROOT_DEFAULT) -> dict:
    """이미 완료된 render_job의 씬 하나만 다시 만들어 원본 render_job에 반영한다.

    다른 씬의 이미지·오디오·TTS는 원본 render_job의 work_dir에 남아있는 산출물을 그대로
    재사용하고(다시 부르지 않는다 — work_dir는 렌더 완료 후에도 지우지 않으므로 그 자리에
    있다), 대상 씬만 새로 생성해 clip을 다시 만든 뒤 전체를 재조립한다. "무무스가드" 사례처럼
    후킹만 이상하게 나온 완료된 렌더를, 다른 씬을 다시 만들 필요 없이 고치기 위한
    기능(사용자 피드백). `target_seq`(null이면 후킹/scenes[0])로 대상 씬을 정한다.

    후킹이면 이미지+Veo 영상을 다시 만든다. 그 외 씬이면 이미지만 다시 만들고(Veo는
    원래도 안 씀), 인물 참조는 반드시 **이 render_job 자신의 씬0 이미지**
    (`source_work_dir/scene_{first_seq}.jpg`)에서 읽어 고정한다 — 씬 확인 단계와 같은
    이유로, 다른 씬 이미지에서 파생하면 인물이 바뀔 위험이 있어 항상 같은 기준(후킹)에서만
    참조를 가져온다.
    """
    active_client = client or get_client()

    job_res = active_client.table("render_jobs").select("*").eq("id", job_id).execute()
    if not job_res.data:
        raise ValueError(f"render_job {job_id}를 찾을 수 없습니다.")
    job = job_res.data[0]
    source_job_id = job["source_render_job_id"]
    target_seq = job.get("target_seq")

    source_res = active_client.table("render_jobs").select("*").eq("id", source_job_id).execute()
    if not source_res.data:
        raise ValueError(f"원본 render_job {source_job_id}를 찾을 수 없습니다.")
    source_job = source_res.data[0]

    script_res = active_client.table("scripts").select("*").eq("id", source_job["script_id"]).execute()
    if not script_res.data:
        raise ValueError(f"script {source_job['script_id']}를 찾을 수 없습니다.")
    script = script_res.data[0]

    product_res = active_client.table("products").select("*").eq("id", script["product_id"]).execute()
    if not product_res.data:
        raise ValueError(f"product {script['product_id']}를 찾을 수 없습니다.")
    product = product_res.data[0]

    script_json = script["script_json"]
    scenes = script_json["scenes"]
    first_seq = scenes[0]["seq"]
    last_seq = scenes[-1]["seq"]
    is_hook = target_seq is None or target_seq == first_seq
    target_scene = scenes[0] if is_hook else next(s for s in scenes if s["seq"] == target_seq)
    target_seq = target_scene["seq"]
    fmt = get_format(script_json.get("tone"))
    source_work_dir = os.path.join(work_root, source_job_id)
    font = resolve_font_path()

    try:
        active_client.table("render_jobs").update({"status": "generating_images"}).eq("id", job_id).execute()
        # 새 clip으로 덮어쓰기 전에 원본 대상 씬 clip의 실제 길이를 재둔다 — 다른 씬들과
        # 타이밍이 어긋나지 않으려면 새 clip도 정확히 같은 길이여야 한다.
        old_clip_path = os.path.join(source_work_dir, f"clip_{target_seq}.mp4")
        target_duration = probe_duration_sec(old_clip_path)

        if is_hook:
            image_path, _ = build_scene_image(target_scene, product, script_json, source_work_dir, character_ref=None)
            active_client.table("render_jobs").update({"status": "generating_video"}).eq("id", job_id).execute()
            video_path = build_scene_video(target_scene, image_path, source_work_dir)
            if not video_path:
                raise RenderError("후킹 영상 생성에 실패했습니다(Veo).")
        else:
            hook_image_path = os.path.join(source_work_dir, f"scene_{first_seq}.jpg")
            if not os.path.exists(hook_image_path):
                raise RenderError("원본 렌더의 후킹 이미지를 찾을 수 없어 인물 일관성을 유지할 수 없습니다.")
            with open(hook_image_path, "rb") as f:
                character_ref = (f.read(), "image/jpeg")
            image_path, _ = build_scene_image(
                target_scene, product, script_json, source_work_dir, character_ref=character_ref
            )
            video_path = None

        active_client.table("render_jobs").update({"status": "assembling"}).eq("id", job_id).execute()
        # 대상 씬의 오디오는 원본 렌더가 이미 만들어 남긴 파일을 그대로 쓴다(파일명 규칙이
        # 결정적이라 재구성 가능) — TTS를 다시 부르지 않는다.
        audio_filename = f"scene_{target_seq}_sped.mp3" if target_seq == last_seq else f"scene_{target_seq}_padded.mp3"
        audio_path = os.path.join(source_work_dir, audio_filename)
        if is_hook:
            render_video_scene_clip(
                video_path, audio_path, target_duration, "", old_clip_path, source_work_dir, font_path=font
            )
        else:
            render_scene_clip(
                image_path, audio_path, target_duration, "", old_clip_path, source_work_dir, font_path=font
            )

        clip_paths = []
        clip_durations = []
        seqs = []
        for scene in scenes:
            seq = scene["seq"]
            clip_path = os.path.join(source_work_dir, f"clip_{seq}.mp4")
            clip_paths.append(clip_path)
            clip_durations.append(probe_duration_sec(clip_path))
            seqs.append(seq)

        concatenated = concat_clips_with_transitions(
            clip_paths, clip_durations, os.path.join(source_work_dir, "concatenated.mp4")
        )
        bgm_path = pick_bgm_track()
        base_video_path = mix_bgm(concatenated, bgm_path, os.path.join(source_work_dir, "base.mp4"))
        scene_timeline = compute_scene_windows(clip_durations, seqs)
        output_path = recomposite_captions(
            base_video_path,
            scene_timeline,
            scenes,
            script_json["disclosure"],
            font,
            source_work_dir,
            os.path.join(source_work_dir, "final.mp4"),
            pre_reveal_stages=fmt.pre_reveal_stages,
        )

        active_client.table("render_jobs").update(
            {
                "output_path": output_path,
                "base_video_path": base_video_path,
                "scene_timeline": scene_timeline,
            }
        ).eq("id", source_job_id).execute()
        active_client.table("render_jobs").update(
            {"status": "done", "finished_at": _now_iso()}
        ).eq("id", job_id).execute()
        return {"status": "done", "output_path": output_path}
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 failed로 기록 후 재전파
        active_client.table("render_jobs").update(
            {"status": "failed", "error_message": str(exc)[:2000], "finished_at": _now_iso()}
        ).eq("id", job_id).execute()
        raise


def poll_and_process_once(client=None, work_root: str = WORK_ROOT_DEFAULT) -> str | None:
    """queued 상태인 render_jobs 1건을 원자적으로 선점해 kind에 맞는 처리 함수로 넘긴다.

    선점(claim) 없이 SELECT만으로 집어가면, 크론 실행이 겹치는 경우(직전 실행이 아직
    안 끝났는데 다음 스케줄이 도는 등, run_worker_batch 참조) 같은 job을 두 인스턴스가
    동시에 처리하는 경쟁 상태가 생긴다. id+status=queued 조건으로 UPDATE해 실제로 행을
    바꾼 쪽(반환된 data가 있는 쪽)만 처리를 진행하면, 이미 다른 쪽이 선점한 job은
    자동으로 걸러진다.

    처리한 job_id 또는 None을 반환한다.
    """
    active_client = client or get_client()
    result = (
        active_client.table("render_jobs")
        .select("id, kind")
        .eq("status", "queued")
        .order("created_at")
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    job_id = result.data[0]["id"]
    kind = result.data[0].get("kind", "full")

    claim = (
        active_client.table("render_jobs")
        .update({"status": "claimed"})
        .eq("id", job_id)
        .eq("status", "queued")
        .execute()
    )
    if not claim.data:
        return None

    if kind == "hook_preview":
        process_hook_preview_job(job_id, client=active_client, work_root=work_root)
    elif kind == "hook_patch":
        process_hook_patch_job(job_id, client=active_client, work_root=work_root)
    else:
        process_render_job(job_id, client=active_client, work_root=work_root)
    return job_id


def run_worker_loop(poll_interval_sec: int = 5, client=None, work_root: str = WORK_ROOT_DEFAULT) -> None:
    """상시 구동 프로세스로 띄우는 폴링 루프 (로컬 개발용, `python -m app.media.worker`)."""
    active_client = client or get_client()
    while True:
        try:
            processed = poll_and_process_once(client=active_client, work_root=work_root)
            if not processed:
                time.sleep(poll_interval_sec)
        except Exception:  # noqa: BLE001 — 워커 프로세스는 개별 실패로 죽지 않아야 한다
            time.sleep(poll_interval_sec)


def run_worker_batch(
    max_duration_sec: int = 240, poll_interval_sec: int = 5, client=None, work_root: str = WORK_ROOT_DEFAULT
) -> int:
    """Railway Cron 등 유한 실행 환경용 진입점 — 큐가 비거나 제한 시간을 넘기면 프로세스가 종료된다.

    render-worker를 상시 프로세스로 띄워두면 처리할 job이 없는 유휴 시간에도 계속
    과금되는 문제(사용자 피드백)가 있어, 스케줄에 맞춰 컨테이너를 짧게 띄웠다 내리는
    구조로 바꾸기 위해 추가했다. max_duration_sec은 "다음 job을 새로 집어올지" 판단하는
    기준일 뿐, 이미 시작한 렌더링 하나를 중간에 끊지는 않는다(process_render_job 등은
    한 번 시작하면 끝까지 실행됨) — 크론 주기보다 렌더링이 길어지는 경우를 대비한
    선점(claim, poll_and_process_once 참조)과 함께 써야 안전하다.

    처리한 job 개수를 반환한다.
    """
    active_client = client or get_client()
    deadline = time.monotonic() + max_duration_sec
    processed = 0
    while time.monotonic() < deadline:
        try:
            job_id = poll_and_process_once(client=active_client, work_root=work_root)
        except Exception:  # noqa: BLE001 — 한 job의 실패로 배치 전체가 죽지 않아야 한다
            time.sleep(poll_interval_sec)
            continue
        if job_id is None:
            break
        processed += 1
    return processed


if __name__ == "__main__":
    import sys

    if "--once" in sys.argv:
        run_worker_batch()
    else:
        run_worker_loop()
