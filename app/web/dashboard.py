"""Phase 4 — 대시보드 (docs/04_ui_spec.md 기준).

FastAPI + Jinja2. 탭 4개(발굴/대본작성/미디어제작/게시검토)는 파이프라인 단계 1:1이며
소프트 게이팅(탭 이동 제약 없음, 큐가 비었을 때만 안내)이다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import DEFAULT_HOLD_MINUTES, PARTNERS_DISCLOSURE, SCRIPT_TONES
from app.db import get_client
from app.discovery.education import detect_needs_education
from app.discovery.scoring import MAX_TOTAL_SCORE, ScoreInputs, calculate_score, score_story
from app.discovery.story_heuristic import count_emotional_keywords
from app.media.images import ImageFetchError, download_image
from app.media.thumbnail import generate_thumbnail
from app.review.analyzer import ReviewAnalysisError, analyze_reviews
from app.script.generator import ScriptGenerationError, generate_script
from app.script.validator import ScriptValidationError, validate_script
from app.upload.publisher import PublishError, publish_video
from app.web.auth import current_user, sign_in
from app.web.auth import AuthError

import os

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="app/web/templates")

DISCOVER_STATUSES = ["discovered", "scored", "reviews_collected"]
SCRIPT_STATUSES = ["analyzed", "script_generated"]
MEDIA_STATUSES = ["script_approved", "media_generated", "thumbnail_generated"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _policy_alert_count(client) -> int:
    result = client.table("policy_alerts").select("id").eq("reviewed", False).execute()
    return len(result.data)


def _base_ctx(request: Request, client) -> dict:
    return {
        "request": request,
        "user": current_user(request),
        "policy_alert_count": _policy_alert_count(client),
        "toast": request.query_params.get("toast"),
    }


def _counts(client) -> dict:
    def _count(statuses: list[str]) -> int:
        result = client.table("products").select("id").in_("status", statuses).execute()
        return len(result.data)

    return {
        "discover": _count(DISCOVER_STATUSES),
        "script": _count(SCRIPT_STATUSES),
        "media": _count(MEDIA_STATUSES),
        "publish": len(client.table("upload_queue").select("id").in_("status", ["pending_review", "ready_to_publish"]).execute().data),
    }


_DELETE_REDIRECT_TABS = {"discover", "scripts", "media"}


@router.post("/products/{product_id}/delete")
def delete_product(request: Request, product_id: str, redirect_to: str = Form("discover")):
    """발굴/대본작성/미디어제작 탭 공용 — 리스트 행의 삭제 아이콘에서 호출된다.

    products를 지우면 reviews/review_analysis/scripts/render_jobs 등은 FK cascade로 함께 삭제된다
    (migrations의 on delete cascade). 되돌릴 수 없어 프론트에서 confirm() 확인을 거친다.
    """
    client = get_client()
    client.table("products").delete().eq("id", product_id).execute()
    target = redirect_to if redirect_to in _DELETE_REDIRECT_TABS else "discover"
    return RedirectResponse(f"/{target}?toast=삭제했어요", status_code=302)


# --- 로그인 ---


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if current_user(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    try:
        user = sign_in(email, password)
    except AuthError as exc:
        return templates.TemplateResponse("login.html", {"request": request, "error": str(exc)}, status_code=401)
    request.session["user"] = user
    return RedirectResponse("/", status_code=302)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# --- 홈 ---


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    client = get_client()
    ctx = _base_ctx(request, client)
    counts = _counts(client)
    uploaded_today = len(
        client.table("products")
        .select("id")
        .eq("status", "uploaded")
        .gte("updated_at", datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00"))
        .execute()
        .data
    )
    ctx.update({"counts": counts, "daily_goal": 3, "uploaded_today": uploaded_today})
    return templates.TemplateResponse("home.html", ctx)


# --- 발굴 탭 ---


@router.get("/discover", response_class=HTMLResponse)
def discover_tab(request: Request, selected: str | None = None, view: str = "list"):
    client = get_client()
    ctx = _base_ctx(request, client)
    products = (
        client.table("products")
        .select("*")
        .in_("status", DISCOVER_STATUSES)
        .order("total_score", desc=True)
        .execute()
        .data
    )
    selected_product = None
    if selected:
        found = [p for p in products if p["id"] == selected]
        selected_product = found[0] if found else None
    ctx.update(
        {
            "active": "discover",
            "counts": _counts(client),
            "products": products,
            "selected": selected_product,
            "view": view if selected_product else "list",
        }
    )
    return templates.TemplateResponse("tab_discover.html", ctx)


@router.post("/discover/new")
def discover_new(request: Request, mode: str = Form(...), value: str = Form(...)):
    client = get_client()
    if mode == "keyword":
        from app.coupang.partners import CoupangPartnersError, search_products

        try:
            results = search_products(value)
        except CoupangPartnersError:
            results = []
        if not results:
            return RedirectResponse("/discover?toast=" + "발굴 실패 (쿠팡 API 확인 필요)", status_code=302)
        top = results[0]
        needs_education = detect_needs_education(top.category_name, top.product_name)
        breakdown = calculate_score(ScoreInputs(review_count=top.rating_count, price=top.product_price))
        row = {
            "coupang_url": top.product_url,
            "keyword": value,
            "product_name": top.product_name,
            "price": top.product_price,
            "image_urls": [top.product_image] if top.product_image else [],
            "deeplink": top.product_url,
            "category": top.category_name,
            "review_count": top.rating_count,
            "needs_education": needs_education,
            "status": "scored",
            **breakdown.as_dict(),
        }
    else:
        # mode == "manual": 쿠팡 API 없이 상품명만으로 최소 등록 (v2.2 임시 소싱)
        needs_education = detect_needs_education(None, value)
        breakdown = calculate_score(ScoreInputs())
        row = {
            "product_name": value,
            "needs_education": needs_education,
            "status": "scored",
            **breakdown.as_dict(),
        }
    result = client.table("products").insert(row).execute()
    new_id = result.data[0]["id"]
    return RedirectResponse(f"/discover?selected={new_id}&view=detail&toast=상품을+등록했어요", status_code=302)


@router.post("/discover/{product_id}/analyze")
def discover_analyze(
    request: Request,
    product_id: str,
    reviews_raw: str = Form(...),
    rating_summary: str = Form(""),
    needs_education: str = Form(None),
):
    client = get_client()
    product = client.table("products").select("*").eq("id", product_id).execute().data[0]

    client.table("reviews").insert(
        {"product_id": product_id, "reviews_raw": reviews_raw, "rating_summary": rating_summary}
    ).execute()

    keyword_count = count_emotional_keywords(reviews_raw)
    new_story_score = score_story(keyword_count)
    old_story_score = product.get("story_score") or 0
    old_total_score = product.get("total_score") or 0
    new_total_score = min(old_total_score - old_story_score + new_story_score, MAX_TOTAL_SCORE)

    client.table("products").update(
        {
            "story_score": new_story_score,
            "total_score": new_total_score,
            "needs_education": needs_education == "on",
            "status": "reviews_collected",
        }
    ).eq("id", product_id).execute()

    try:
        analysis_json = analyze_reviews(reviews_raw)
        review_row = client.table("reviews").select("*").eq("product_id", product_id).order("created_at", desc=True).limit(1).execute().data[0]
        client.table("review_analysis").insert({"review_id": review_row["id"], "analysis_json": analysis_json}).execute()
        client.table("products").update({"status": "analyzed"}).eq("id", product_id).execute()
    except ReviewAnalysisError:
        return RedirectResponse(f"/discover?selected={product_id}&view=detail&toast=후기+분석에+실패했어요", status_code=302)

    # 04_ui_spec.md: "완료하고 다음으로"는 다음 탭으로 강제 이동하지 않는다 — 토스트만 안내하고
    # 현재(발굴) 탭에 머문다. 상태가 바뀐 상품은 이 탭 큐에서 자연히 사라진다.
    return RedirectResponse("/discover?toast=완료!+대본작성+탭에서+확인할+수+있어요", status_code=302)


# --- 대본작성 탭 ---


@router.get("/scripts", response_class=HTMLResponse)
def scripts_tab(request: Request, selected: str | None = None, view: str = "list"):
    client = get_client()
    ctx = _base_ctx(request, client)
    products = (
        client.table("products")
        .select("*")
        .in_("status", SCRIPT_STATUSES)
        .order("total_score", desc=True)
        .execute()
        .data
    )
    selected_product = None
    latest_script = None
    if selected:
        found = [p for p in products if p["id"] == selected]
        selected_product = found[0] if found else None
        if selected_product:
            scripts = (
                client.table("scripts")
                .select("*")
                .eq("product_id", selected)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
                .data
            )
            latest_script = scripts[0] if scripts else None
    ctx.update(
        {
            "active": "script",
            "counts": _counts(client),
            "products": products,
            "selected": selected_product,
            "script": latest_script,
            "tones": SCRIPT_TONES,
            "view": view if selected_product else "list",
        }
    )
    return templates.TemplateResponse("tab_script.html", ctx)


@router.post("/scripts/{product_id}/generate")
def scripts_generate(request: Request, product_id: str, tone: str = Form(...)):
    client = get_client()
    product = client.table("products").select("*").eq("id", product_id).execute().data[0]
    review = client.table("reviews").select("*").eq("product_id", product_id).order("created_at", desc=True).limit(1).execute().data[0]
    analysis = client.table("review_analysis").select("*").eq("review_id", review["id"]).order("created_at", desc=True).limit(1).execute().data[0]

    needs_education = bool(product.get("needs_education", False))
    try:
        script_json = generate_script(
            analysis_json=analysis["analysis_json"], product=product, tone=tone, needs_education=needs_education
        )
        validate_script(script_json, review["reviews_raw"], needs_education)
    except (ScriptGenerationError, ScriptValidationError) as exc:
        return RedirectResponse(f"/scripts?selected={product_id}&view=detail&toast=대본+생성+실패:+{str(exc)[:60]}", status_code=302)

    client.table("scripts").insert(
        {
            "product_id": product_id,
            "analysis_id": analysis["id"],
            "tone": tone,
            "script_json": script_json,
        }
    ).execute()
    client.table("products").update({"status": "script_generated"}).eq("id", product_id).execute()
    return RedirectResponse(f"/scripts?selected={product_id}&view=detail&toast={tone}+톤으로+다시+생성했어요", status_code=302)


@router.post("/scripts/{script_id}/approve")
def scripts_approve(request: Request, script_id: str, product_id: str = Form(...)):
    client = get_client()
    client.table("scripts").update({"approved": True}).eq("id", script_id).execute()
    client.table("render_jobs").insert({"script_id": script_id, "status": "queued"}).execute()
    client.table("products").update({"status": "script_approved"}).eq("id", product_id).execute()
    # 04_ui_spec.md: 다음 탭으로 강제 이동하지 않는다 — 토스트만 안내하고 현재(대본작성) 탭에 머문다.
    return RedirectResponse("/scripts?toast=완료!+미디어제작+탭에서+확인할+수+있어요", status_code=302)


# --- 미디어제작 탭 ---


@router.get("/media", response_class=HTMLResponse)
def media_tab(request: Request, selected: str | None = None, view: str = "list"):
    client = get_client()
    ctx = _base_ctx(request, client)
    products = (
        client.table("products")
        .select("*")
        .in_("status", MEDIA_STATUSES)
        .order("updated_at", desc=True)
        .execute()
        .data
    )
    selected_product = None
    render_job = None
    thumbnail = None
    disclosure_ok = deeplink_ok = False
    if selected:
        found = [p for p in products if p["id"] == selected]
        selected_product = found[0] if found else None
        if selected_product:
            scripts = client.table("scripts").select("*").eq("product_id", selected).order("created_at", desc=True).limit(1).execute().data
            script = scripts[0] if scripts else None
            if script:
                jobs = client.table("render_jobs").select("*").eq("script_id", script["id"]).order("created_at", desc=True).limit(1).execute().data
                render_job = jobs[0] if jobs else None
                youtube = (script.get("script_json") or {}).get("youtube") or {}
                description = youtube.get("description", "") or ""
                disclosure_ok = description.rstrip().endswith(PARTNERS_DISCLOSURE)
                deeplink_ok = bool(selected_product.get("deeplink")) and (selected_product.get("deeplink") or "") in description
                if render_job:
                    thumbs = client.table("thumbnails").select("*").eq("render_job_id", render_job["id"]).order("created_at", desc=True).limit(1).execute().data
                    thumbnail = thumbs[0] if thumbs else None
    ctx.update(
        {
            "active": "media",
            "counts": _counts(client),
            "products": products,
            "selected": selected_product,
            "render_job": render_job,
            "thumbnail": thumbnail,
            "disclosure_ok": disclosure_ok,
            "deeplink_ok": deeplink_ok,
            "view": view if selected_product else "list",
        }
    )
    return templates.TemplateResponse("tab_media.html", ctx)


@router.post("/media/{render_job_id}/generate-thumbnail")
def media_generate_thumbnail(request: Request, render_job_id: str, product_id: str = Form(...)):
    client = get_client()
    job = client.table("render_jobs").select("*").eq("id", render_job_id).execute().data[0]
    script = client.table("scripts").select("*").eq("id", job["script_id"]).execute().data[0]
    product = client.table("products").select("*").eq("id", script["product_id"]).execute().data[0]

    hook_text = script["script_json"]["structure"]["empathy"]
    image_bytes = None
    image_urls = product.get("image_urls") or []
    if image_urls:
        try:
            image_bytes = download_image(image_urls[0])
        except ImageFetchError:
            image_bytes = None

    work_dir = os.path.join("renders", render_job_id)
    os.makedirs(work_dir, exist_ok=True)
    output_path = os.path.join(work_dir, "thumbnail.jpg")
    generate_thumbnail(hook_text, image_bytes, product.get("category"), output_path)

    client.table("thumbnails").insert({"render_job_id": render_job_id, "image_path": output_path, "status": "done"}).execute()
    client.table("products").update({"status": "thumbnail_generated"}).eq("id", product_id).execute()
    return RedirectResponse(f"/media?selected={product_id}&view=detail&toast=썸네일을+다시+만들었어요", status_code=302)


@router.post("/media/{render_job_id}/queue-upload")
def media_queue_upload(request: Request, render_job_id: str, product_id: str = Form(...)):
    client = get_client()
    job = client.table("render_jobs").select("*").eq("id", render_job_id).execute().data[0]
    script = client.table("scripts").select("*").eq("id", job["script_id"]).execute().data[0]
    thumbs = client.table("thumbnails").select("*").eq("render_job_id", render_job_id).order("created_at", desc=True).limit(1).execute().data
    thumbnail = thumbs[0] if thumbs else None

    ready_at = (datetime.now(timezone.utc) + timedelta(minutes=DEFAULT_HOLD_MINUTES)).isoformat()
    youtube_meta = (script["script_json"] or {}).get("youtube") or {}
    client.table("upload_queue").insert(
        {
            "render_job_id": render_job_id,
            "thumbnail_id": thumbnail["id"] if thumbnail else None,
            "youtube_title": youtube_meta.get("title"),
            "youtube_description": youtube_meta.get("description"),
            "ready_at": ready_at,
            "status": "pending_review",
        }
    ).execute()
    client.table("products").update({"status": "queued_for_upload"}).eq("id", product_id).execute()
    # 04_ui_spec.md: 다음 탭으로 강제 이동하지 않는다 — 토스트만 안내하고 현재(미디어제작) 탭에 머문다.
    return RedirectResponse("/media?toast=완료!+게시검토+탭에서+확인할+수+있어요", status_code=302)


# --- 게시검토 탭 ---


@router.get("/publish", response_class=HTMLResponse)
def publish_tab(request: Request, selected: str | None = None, view: str = "list"):
    client = get_client()
    ctx = _base_ctx(request, client)
    items = (
        client.table("upload_queue")
        .select("*")
        .in_("status", ["pending_review", "ready_to_publish", "published"])
        .order("created_at", desc=True)
        .execute()
        .data
    )
    selected_item = None
    render_job = None
    thumbnail = None
    remaining_minutes = 0
    if selected:
        found = [i for i in items if i["id"] == selected]
        selected_item = found[0] if found else None
        if selected_item:
            render_job = client.table("render_jobs").select("*").eq("id", selected_item["render_job_id"]).execute().data[0]
            if selected_item.get("thumbnail_id"):
                thumbs = client.table("thumbnails").select("*").eq("id", selected_item["thumbnail_id"]).execute().data
                thumbnail = thumbs[0] if thumbs else None
            if selected_item["status"] == "pending_review":
                ready_at = datetime.fromisoformat(selected_item["ready_at"].replace("Z", "+00:00"))
                remaining_minutes = max(int((ready_at - datetime.now(timezone.utc)).total_seconds() // 60), 0)
    ctx.update(
        {
            "active": "publish",
            "counts": _counts(client),
            "items": items,
            "selected": selected_item,
            "render_job": render_job,
            "thumbnail": thumbnail,
            "remaining_minutes": remaining_minutes,
            "view": view if selected_item else "list",
        }
    )
    return templates.TemplateResponse("tab_publish.html", ctx)


@router.post("/publish/{upload_queue_id}/cancel")
def publish_cancel(request: Request, upload_queue_id: str):
    client = get_client()
    client.table("upload_queue").update({"status": "canceled"}).eq("id", upload_queue_id).execute()
    return RedirectResponse("/publish?toast=취소했어요", status_code=302)


@router.post("/publish/{upload_queue_id}/delete")
def delete_upload_queue_item(request: Request, upload_queue_id: str):
    """게시검토 탭 리스트 삭제 아이콘 — upload_queue 행 자체를 지운다(취소와 달리 목록에서 사라짐)."""
    client = get_client()
    client.table("upload_queue").delete().eq("id", upload_queue_id).execute()
    return RedirectResponse("/publish?toast=삭제했어요", status_code=302)


@router.post("/publish/{upload_queue_id}/publish")
def publish_now(request: Request, upload_queue_id: str):
    client = get_client()
    item = client.table("upload_queue").select("*").eq("id", upload_queue_id).execute().data[0]
    if item["status"] != "ready_to_publish":
        return RedirectResponse(f"/publish?selected={upload_queue_id}&view=detail&toast=아직+게시할+수+없는+상태예요", status_code=302)

    render_job = client.table("render_jobs").select("*").eq("id", item["render_job_id"]).execute().data[0]
    thumbnail_path = None
    if item.get("thumbnail_id"):
        thumbs = client.table("thumbnails").select("*").eq("id", item["thumbnail_id"]).execute().data
        thumbnail_path = thumbs[0]["image_path"] if thumbs else None

    try:
        video_id = publish_video(
            render_job["output_path"], item.get("youtube_title") or "", item.get("youtube_description") or "", thumbnail_path=thumbnail_path
        )
    except PublishError as exc:
        client.table("upload_queue").update({"status": "failed"}).eq("id", upload_queue_id).execute()
        return RedirectResponse(f"/publish?selected={upload_queue_id}&view=detail&toast=게시+실패:+{str(exc)[:60]}", status_code=302)

    client.table("upload_queue").update(
        {"status": "published", "youtube_video_id": video_id, "published_at": _now_iso()}
    ).eq("id", upload_queue_id).execute()
    return RedirectResponse("/publish?toast=게시했어요!+🎉", status_code=302)


# --- 정책 알림 목록 ---


@router.get("/policy-alerts", response_class=HTMLResponse)
def policy_alerts_page(request: Request):
    client = get_client()
    ctx = _base_ctx(request, client)
    alerts = client.table("policy_alerts").select("*, policy_snapshots(platform, policy_name, url)").order("detected_at", desc=True).execute().data
    ctx["alerts"] = alerts
    return templates.TemplateResponse("policy_alerts.html", ctx)


@router.post("/policy-alerts/{alert_id}/review")
def policy_alert_review(request: Request, alert_id: str, note: str = Form("")):
    client = get_client()
    client.table("policy_alerts").update(
        {"reviewed": True, "reviewed_at": _now_iso(), "note": note}
    ).eq("id", alert_id).execute()
    return RedirectResponse("/policy-alerts", status_code=302)
