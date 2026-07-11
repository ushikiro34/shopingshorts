"""사실설명(educational_note) 대상 여부 자동 판단.

docs/03_interfaces.md 8번 — EDUCATION_TRIGGER_KEYWORDS 매칭.
사람이 대시보드에서 재검토·수정 가능 (PATCH /api/products/{id}/needs-education).
"""

from __future__ import annotations

from app.config import EDUCATION_TRIGGER_KEYWORDS


def detect_needs_education(category: str | None, product_name: str | None) -> bool:
    text = f"{category or ''} {product_name or ''}"
    return any(keyword in text for keyword in EDUCATION_TRIGGER_KEYWORDS)
