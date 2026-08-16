from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, model_validator

from app.api.common import get_product_or_404
from app.config import DEFAULT_MIN_SCORE, DEFAULT_TARGET_PERSONA
from app.coupang.partners import CoupangPartnersError, create_deeplinks, search_products
from app.db import get_client
from app.discovery.education import detect_needs_education
from app.discovery.scoring import MAX_TOTAL_SCORE, ScoreInputs, calculate_score, score_story
from app.discovery.story_heuristic import count_emotional_keywords
from app.review.analyzer import ReviewAnalysisError, analyze_reviews
from app.script.formats import active_tone_choices
from app.script.generator import ScriptGenerationError, generate_script
from app.script.validator import ScriptValidationError, validate_script

router = APIRouter(prefix="/api", tags=["products"])


class DiscoverRequest(BaseModel):
    coupang_url: str | None = None
    keyword: str | None = None

    @model_validator(mode="after")
    def _one_of_url_or_keyword(self) -> "DiscoverRequest":
        if not self.coupang_url and not self.keyword:
            raise ValueError("coupang_url 또는 keyword 중 하나는 필수입니다.")
        return self


class ManualProductRequest(BaseModel):
    """(v2.2) 쿠팡 파트너스 API 키 미발급 기간의 임시 소싱 경로 — API 호출 없이 사람이 입력한 값으로 등록한다."""

    product_name: str
    price: int | None = None
    category: str | None = None
    image_urls: list[str] = []
    coupang_url: str | None = None
    review_count: int | None = None

    @model_validator(mode="after")
    def _product_name_required(self) -> "ManualProductRequest":
        if not self.product_name.strip():
            raise ValueError("product_name은 비어있을 수 없습니다.")
        return self


class ReviewInput(BaseModel):
    reviews_raw: str


class NeedsEducationPatch(BaseModel):
    needs_education: bool


class DeeplinkPatch(BaseModel):
    deeplink: str


class GenerateScriptRequest(BaseModel):
    tone: str
    target_persona: str | None = None


