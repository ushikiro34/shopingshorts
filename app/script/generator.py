"""3호 직원 — 대본 생성.

analysis_json + product 정보 + tone 파라미터 + needs_education 플래그를 받아
docs/03_interfaces.md 4번 스키마의 script_json을 생성한다.
"""

from __future__ import annotations

import json
import time

import anthropic

from app.config import ANTHROPIC_API_KEY, DEFAULT_TARGET_PERSONA
from app.script.prompts import build_system_prompt, build_user_prompt

MODEL = "claude-sonnet-4-5"


class ScriptGenerationError(RuntimeError):
    """생성 실패(파싱 실패, API 오류 포함)를 감싸는 명확한 예외."""


def _client() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise ScriptGenerationError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def generate_script(
    analysis_json: dict,
    product: dict,
    tone: str,
    needs_education: bool,
    target_persona: str = DEFAULT_TARGET_PERSONA,
    client: anthropic.Anthropic | None = None,
) -> dict:
    active_client = client or _client()
    system_prompt = build_system_prompt(tone, needs_education)
    user_prompt = build_user_prompt(analysis_json, product, target_persona)

    last_error: Exception | None = None
    for attempt in range(2):  # 최초 시도 + 재시도 1회 (AGENTS.md 코딩 컨벤션)
        try:
            message = active_client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = message.content[0].text
            return json.loads(text)
        except (json.JSONDecodeError, anthropic.APIError) as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.5)
                continue

    raise ScriptGenerationError(f"대본 생성 실패: {last_error}") from last_error
