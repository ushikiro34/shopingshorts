from __future__ import annotations

from fastapi import HTTPException


def get_product_or_404(client, product_id: str) -> dict:
    result = client.table("products").select("*").eq("id", product_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")
    return result.data[0]
