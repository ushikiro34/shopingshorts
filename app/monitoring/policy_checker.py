"""플랫폼 정책 모니터링 (Phase 4 부속 기능).

등록된 정책 페이지를 fetch해 본문 해시를 비교한다. 변경 여부만 감지하며,
실제 대응(대본 규칙 수정 등)은 사람이 판단한다(docs/00_project_overview.md).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import httpx

from app.db import get_client


class PolicyCheckError(RuntimeError):
    """정책 페이지 fetch 실패를 감싸는 명확한 예외."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_and_hash(url: str, client: httpx.Client) -> str:
    response = client.get(url)
    if response.status_code >= 400:
        raise PolicyCheckError(f"정책 페이지 fetch 실패 (status={response.status_code}): {url}")
    return hashlib.sha256(response.text.encode("utf-8")).hexdigest()


def run_policy_check(client=None, http_client: httpx.Client | None = None) -> dict:
    """등록된 모든 policy_snapshots를 확인해 변경 시 policy_alerts를 생성한다."""
    active_client = client or get_client()
    active_http_client = http_client or httpx.Client(timeout=20.0)

    snapshots = active_client.table("policy_snapshots").select("*").execute().data

    checked = 0
    changed = 0
    errors: list[dict] = []
    now_iso = _now_iso()

    for snapshot in snapshots:
        try:
            new_hash = _fetch_and_hash(snapshot["url"], active_http_client)
        except PolicyCheckError as exc:
            errors.append({"snapshot_id": snapshot["id"], "error": str(exc)})
            continue

        checked += 1
        old_hash = snapshot.get("content_hash") or ""
        update = {"content_hash": new_hash, "last_checked_at": now_iso}

        if old_hash and old_hash != new_hash:
            update["last_changed_at"] = now_iso
            active_client.table("policy_alerts").insert({"snapshot_id": snapshot["id"]}).execute()
            changed += 1

        active_client.table("policy_snapshots").update(update).eq("id", snapshot["id"]).execute()

    return {"checked": checked, "changed": changed, "errors": errors}
