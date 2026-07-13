"""내부 상태 워커 (Phase 4).

AGENTS.md 절대 규칙 4: 이 워커는 pending_review 중 ready_at이 지난 항목의 상태만
ready_to_publish로 바꾼다. 유튜브(외부) API는 절대 호출하지 않는다 — 실제 업로드는
사람이 /publish 엔드포인트를 호출했을 때만 발생한다.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from app.db import get_client


def promote_ready_items(client=None) -> list[str]:
    """pending_review 중 ready_at이 지난 항목을 ready_to_publish로 전환한다.

    반환값: 전환된 upload_queue id 목록. 외부 API 호출 없음(내부 상태 전환뿐).
    """
    active_client = client or get_client()
    now_iso = datetime.now(timezone.utc).isoformat()
    result = (
        active_client.table("upload_queue")
        .select("id")
        .eq("status", "pending_review")
        .lte("ready_at", now_iso)
        .execute()
    )
    ids = [row["id"] for row in result.data]
    for item_id in ids:
        active_client.table("upload_queue").update({"status": "ready_to_publish"}).eq("id", item_id).execute()
    return ids


def run_worker_loop(poll_interval_sec: int = 60, client=None) -> None:
    """Railway 등에서 별도 프로세스로 띄우는 폴링 루프. 실패해도 리스크가 낮다(외부 API 미호출)."""
    active_client = client or get_client()
    while True:
        try:
            promote_ready_items(client=active_client)
        except Exception:  # noqa: BLE001 — 워커 프로세스는 개별 실패로 죽지 않아야 한다
            pass
        time.sleep(poll_interval_sec)


if __name__ == "__main__":
    run_worker_loop()
