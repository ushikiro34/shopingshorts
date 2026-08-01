"""Veo(구글 영상 생성) 호출 — 이미 만든 씬 스틸컷을 시작 프레임으로 넣어 실제 움직임이 있는
짧은 영상으로 애니메이션한다.

정지 사진 + Ken Burns 팬만으로는 일부 씬이 어색해 보인다는 피드백으로, 가장 임팩트가 큰
후킹(첫 씬)에 시범 적용한다(사용자와 논의 후 범위 확정). 시작 프레임은 이미 상품 실물을
유지하도록 만든 이미지라 영상에서도 초반 형태는 그대로 유지되지만, Veo가 재생 중간에
브랜드 로고 같은 작은 텍스트를 다르게 그릴 수 있다는 한계는 실측으로 확인했다 — 아주
짧은 후킹 컷이라 감내할 만하다고 판단했다.

프롬프트는 동작 폭을 의도적으로 작게 제한한다 — 실측 비교(동일 상품, 재렌더)에서 동작이
클수록(예: 가전제품 문이 저절로 열리는 등) 형태 붕괴·왜곡이 눈에 띄게 늘어나는 걸 확인했다
(사용자 피드백: "할루시네이션 같다"). 이 프로젝트는 상품 카테고리가 계속 늘어날 예정이라
매번 다른 상품마다 프롬프트를 따로 튜닝할 수 없다 — 그래서 "허용되는 움직임"과 "절대
금지되는 움직임"을 상품 종류에 무관하게 일반화된 문구로 명시해, 카테고리가 바뀌어도 같은
수준의 안정성을 기대할 수 있게 한다.
"""

from __future__ import annotations

import base64
import time

import httpx

from app.config import GEMINI_API_KEY

MODEL = "veo-3.1-fast-generate-preview"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
SUBMIT_URL = f"{BASE_URL}/models/{MODEL}:predictLongRunning"

# Veo 작업은 완료까지 몇 초~몇 분 걸릴 수 있어 폴링한다 — 최대 대기시간의 상한.
POLL_INTERVAL_SEC = 10
MAX_POLL_ATTEMPTS = 30  # 최대 5분


class VideoGenerationError(RuntimeError):
    """영상 생성 실패(제출/폴링/다운로드 오류, 시간 초과 포함)를 감싸는 명확한 예외."""


def _build_prompt(visual: str, narration: str) -> str:
    return (
        f"참고 이미지를 시작 프레임으로 사용해 아주 미묘하고 절제된 움직임만 있는 짧은 "
        f"영상으로 만들어줘. 상품의 실제 형태·색상·로고·크기 비율은 시작 프레임에 나온 "
        f"그대로 끝까지 유지해줘 — 재생 중에 상품이 실제보다 커지거나 작아지지 않게 하고, "
        f"인물의 몸이나 손에 가려 상품이 안 보이는 순간이 없게 해줘.\n"
        f"허용되는 움직임: 카메라의 아주 미세한 흔들림이나 서서히 다가가는 정도의 팬/줌, "
        f"인물의 자연스러운 숨쉬기·미세한 무게중심 이동·시선이나 고개를 살짝 돌리는 정도.\n"
        f"절대 금지되는 움직임: 상품의 문·뚜껑·버튼·손잡이·다이얼 등 움직이는 부분을 열거나 "
        f"닫거나 조작하는 동작(어떤 종류의 상품이든 마찬가지), 인물이 팔을 크게 휘젓거나 "
        f"자세를 큰 폭으로 바꾸는 동작, 걷거나 이동하는 동작. 이런 큰 동작은 AI 영상 특유의 "
        f"형태 붕괴·왜곡(할루시네이션)을 일으키기 쉬우니 절대 넣지 마.\n"
        f"장면 연출: {visual}\n"
        f"장면 맥락(참고용): {narration}\n"
        f"인물이 입을 움직여 말하거나 대사를 하는 것처럼 보이지 않게 해줘 — 입은 다물거나 "
        f"자연스러운 표정만 짓게 하고, 말하는 듯한 입모양·립싱크는 절대 넣지 마.\n"
        f"세로 방향(9:16) 영상, 사실적인 사진 스타일, 화면에 텍스트를 넣지 마."
    )


