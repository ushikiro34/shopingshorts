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