def _get_latest_review_or_400(client, product_id: str) -> dict:
    result = (
        client.table("reviews")
        .select("*")
        .eq("product_id", product_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=400, detail="리뷰가 입력되지 않았습니다. 먼저 리뷰를 등록하세요.")
    return result.data[0]


@router.post("/products/discover", status_code=201)
def discover_product(payload: DiscoverRequest):
    client = get_client()

    product_name = price = category = deeplink = coupang_url = None
    image_urls: list[str] = []
    rating_count: int | None = None

    if payload.keyword:
        try:
            results = search_products(payload.keyword)
        except CoupangPartnersError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if not results:
            raise HTTPException(status_code=404, detail=f"'{payload.keyword}' 검색 결과가 없습니다.")
        top = results[0]
        product_name = top.product_name
        price = top.product_price
        image_urls = [top.product_image] if top.product_image else []
        category = top.category_name
        coupang_url = top.product_url
        deeplink = top.product_url  # 파트너스 검색 API productUrl은 이미 제휴 링크
        rating_count = top.rating_count
    else:
        coupang_url = payload.coupang_url
        try:
            deeplinks = create_deeplinks([payload.coupang_url])
        except CoupangPartnersError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if not deeplinks or not deeplinks[0].shorten_url:
            raise HTTPException(status_code=502, detail="딥링크 생성에 실패했습니다.")
        deeplink = deeplinks[0].shorten_url
        # coupang_url 입력 경로는 크롤링 없이는 상품명/가격/이미지를 알 수 없다 (AGENTS.md 절대 규칙 1).
        # 이 필드들은 사람이 대시보드에서 보완 입력한다.

    needs_education = detect_needs_education(category, product_name)
    breakdown = calculate_score(ScoreInputs(review_count=rating_count, price=price))

    row = {
        "coupang_url": coupang_url,
        "keyword": payload.keyword,
        "product_name": product_name,
        "price": price,
        "image_urls": image_urls,
        "deeplink": deeplink,
        "category": category,
        "review_count": rating_count,
        "needs_education": needs_education,
        "status": "scored",
        **breakdown.as_dict(),
    }

    result = client.table("products").insert(row).execute()
    return result.data[0]


@router.post("/products/manual", status_code=201)
def register_product_manually(payload: ManualProductRequest):
    """(v2.2) 쿠팡 파트너스 API를 호출하지 않고 사람이 입력한 값만으로 상품을 등록한다.

    딥링크는 비워둔 채 생성되며, 사람이 파트너스 웹사이트에서 수동 생성한 뒤
    PATCH /api/products/{id}/deeplink로 등록한다.
    """
    client = get_client()

    needs_education = detect_needs_education(payload.category, payload.product_name)
    breakdown = calculate_score(ScoreInputs(review_count=payload.review_count, price=payload.price))

    row = {
        "coupang_url": payload.coupang_url,
        "product_name": payload.product_name,
        "price": payload.price,
        "image_urls": payload.image_urls,
        "deeplink": None,
        "category": payload.category,
        "review_count": payload.review_count,
        "needs_education": needs_education,
        "status": "scored",
        **breakdown.as_dict(),
    }

    result = client.table("products").insert(row).execute()
    return result.data[0]


@router.get("/products")
def list_products(min_score: int = DEFAULT_MIN_SCORE):
    result = (
        get_client()
        .table("products")
        .select("*")
        .gte("total_score", min_score)
        .order("total_score", desc=True)
        .execute()
    )
    return result.data


@router.post("/products/{product_id}/reviews", status_code=201)
def add_review(product_id: str, payload: ReviewInput):
    client = get_client()
    product = get_product_or_404(client, product_id)

    review_row = {"product_id": product_id, "reviews_raw": payload.reviews_raw}
    review_result = client.table("reviews").insert(review_row).execute()

    keyword_count = count_emotional_keywords(payload.reviews_raw)
    new_story_score = score_story(keyword_count)
    old_story_score = product.get("story_score") or 0
    old_total_score = product.get("total_score") or 0
    new_total_score = min(old_total_score - old_story_score + new_story_score, MAX_TOTAL_SCORE)

    update_result = (
        client.table("products")
        .update(
            {
                "story_score": new_story_score,
                "total_score": new_total_score,
                "status": "reviews_collected",
            }
        )
        .eq("id", product_id)
        .execute()
    )

    return {"review": review_result.data[0], "product": update_result.data[0]}


@router.patch("/products/{product_id}/needs-education")
def update_needs_education(product_id: str, payload: NeedsEducationPatch):
    client = get_client()
    get_product_or_404(client, product_id)
    result = (
        client.table("products")
        .update({"needs_education": payload.needs_education})
        .eq("id", product_id)
        .execute()
    )
    return result.data[0]


@router.patch("/products/{product_id}/deeplink")
def update_deeplink(product_id: str, payload: DeeplinkPatch):
    """(v2.2) 사람이 파트너스 웹사이트에서 수동 생성한 딥링크를 등록/수정한다."""
    client = get_client()
    get_product_or_404(client, product_id)
    result = (
        client.table("products")
        .update({"deeplink": payload.deeplink})
        .eq("id", product_id)
        .execute()
    )
    return result.data[0]


@router.post("/products/{product_id}/analyze-reviews", status_code=201)
def analyze_product_reviews(product_id: str):
    client = get_client()
    get_product_or_404(client, product_id)
    review = _get_latest_review_or_400(client, product_id)

    try:
        analysis_json = analyze_reviews(review["reviews_raw"])
    except ReviewAnalysisError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    analysis_result = (
        client.table("review_analysis")
        .insert({"review_id": review["id"], "analysis_json": analysis_json})
        .execute()
    )
    client.table("products").update({"status": "analyzed"}).eq("id", product_id).execute()
    return analysis_result.data[0]


@router.post("/products/{product_id}/generate-script", status_code=201)
def generate_product_script(product_id: str, payload: GenerateScriptRequest):
    client = get_client()
    product = get_product_or_404(client, product_id)

    if payload.tone not in active_tone_choices():
        raise HTTPException(status_code=400, detail=f"tone은 {active_tone_choices()} 중 하나여야 합니다.")

    review = _get_latest_review_or_400(client, product_id)
    analysis_result = (
        client.table("review_analysis")
        .select("*")
        .eq("review_id", review["id"])
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not analysis_result.data:
        raise HTTPException(status_code=400, detail="먼저 /analyze-reviews를 호출하세요.")
    analysis = analysis_result.data[0]

    needs_education = bool(product.get("needs_education", False))
    target_persona = payload.target_persona or DEFAULT_TARGET_PERSONA

    try:
        script_json = generate_script(
            analysis_json=analysis["analysis_json"],
            product=product,
            tone=payload.tone,
            needs_education=needs_education,
            target_persona=target_persona,
        )
    except ScriptGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        validate_script(script_json, review["reviews_raw"], needs_education)
    except ScriptValidationError as exc:
        raise HTTPException(
            status_code=422, detail={"message": "대본 검증 실패", "errors": exc.errors}
        ) from exc

    script_result = (
        client.table("scripts")
        .insert(
            {
                "product_id": product_id,
                "analysis_id": analysis["id"],
                "target_persona": target_persona,
                "tone": payload.tone,
                "script_json": script_json,
            }
        )
        .execute()
    )
    client.table("products").update({"status": "script_generated"}).eq("id", product_id).execute()
    return script_result.data[0]
