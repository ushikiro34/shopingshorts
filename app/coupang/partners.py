"""쿠팡 파트너스 오픈 API 클라이언트 (HMAC 인증).

AGENTS.md 절대 규칙 1: 이 모듈은 공식 오픈 API(HMAC 서명 요청)만 호출한다.
Selenium/requests로 쿠팡 페이지를 직접 파싱(크롤링)하는 코드는 절대 추가하지 않는다.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from app.config import COUPANG_ACCESS_KEY, COUPANG_SECRET_KEY

BASE_URL = "https://api-gateway.coupang.com"
SEARCH_PATH = "/v2/providers/affiliate_open_api/apis/openapi/products/search"
DEEPLINK_PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/deeplink"

_SIGNED_DATE_FORMAT = "%y%m%dT%H%M%SZ"


class CoupangPartnersError(RuntimeError):
    """파트너스 API 호출 실패(인증 오류 포함)를 감싸는 명확한 예외."""


@dataclass
class ProductSearchResult:
    product_id: str | None
    product_name: str | None
    product_price: int | None
    product_image: str | None
    product_url: str | None
    category_name: str | None
    is_rocket: bool = False
    is_free_shipping: bool = False
    rating_count: int | None = None


@dataclass
class DeeplinkResult:
    original_url: str
    shorten_url: str | None
    landing_url: str | None


def _signed_date(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime(_SIGNED_DATE_FORMAT)


def generate_hmac(method: str, url_path_with_query: str, secret_key: str, access_key: str) -> tuple[str, str]:
    """쿠팡 파트너스 서명 규격에 맞는 (signed_date, signature)를 반환한다."""
    signed_date = _signed_date()
    message = signed_date + method + url_path_with_query
    signature = hmac.new(
        secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return signed_date, signature


def _authorization_header(method: str, url_path_with_query: str) -> str:
    if not COUPANG_ACCESS_KEY or not COUPANG_SECRET_KEY:
        raise CoupangPartnersError(
            "COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY가 설정되지 않았습니다."
        )
    signed_date, signature = generate_hmac(
        method, url_path_with_query, COUPANG_SECRET_KEY, COUPANG_ACCESS_KEY
    )
    return (
        f"CEA algorithm=HmacSHA256, access-key={COUPANG_ACCESS_KEY}, "
        f"signed-date={signed_date}, signature={signature}"
    )


def _request(method: str, path: str, params: dict | None = None, json_body: dict | None = None) -> dict:
    query = urlencode(params) if params else ""
    path_with_query = f"{path}?{query}" if query else path
    headers = {
        "Authorization": _authorization_header(method, path_with_query),
        "Content-Type": "application/json;charset=UTF-8",
    }
    url = BASE_URL + path_with_query

    last_error: Exception | None = None
    for attempt in range(2):  # 최초 시도 + 재시도 1회 (AGENTS.md 코딩 컨벤션)
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.request(method, url, headers=headers, json=json_body)
            if response.status_code >= 400:
                raise CoupangPartnersError(
                    f"쿠팡 파트너스 API 오류 (status={response.status_code}): {response.text[:300]}"
                )
            return response.json()
        except (httpx.HTTPError, CoupangPartnersError) as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.5)
                continue
    raise CoupangPartnersError(f"쿠팡 파트너스 API 호출 실패: {last_error}") from last_error


def search_products(keyword: str, limit: int = 20) -> list[ProductSearchResult]:
    data = _request("GET", SEARCH_PATH, params={"keyword": keyword, "limit": limit})
    items = (data.get("data") or {}).get("productData") or []
    results = []
    for item in items:
        results.append(
            ProductSearchResult(
                product_id=str(item.get("productId")) if item.get("productId") else None,
                product_name=item.get("productName"),
                product_price=item.get("productPrice"),
                product_image=item.get("productImage"),
                product_url=item.get("productUrl"),
                category_name=item.get("categoryName"),
                is_rocket=bool(item.get("isRocket", False)),
                is_free_shipping=bool(item.get("isFreeShipping", False)),
                rating_count=item.get("ratingCount"),
            )
        )
    return results


def create_deeplinks(coupang_urls: list[str]) -> list[DeeplinkResult]:
    data = _request("POST", DEEPLINK_PATH, json_body={"coupangUrls": coupang_urls})
    items = data.get("data") or []
    results = []
    for item in items:
        results.append(
            DeeplinkResult(
                original_url=item.get("originalUrl"),
                shorten_url=item.get("shortenUrl"),
                landing_url=item.get("landingUrl"),
            )
        )
    return results
