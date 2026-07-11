"""Claude 응답에서 JSON을 안전하게 추출하는 공용 유틸.

프롬프트에 "JSON만 출력하라"고 지시해도 모델이 ```json ... ``` 코드펜스로
감싸서 응답하는 경우가 있어, 파싱 전에 펜스를 제거한다.
"""

from __future__ import annotations

import json
import re

_CODE_FENCE_START_RE = re.compile(r"^```[a-zA-Z]*\s*\n?")
_CODE_FENCE_END_RE = re.compile(r"\n?```\s*$")


def strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = _CODE_FENCE_START_RE.sub("", cleaned)
        cleaned = _CODE_FENCE_END_RE.sub("", cleaned)
    return cleaned.strip()


def parse_json_response(text: str) -> dict:
    return json.loads(strip_code_fence(text))
