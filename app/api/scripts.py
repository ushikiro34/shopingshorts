from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import get_client

router = APIRouter(prefix="/api", tags=["scripts"])


class ScriptPatch(BaseModel):
    script_json: dict


@router.patch("/scripts/{script_id}")
def update_script(script_id: str, payload: ScriptPatch):
    client = get_client()
    existing = client.table("scripts").select("*").eq("id", script_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="대본을 찾을 수 없습니다.")
    current = existing.data[0]

    result = (
        client.table("scripts")
        .update({"script_json": payload.script_json, "version": current["version"] + 1})
        .eq("id", script_id)
        .execute()
    )
    return result.data[0]


@router.post("/scripts/{script_id}/approve", status_code=201)
def approve_script(script_id: str):
    """대본을 승인하고 render_jobs를 enqueue한다 (Phase 3). 실제 렌더링은 별도 워커가 폴링해 처리한다."""
    client = get_client()
    existing = client.table("scripts").select("*").eq("id", script_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="대본을 찾을 수 없습니다.")
    script = existing.data[0]

    client.table("scripts").update({"approved": True}).eq("id", script_id).execute()

    job_result = (
        client.table("render_jobs")
        .insert({"script_id": script_id, "status": "queued"})
        .execute()
    )
    client.table("products").update({"status": "script_approved"}).eq("id", script["product_id"]).execute()
    return job_result.data[0]