def generate_scene_video(
    image_bytes: bytes,
    image_media_type: str,
    visual: str,
    narration: str,
    client: httpx.Client | None = None,
) -> bytes:
    """씬 스틸컷을 시작 프레임으로 애니메이션한 mp4 바이트를 반환한다. 실패하면 VideoGenerationError.

    Veo는 즉시 응답하지 않는 비동기(long-running operation) API라 제출 -> 폴링 -> 다운로드
    3단계를 거친다. 후킹(첫 씬)은 반드시 영상으로 나가야 한다고 결정해(사용자 피드백),
    콘텐츠 안전 필터 등으로 인한 비결정적 실패에 대비해 AGENTS.md 컨벤션(외부 API 호출
    재시도 1회)을 그대로 적용한다 — 렌더 하나당 이 호출은 첫 씬 1개뿐이라 재시도해도
    전체 렌더 시간에 미치는 영향이 제한적이다.
    """
    if not GEMINI_API_KEY:
        raise VideoGenerationError("GEMINI_API_KEY가 설정되지 않았습니다.")

    active_client = client or httpx.Client(timeout=60.0)

    last_error: Exception | None = None
    for attempt in range(2):  # 최초 시도 + 재시도 1회 (AGENTS.md 코딩 컨벤션)
        try:
            return _generate_scene_video_once(active_client, image_bytes, image_media_type, visual, narration)
        except VideoGenerationError as exc:
            last_error = exc

    raise VideoGenerationError(f"Veo 영상 생성 실패(재시도 포함): {last_error}") from last_error


def _generate_scene_video_once(
    active_client: httpx.Client,
    image_bytes: bytes,
    image_media_type: str,
    visual: str,
    narration: str,
) -> bytes:
    body = {
        "instances": [
            {
                "prompt": _build_prompt(visual, narration),
                "image": {
                    "bytesBase64Encoded": base64.standard_b64encode(image_bytes).decode("utf-8"),
                    "mimeType": image_media_type,
                },
            }
        ],
        "parameters": {"aspectRatio": "9:16"},
    }

    submit_res = active_client.post(SUBMIT_URL, params={"key": GEMINI_API_KEY}, json=body)
    if submit_res.status_code >= 400:
        raise VideoGenerationError(f"Veo 영상 생성 요청 실패 (status={submit_res.status_code}): {submit_res.text[:500]}")
    op_name = submit_res.json().get("name")
    if not op_name:
        raise VideoGenerationError(f"응답에 operation 이름이 없습니다: {submit_res.text[:500]}")

    poll_url = f"{BASE_URL}/{op_name}"
    for _ in range(MAX_POLL_ATTEMPTS):
        time.sleep(POLL_INTERVAL_SEC)
        poll_res = active_client.get(poll_url, params={"key": GEMINI_API_KEY})
        if poll_res.status_code >= 400:
            raise VideoGenerationError(f"Veo 작업 조회 실패 (status={poll_res.status_code}): {poll_res.text[:500]}")
        data = poll_res.json()
        if data.get("done"):
            try:
                samples = data["response"]["generateVideoResponse"]["generatedSamples"]
                video_uri = samples[0]["video"]["uri"]
            except (KeyError, IndexError) as exc:
                raise VideoGenerationError(f"완료 응답에 영상 URI가 없습니다: {str(data)[:500]}") from exc
            download_res = active_client.get(video_uri, params={"key": GEMINI_API_KEY}, follow_redirects=True)
            if download_res.status_code >= 400:
                raise VideoGenerationError(f"영상 다운로드 실패 (status={download_res.status_code})")
            return download_res.content

    raise VideoGenerationError(f"Veo 작업이 {MAX_POLL_ATTEMPTS * POLL_INTERVAL_SEC}초 안에 끝나지 않았습니다.")
