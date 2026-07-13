from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db import get_client

router = APIRouter(prefix="/api", tags=["render-jobs"])


@router.get("/render-jobs/{render_job_id}")
def get_render_job(render_job_id: str):
    client = get_client()
    result = client.table("render_jobs").select("*").eq("id", render_job_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="렌더 작업을 찾을 수 없습니다.")
    return result.data[0]
