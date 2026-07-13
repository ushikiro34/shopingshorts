import os

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.policy import router as policy_router
from app.api.products import router as products_router
from app.api.render_jobs import router as render_jobs_router
from app.api.scripts import router as scripts_router
from app.api.upload_queue import router as upload_queue_router
from app.config import SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS, SESSION_SECRET
from app.web.auth import current_user, is_public_path
from app.web.dashboard import router as dashboard_router

os.makedirs("renders", exist_ok=True)

app = FastAPI(title="couparvi", version="0.1.0")

app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
app.mount("/renders", StaticFiles(directory="renders"), name="renders")

app.include_router(products_router)
app.include_router(scripts_router)
app.include_router(render_jobs_router)
app.include_router(upload_queue_router)
app.include_router(policy_router)
app.include_router(dashboard_router)


@app.middleware("http")
async def require_login_for_dashboard(request: Request, call_next):
    """docs/04_ui_spec.md 0번 — 로그인 전 대시보드(웹) 라우트는 접근 불가.

    /api/*는 Phase 1~3에서 이미 인증 없는 내부 API 계약으로 설계돼 그대로 둔다.
    """
    if not is_public_path(request.url.path) and current_user(request) is None:
        return RedirectResponse("/login", status_code=302)
    return await call_next(request)


# Starlette는 나중에 추가된 미들웨어가 바깥쪽(먼저 실행)이 된다 — SessionMiddleware를
# require_login_for_dashboard보다 뒤에 등록해야 request.session이 먼저 준비된다.
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET or "dev-only-insecure-secret-change-me",
    session_cookie=SESSION_COOKIE_NAME,
    max_age=SESSION_MAX_AGE_SECONDS,
)


@app.get("/health")
def health():
    return {"status": "ok"}
