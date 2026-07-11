from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, model_validator

from app.config import DEFAULT_MIN_SCORE
from app.coupang.partners import CoupangPartnersError, create_deeplinks, search_products
from app.db import get_client
from app.discovery.education import detect_needs_education
from app.discovery.scoring import MAX_TOTAL_SCORE, ScoreInputs, calculate_score, score_story
from app.discovery.story_heuristic import count_emotional_keywords

router = APIRouter(prefix="/api", tags=["products"])


class DiscoverRequest(BaseModel):
    coupang_url: str | None = None
    keyword: str | None = None

    @model_validator(mode="after")
    def _one_of_url_or_keyword(self) -> "DiscoverRequest":
        if not self.coupang_url and not self.keyword:
            raise ValueError("coupang_url 또는 keyword 중 하나는 필수입니다.")
        return self


class ReviewInput(BaseModel):
    reviews_raw: str
    rating_summary: str | None = None


class NeedsEducationPatch(BaseModel):
    needs_education: bool


def _get_product_or_404(client, product_id: str) -> dict:
    result = client.table("products").select("*").eq("id", product_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")
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
    product = _get_product_or_404(client, product_id)

    review_row = {
        "product_id": product_id,
        "reviews_raw": payload.reviews_raw,
        "rating_summary": payload.rating_summary,
    }
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
    _get_product_or_404(client, product_id)
    result = (
        client.table("products")
        .update({"needs_education": payload.needs_education})
        .eq("id", product_id)
        .execute()
    )
    return result.data[0]
