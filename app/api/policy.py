from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.config import POLICY_CHECK_SECRET
from app.db import get_client
from app.monitoring.policy_checker import run_policy_check

router = APIRouter(prefix="/api", tags=["policy"])


class PolicyAlertReview(BaseModel):
    note: str | None = None


@router.post("/policy-check/run")
def policy_check_run(x_policy_check_secret: str | None = Header(default=None)):
    """외부 스케줄러(cron-job.org)가 주기 호출. 무단 트리거 방지를 위해 헤더로 시크릿을 검증한다."""
    if POLICY_CHECK_SECRET and x_policy_check_secret != POLICY_CHECK_SECRET:
        raise HTTPException(status_code=401, detail="인증 실패")
    return run_policy_check()


@router.get("/policy-alerts")
def list_policy_alerts(reviewed: bool | None = None):
    client = get_client()
    query = client.table("policy_alerts").select("*, policy_snapshots(platform, policy_name, url)")
    if reviewed is not None:
        query = query.eq("reviewed", reviewed)
    result = query.order("detected_at", desc=True).execute()
    return result.data


@router.post("/policy-alerts/{alert_id}/review")
def review_policy_alert(alert_id: str, payload: PolicyAlertReview):
    client = get_client()
    existing = client.table("policy_alerts").select("id").eq("id", alert_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="정책 알림을 찾을 수 없습니다.")

    result = (
        client.table("policy_alerts")
        .update(
            {
                "reviewed": True,
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "note": payload.note,
            }
        )
        .eq("id", alert_id)
        .execute()
    )
    return result.data[0]
