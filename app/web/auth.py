"""Phase 4 — Supabase Auth 로그인 + 세션 (단일 운영자 계정).

회원가입 화면은 만들지 않는다 — 계정은 Supabase 대시보드에서 수동 생성한다
(docs/04_ui_spec.md 0번). 세션은 SessionMiddleware(httpOnly, SESSION_SECRET 서명)가
발급하는 쿠키에 저장된다.
"""

from __future__ import annotations

import httpx
from fastapi import Request

from app.config import SUPABASE_SERVICE_KEY, SUPABASE_URL

AUTH_TOKEN_URL_TEMPLATE = "{base}/auth/v1/token?grant_type=password"

# 로그인 없이도 접근 가능한 경로 (대시보드 자체가 아닌 것들). /api는 Phase 1~3에서
# 이미 인증 없이 설계된 내부 API 계약이라 그대로 둔다 — 04_ui_spec.md의
# "로그인 전 모든 라우트는 접근 불가"는 대시보드(웹) 화면 기준이다.
PUBLIC_PATH_PREFIXES = ("/login", "/static", "/api", "/health", "/docs", "/redoc", "/openapi.json")


class AuthError(RuntimeError):
    """로그인 실패를 감싸는 예외."""


def sign_in(email: str, password: str, client: httpx.Client | None = None) -> dict:
    """Supabase Auth로 로그인하고 {id, email}을 반환한다. 실패 시 AuthError."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise AuthError("SUPABASE_URL/SUPABASE_SERVICE_KEY가 설정되지 않았습니다.")

    url = AUTH_TOKEN_URL_TEMPLATE.format(base=SUPABASE_URL)
    headers = {"apikey": SUPABASE_SERVICE_KEY, "Content-Type": "application/json"}
    body = {"email": email, "password": password}

    active_client = client or httpx.Client(timeout=15.0)
    response = active_client.post(url, headers=headers, json=body)
    if response.status_code >= 400:
        raise AuthError("이메일 또는 비밀번호를 확인해주세요.")

    data = response.json()
    user = data.get("user") or {}
    if not user.get("id"):
        raise AuthError("이메일 또는 비밀번호를 확인해주세요.")
    return {"id": user["id"], "email": user.get("email")}


def current_user(request: Request) -> dict | None:
    return request.session.get("user")


def is_public_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") or path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)
