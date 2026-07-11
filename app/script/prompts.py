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
- product: 상품 등장 + 리뷰 근거 + CTA까지 포함하는 마무리 문장들 (가격은 언급하지 않는다)
CTA는 별도 단계가 아니라 product 단계 마지막 문장에 자연스럽게 포함한다."""

TONE_INSTRUCTIONS = {
    "불편해결": "일상의 불편함을 짚고, 상품이 그 불편을 없애준다는 실용적 해결 톤으로 쓴다.",
    "우월감": "이 상품을 쓰면 남들보다 한발 앞선 선택을 한다는 느낌을 주는 톤으로 쓴다.",
    "보상": "고생한 나에게 주는 선물/보상이라는 톤으로 쓴다.",
    "생활팁": "생활 노하우를 공유하는 친근한 정보성 톤으로 쓴다.",
    "사실형": "과장 없이 담백하게 사실과 근거 위주로 쓴다.",
    "생활형": "일상 대화하듯 편안하고 자연스러운 톤으로 쓴다.",
    "실리적": "가격 숫자 대신 '가성비'/'효율' 같은 개념으로 실속을 강조하는 톤으로 쓴다.",
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

# v2.2: 가격은 표기하지 않고 "본문 확인"으로 유도, 고지문구는 narration이 아니라
# youtube.description 마지막 줄에만 넣는다 (사용자 피드백 반영).
PRICE_INSTRUCTION = """가격은 narration/구조(structure)/youtube.title/youtube.description 어디에도
숫자로 표기하지 않는다 (예: "18,900원", "2만원대" 금지 — 가격은 변동될 수 있고 딥링크를 눌러야 최신가를
확인하게 유도하는 편이 낫다). 구매를 유도할 때는 "제품정보(가격 포함)는 본문에 있어요, 확인해보세요"처럼
"본문"/"더보기"/"설명란" 중 하나를 반드시 포함한 문구로 마무리한다."""

DISCLOSURE_PLACEMENT_INSTRUCTION = f"""고지문구는 narration(structure의 모든 필드, scenes[].narration)에는
절대 넣지 않는다 — 음성으로 낭독하지 않는다. youtube.description의 맨 마지막 줄에만 아래 문구를 정확히
그대로 넣는다: "{PARTNERS_DISCLOSURE}"
description 앞부분에는 상품 매력 요약과 구매 링크 안내를 넣는다: user 메시지의 product.deeplink 값이 있으면
그 URL을 그대로 포함하고, 없으면 "구매 링크는 본문 더보기에서 확인해 주세요"라는 안내문으로 대체한다.
그 다음 줄(빈 줄로 구분)에 위 고지문구를 붙인다."""


def _build_output_schema_example(needs_education: bool) -> dict:
    """needs_education 값에 맞는 educational_note 예시를 보여준다.

    항상 included=false 예시만 주면 모델이 지시문보다 예시를 따라가
    needs_education=true인 상품에도 educational_note를 비워버리는 문제가 있었다.
    """
    educational_note_example = (
        {"included": True, "text": "자외선은 피부 노화를 유발할 수 있어요."}
        if needs_education
        else {"included": False, "text": ""}
    )
    return {
        "structure": {
            "empathy": "...",
            "emotion": "...",
            "problem": "...",
            "solution": "...",
            "product": "... 제품정보는 본문에 있어요, 확인해보세요.",
        },
        "educational_note": educational_note_example,
        "tone": "생활팁",
        "scenes": [
            {"seq": 1, "narration": "...", "caption": "...", "image_index": 0, "duration_sec": 5},
            {"seq": 2, "narration": "...", "caption": "...", "image_index": 0, "duration_sec": 5},
        ],
        "disclosure": PARTNERS_DISCLOSURE,
        "estimated_duration_sec": 45,
        "youtube": {
            "title": "...",
            "description": f"... 구매 링크는 본문 더보기에서 확인해 주세요.\n\n{PARTNERS_DISCLOSURE}",
            "tags": ["..."],
        },
    }


def build_system_prompt(tone: str, needs_education: bool) -> str:
    if tone not in SCRIPT_TONES:
        raise ValueError(f"tone은 {SCRIPT_TONES} 중 하나여야 합니다: {tone}")

    education_block = EDUCATIONAL_NOTE_INSTRUCTION if needs_education else NO_EDUCATIONAL_NOTE_INSTRUCTION
    schema_example = _build_output_schema_example(needs_education)

    return f"""너는 쿠팡 파트너스 쇼츠 대본을 쓰는 AI 직원이다.

{STRUCTURE_INSTRUCTION}

톤 지시: {TONE_INSTRUCTIONS[tone]}

후기 분석 결과의 suggested_hook_angle과 emotional_keywords를 empathy 문장에 직접 반영하라.
예: 분석 결과에 "갱년기", "새벽에 깬다"가 반복되면 훅은 "요즘 새벽마다 깨시나요?"처럼 만든다.

{education_block}

{PRICE_INSTRUCTION}

{DISCLOSURE_PLACEMENT_INSTRUCTION}

제약(반드시 지켜야 하며, 어기면 시스템이 자동으로 반려한다):
- scenes 배열의 원소 개수는 반드시 3개 이상 8개 이하다. 9개 이상은 절대 금지. 5단계 구조를 scene 여러 개로
  나누더라도 총합이 8을 넘지 않게 통합하라 (예: problem+educational_note를 한 scene에 같이 담아도 된다).
- narration을 모두 합친 영상 길이(estimated_duration_sec)는 30~60초.
- narration에는 리뷰 원문 문장을 그대로 옮기지 않는다 (재구성된 표현만 사용).
- disclosure 필드에는 반드시 다음 문구를 정확히 그대로 넣는다: "{PARTNERS_DISCLOSURE}"
- tone 필드에는 "{tone}"을 그대로 넣는다.
- educational_note 필드는 위 지시를 정확히 따른다. 아래 예시의 included/text 값을 그대로 참고하라
  (예시가 아니라 지시 내용이 기준이다 — 이 상품의 needs_education은 {str(needs_education).lower()}이다).

다른 설명 없이 아래와 같은 형태의 JSON 객체 하나만 출력한다 (scenes는 예시일 뿐 실제로는 3~8개를 채운다):
{json.dumps(schema_example, ensure_ascii=False, indent=2)}"""


def build_user_prompt(
    analysis_json: dict,
    product: dict,
    target_persona: str = DEFAULT_TARGET_PERSONA,
) -> str:
    payload = {
        "product_name": product.get("product_name"),
        "category": product.get("category"),
        "deeplink": product.get("deeplink"),
        "target_persona": target_persona,
        "analysis": analysis_json,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
