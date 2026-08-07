from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import DEFAULT_HOLD_MINUTES
from app.db import get_client
from app.media.images import ImageFetchError, download_image
from app.media.thumbnail import generate_thumbnail
from app.script.formats import get_format
from app.upload.publisher import PublishError, publish_video

router = APIRouter(prefix="/api", tags=["upload"])


class QueueUploadRequest(BaseModel):
    cooldown_minutes: int | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_or_404(client, table: str, item_id: str, not_found_message: str) -> dict:
    result = client.table(table).select("*").eq("id", item_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail=not_found_message)
    return result.data[0]


@router.post("/render-jobs/{render_job_id}/generate-thumbnail", status_code=201)
def generate_thumbnail_endpoint(render_job_id: str):
    client = get_client()
    job = _get_or_404(client, "render_jobs", render_job_id, "렌더 작업을 찾을 수 없습니다.")
    if job["status"] != "done":
        raise HTTPException(status_code=400, detail=f"render_job이 done 상태가 아닙니다 (현재: {job['status']}).")

    script = _get_or_404(client, "scripts", job["script_id"], "대본을 찾을 수 없습니다.")
    product = _get_or_404(client, "products", script["product_id"], "상품을 찾을 수 없습니다.")

    # "empathy"로 하드코딩돼 있었는데, 형식(tone)마다 첫 단계 키가 다를 수 있어(예:
    # 기획천재발견형은 "hook", 썸쇼츠형은 "story_setup") 형식에서 실제 첫 단계 키를 조회한다.
    fmt = get_format(script["script_json"].get("tone"))
    hook_text = script["script_json"]["structure"][fmt.stage_keys[0]]
    image_bytes = None
    image_urls = product.get("image_urls") or []
    if image_urls:
        try:
            image_bytes = download_image(image_urls[0])
        except ImageFetchError:
            image_bytes = None  # 실사 이미지를 못 받으면 2D 그래픽 폴백으로 진행

    work_dir = os.path.join("renders", render_job_id)
    os.makedirs(work_dir, exist_ok=True)
    output_path = os.path.join(work_dir, "thumbnail.jpg")
    generate_thumbnail(hook_text, image_bytes, product.get("category"), output_path)

    result = (
        client.table("thumbnails")
        .insert({"render_job_id": render_job_id, "image_path": output_path, "status": "done"})
        .execute()
    )
    client.table("products").update({"status": "thumbnail_generated"}).eq("id", product["id"]).execute()
    return result.data[0]


@router.post("/render-jobs/{render_job_id}/queue-upload", status_code=201)
def queue_upload(render_job_id: str, payload: QueueUploadRequest):
    client = get_client()
    job = _get_or_404(client, "render_jobs", render_job_id, "렌더 작업을 찾을 수 없습니다.")
    script = _get_or_404(client, "scripts", job["script_id"], "대본을 찾을 수 없습니다.")

    thumbnail_result = (
        client.table("thumbnails")
        .select("*")
        .eq("render_job_id", render_job_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    thumbnail = thumbnail_result.data[0] if thumbnail_result.data else None

    cooldown_minutes = payload.cooldown_minutes if payload.cooldown_minutes is not None else DEFAULT_HOLD_MINUTES
    ready_at = (datetime.now(timezone.utc) + timedelta(minutes=cooldown_minutes)).isoformat()

    youtube_meta = (script["script_json"] or {}).get("youtube") or {}
    row = {
        "render_job_id": render_job_id,
        "thumbnail_id": thumbnail["id"] if thumbnail else None,
        "youtube_title": youtube_meta.get("title"),
        "youtube_description": youtube_meta.get("description"),
        "ready_at": ready_at,
        "status": "pending_review",
    }
    result = client.table("upload_queue").insert(row).execute()
    client.table("products").update({"status": "queued_for_upload"}).eq("id", script["product_id"]).execute()
    return result.data[0]


@router.get("/upload-queue")
def list_upload_queue(status: str | None = None):
    client = get_client()
    query = client.table("upload_queue").select("*")
    if status:
        query = query.eq("status", status)
    result = query.order("created_at", desc=True).execute()
    return result.data


@router.post("/upload-queue/{upload_queue_id}/cancel")
def cancel_upload(upload_queue_id: str):
    client = get_client()
    item = _get_or_404(client, "upload_queue", upload_queue_id, "게시 큐 항목을 찾을 수 없습니다.")
    if item["status"] in ("published", "canceled"):
        raise HTTPException(status_code=400, detail=f"현재 상태({item['status']})에서는 취소할 수 없습니다.")
    result = client.table("upload_queue").update({"status": "canceled"}).eq("id", upload_queue_id).execute()
    return result.data[0]


@router.post("/upload-queue/{upload_queue_id}/publish")
def publish_upload(upload_queue_id: str):
    """AGENTS.md 절대 규칙 4의 실제 구현체 — 사람이 명시적으로 호출해야만 실제 업로드가 발생한다."""
    client = get_client()
    item = _get_or_404(client, "upload_queue", upload_queue_id, "게시 큐 항목을 찾을 수 없습니다.")

    if item["status"] != "ready_to_publish":
        raise HTTPException(
            status_code=403,
            detail=f"현재 상태({item['status']})에서는 게시할 수 없습니다. ready_to_publish 상태여야 합니다.",
        )

    render_job = _get_or_404(client, "render_jobs", item["render_job_id"], "렌더 작업을 찾을 수 없습니다.")
    thumbnail_path = None
    if item.get("thumbnail_id"):
        thumb = client.table("thumbnails").select("*").eq("id", item["thumbnail_id"]).execute()
        if thumb.data:
            thumbnail_path = thumb.data[0]["image_path"]

    try:
        video_id = publish_video(
            render_job["output_path"],
            item.get("youtube_title") or "",
            item.get("youtube_description") or "",
            thumbnail_path=thumbnail_path,
        )
    except PublishError as exc:
        client.table("upload_queue").update({"status": "failed"}).eq("id", upload_queue_id).execute()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    result = (
        client.table("upload_queue")
        .update({"status": "published", "youtube_video_id": video_id, "published_at": _now_iso()})
        .eq("id", upload_queue_id)
        .execute()
    )

    script = _get_or_404(client, "scripts", render_job["script_id"], "대본을 찾을 수 없습니다.")
    client.table("products").update({"status": "uploaded"}).eq("id", script["product_id"]).execute()
    return result.data[0]
