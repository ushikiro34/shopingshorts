"""3호 직원 — 대본 프롬프트: 구조(고정 5단계) + 톤(7종 가변) 이중 프롬프트.

docs/03_interfaces.md 4번 스키마와 docs/00_project_overview.md "대본 설계" 절 기준.
"""

from __future__ import annotations

import json

from app.config import DEFAULT_TARGET_PERSONA, PARTNERS_DISCLOSURE, SCRIPT_TONES

STRUCTURE_INSTRUCTION = """구조는 정확히 5단계로 고정한다: 공감 -> 감정 -> 문제제기 -> 해결 -> 상품.
- empathy: 첫 3초, 타겟이 "어 이거 내 얘기네" 하는 공감 문장
- emotion: 공감을 구체적 감정(답답함/불안/설렘 등)으로 증폭시키는 문장
- problem: 그 감정의 원인이 되는 문제를 명확히 짚는 문장
- solution: 문제를 해결하는 방향성 제시 (아직 상품명 등장 전)
- product: 상품 등장 + 리뷰 근거 + 가격/CTA까지 포함하는 마무리 문장들
CTA와 고지문구는 별도 단계가 아니라 product 단계 마지막 문장에 자연스럽게 포함한다."""

TONE_INSTRUCTIONS = {
    "불편해결": "일상의 불편함을 짚고, 상품이 그 불편을 없애준다는 실용적 해결 톤으로 쓴다.",
    "우월감": "이 상품을 쓰면 남들보다 한발 앞선 선택을 한다는 느낌을 주는 톤으로 쓴다.",
    "보상": "고생한 나에게 주는 선물/보상이라는 톤으로 쓴다.",
    "생활팁": "생활 노하우를 공유하는 친근한 정보성 톤으로 쓴다.",
    "사실형": "과장 없이 담백하게 사실과 근거 위주로 쓴다.",
    "생활형": "일상 대화하듯 편안하고 자연스러운 톤으로 쓴다.",
    "실리적": "가격 대비 효용을 강조하는 실속형 톤으로 쓴다.",
}

EDUCATIONAL_NOTE_INSTRUCTION = """이 상품은 needs_education=true이므로 problem 단계 직후에 삽입할
educational_note를 함께 생성한다. 규칙:
- 널리 합의된 상식 수준의 사실만 사용한다 (예: "자외선은 피부 노화·화상을 유발할 수 있다"는 가능, 특정 질병의
  진단·치료 효과를 암시하는 표현은 불가).
- 의학적 조언·진단처럼 들리는 표현을 쓰지 않는다 ("~하면 안 걸립니다", "치료됩니다" 등 금지).
- 과장·확정적 인과 표현 대신 "~일 수 있어요", "~로 알려져 있어요" 같은 절제된 어투를 쓴다.
educational_note는 {"included": true, "text": "..."} 형태로 채운다."""

NO_EDUCATIONAL_NOTE_INSTRUCTION = (
    'educational_note는 이 상품에 해당하지 않으므로 {"included": false, "text": ""}로 둔다.'
)

OUTPUT_SCHEMA_EXAMPLE = {
    "structure": {
        "empathy": "...",
        "emotion": "...",
        "problem": "...",
        "solution": "...",
        "product": "...",
    },
    "educational_note": {"included": False, "text": ""},
    "tone": "생활팁",
    "scenes": [
        {"seq": 1, "narration": "...", "caption": "...", "image_index": 0, "duration_sec": 5}
    ],
    "disclosure": PARTNERS_DISCLOSURE,
    "estimated_duration_sec": 45,
    "youtube": {"title": "...", "description": "...", "tags": ["..."]},
}


def build_system_prompt(tone: str, needs_education: bool) -> str:
    if tone not in SCRIPT_TONES:
        raise ValueError(f"tone은 {SCRIPT_TONES} 중 하나여야 합니다: {tone}")

    education_block = EDUCATIONAL_NOTE_INSTRUCTION if needs_education else NO_EDUCATIONAL_NOTE_INSTRUCTION

    return f"""너는 쿠팡 파트너스 쇼츠 대본을 쓰는 AI 직원이다.

{STRUCTURE_INSTRUCTION}

톤 지시: {TONE_INSTRUCTIONS[tone]}

후기 분석 결과의 suggested_hook_angle과 emotional_keywords를 empathy 문장에 직접 반영하라.
예: 분석 결과에 "갱년기", "새벽에 깬다"가 반복되면 훅은 "요즘 새벽마다 깨시나요?"처럼 만든다.

{education_block}

제약:
- scenes는 3~8개, narration을 합친 전체 영상 길이(estimated_duration_sec)는 30~60초.
- narration에는 리뷰 원문 문장을 그대로 옮기지 않는다 (재구성된 표현만 사용).
- disclosure 필드에는 반드시 다음 문구를 정확히 그대로 넣는다: "{PARTNERS_DISCLOSURE}"
- tone 필드에는 "{tone}"을 그대로 넣는다.

다른 설명 없이 아래와 같은 형태의 JSON 객체 하나만 출력한다:
{json.dumps(OUTPUT_SCHEMA_EXAMPLE, ensure_ascii=False, indent=2)}"""


def build_user_prompt(
    analysis_json: dict,
    product: dict,
    target_persona: str = DEFAULT_TARGET_PERSONA,
) -> str:
    payload = {
        "product_name": product.get("product_name"),
        "price": product.get("price"),
        "category": product.get("category"),
        "target_persona": target_persona,
        "analysis": analysis_json,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
