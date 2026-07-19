"""네이버 쇼핑검색 오픈API 클라이언트.

AGENTS.md 절대 규칙 1은 "쿠팡 페이지 크롤링"만 금지한다. 이 모듈은 쿠팡과 무관하며,
네이버가 공식 제공하는 REST 오픈API(https://developers.naver.com)만 호출한다 —
페이지를 직접 파싱하는 크롤링이 아니다. 수동 등록 상품(mode=manual)의 대표 이미지를
자동으로 채우는 용도로 쓴다.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import httpx

from app.config import NAVER_CLIENT_ID, NAVER_CLIENT_SECRET

BASE_URL = "https://openapi.naver.com/v1/search/shop.json"
_TAG_RE = re.compile(r"</?b>")


class NaverSearchError(RuntimeError):
    """네이버 쇼핑검색 API 호출 실패(인증 오류 포함)를 감싸는 명확한 예외."""


@dataclass
class NaverProductResult:
    title: str
    image: str | None
    link: str | None
    lprice: int | None


def search_product_image(keyword: str) -> NaverProductResult | None:
    """상품명으로 검색해 가장 적합도 높은 결과 1건을 반환한다. 검색 결과가 없으면 None."""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        raise NaverSearchError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET이 설정되지 않았습니다.")

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": keyword, "display": 1, "sort": "sim"}

    last_error: Exception | None = None
    for attempt in range(2):  # 최초 시도 + 재시도 1회 (AGENTS.md 코딩 컨벤션)
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(BASE_URL, headers=headers, params=params)
            if response.status_code >= 400:
                raise NaverSearchError(
                    f"네이버 쇼핑검색 API 오류 (status={response.status_code}): {response.text[:300]}"
                )
            data = response.json()
            items = data.get("items") or []
            if not items:
                return None
            item = items[0]
            return NaverProductResult(
                title=_TAG_RE.sub("", item.get("title", "")),
                image=item.get("image") or None,
                link=item.get("link") or None,
                lprice=int(item["lprice"]) if item.get("lprice") else None,
            )
        except (httpx.HTTPError, NaverSearchError) as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.5)
                continue
    raise NaverSearchError(f"네이버 쇼핑검색 API 호출 실패: {last_error}") from last_error
