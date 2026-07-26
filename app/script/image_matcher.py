"""화면 연출(visual) 문구를 바탕으로, 후보 이미지 중 씬마다 가장 잘 맞는 컷을 고른다.

app/review/ocr.py와 같은 Claude vision 호출 패턴을 쓴다 — 대본 생성(app/script/generator.py)은
텍스트만 다루므로, 후보 사진을 실제로 "보고" 고르는 건 별도 단계로 분리했다.
"""

from __future__ import annotations

import base64
import json
import time

import anthropic

from app.config import ANTHROPIC_API_KEY
from app.llm_utils import parse_json_response
from app.media.images import download_image

MODEL = "claude-sonnet-4-5"


class ImageMatchError(RuntimeError):
    """이미지 매칭 실패(다운로드/파싱/API 오류 포함)를 감싸는 명확한 예외."""


def _client() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise ImageMatchError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _guess_media_type(image_bytes: bytes) -> str:
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def select_scene_images(
    scenes: list[dict], image_urls: list[str], client: anthropic.Anthropic | None = None
) -> dict[int, int]:
    """{seq: image_index} — 씬별로 가장 어울리는 후보 이미지 번호를 고른다.

    후보가 1장 이하면 고를 게 없으므로 API를 호출하지 않고 전부 0으로 매핑한다.
    """
    if len(image_urls) <= 1:
        return {scene["seq"]: 0 for scene in scenes}

    content: list[dict] = []
    for i, url in enumerate(image_urls):
        try:
            image_bytes = download_image(url)
        except Exception as exc:
            raise ImageMatchError(f"이미지 {i} 다운로드 실패: {exc}") from exc
        content.append({"type": "text", "text": f"이미지 {i}:"})
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": _guess_media_type(image_bytes),
                    "data": base64.standard_b64encode(image_bytes).decode("utf-8"),
                },
            }
        )

    scenes_desc = [
        {"seq": scene["seq"], "visual": scene.get("visual", ""), "narration": scene.get("narration", "")}
        for scene in scenes
    ]
    content.append(
        {
            "type": "text",
            "text": (
                "위 사진들은 번호(0부터 시작)가 매겨진 후보 이미지다. 아래 씬 목록의 visual(화면 연출)과 "
                "narration 내용을 보고, 씬마다 가장 잘 어울리는 이미지 번호를 하나씩 골라라. "
                "같은 이미지를 여러 씬에서 재사용해도 된다. 다른 설명 없이 JSON 객체 하나만 출력한다 — "
                '형태: {"1": 0, "2": 2} (키는 seq를 문자열로, 값은 0부터 시작하는 이미지 번호).\n\n'
                f"씬 목록: {json.dumps(scenes_desc, ensure_ascii=False)}"
            ),
        }
    )

    active_client = client or _client()
    last_error: Exception | None = None
    for attempt in range(2):  # 최초 시도 + 재시도 1회 (AGENTS.md 코딩 컨벤션)
        try:
            message = active_client.messages.create(
                model=MODEL,
                max_tokens=1024,
                messages=[{"role": "user", "content": content}],
            )
            raw = parse_json_response(message.content[0].text)
            return {int(seq): int(idx) for seq, idx in raw.items()}
        except (json.JSONDecodeError, ValueError, anthropic.APIError) as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.5)
                continue

    raise ImageMatchError(f"이미지 매칭 실패: {last_error}") from last_error
