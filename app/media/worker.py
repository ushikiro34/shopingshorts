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
from app.media.images import compose_scene_image, download_image, save_jpeg
from app.media.render import (
    HEIGHT,
    WIDTH,
    RenderError,
    concat_clips,
    mix_bgm,
    pick_bgm_track,
    render_scene_clip,
    resolve_font_path,
)
from app.media.tts import TTSError, synthesize_script_audio

WORK_ROOT_DEFAULT = "renders"


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


def build_scene_image(scene: dict, product: dict, script_json: dict, work_dir: str) -> str:
    """씬 하나의 배경 이미지를 결정해 JPEG로 저장하고 경로를 반환한다."""
    educational_text = (script_json.get("educational_note") or {}).get("text", "")
    use_graphic = _scene_uses_educational_graphic(scene.get("narration", ""), educational_text)

    image_urls = product.get("image_urls") or []
    category = product.get("category")

    if use_graphic or not image_urls:
        composed = compose_educational_note_scene((WIDTH, HEIGHT), category=category)
    else:
        idx = scene.get("image_index", 0) % len(image_urls)
        image_bytes = download_image(image_urls[idx])
        composed = compose_scene_image(image_bytes)

    path = os.path.join(work_dir, f"scene_{scene['seq']}.jpg")
    return save_jpeg(composed, path)


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
    image_paths = {scene["seq"]: build_scene_image(scene, product, script_json, work_dir) for scene in scenes}

    if status_callback:
        status_callback("generating_audio")
    audio_results = synthesize_script_audio(scenes, work_dir, client=tts_client)
    audio_by_seq = {a["seq"]: a for a in audio_results}

    if status_callback:
        status_callback("assembling")
    last_seq = scenes[-1]["seq"]
    clip_paths = []
    for scene in scenes:
        seq = scene["seq"]
        clip_path = os.path.join(work_dir, f"clip_{seq}.mp4")
        render_scene_clip(
            image_paths[seq],
            audio_by_seq[seq]["path"],
            audio_by_seq[seq]["duration_sec"],
            scene["caption"],
            clip_path,
            work_dir,
            font_path=font,
            disclosure_text=script_json["disclosure"] if seq == last_seq else None,
        )
        clip_paths.append(clip_path)

    concatenated = concat_clips(
        clip_paths, os.path.join(work_dir, "concat_list.txt"), os.path.join(work_dir, "concatenated.mp4")
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
