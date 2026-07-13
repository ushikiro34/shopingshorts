"""5호 직원 — YouTube 업로드 (Phase 4).

AGENTS.md 절대 규칙 4: 이 모듈의 함수는 오직 /publish 엔드포인트가 호출됐을 때만
실행된다. 타이머·워커가 이 함수를 호출하는 코드 경로는 절대 만들지 않는다.
"""

from __future__ import annotations

import httpx

from app.config import YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
THUMBNAIL_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"


class PublishError(RuntimeError):
    """업로드 실패(인증/네트워크/API 오류 포함)를 감싸는 명확한 예외."""


def _get_access_token(client: httpx.Client) -> str:
    if not (YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET and YOUTUBE_REFRESH_TOKEN):
        raise PublishError("YOUTUBE_CLIENT_ID/YOUTUBE_CLIENT_SECRET/YOUTUBE_REFRESH_TOKEN이 설정되지 않았습니다.")
    response = client.post(
        TOKEN_URL,
        data={
            "client_id": YOUTUBE_CLIENT_ID,
            "client_secret": YOUTUBE_CLIENT_SECRET,
            "refresh_token": YOUTUBE_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        },
    )
    if response.status_code >= 400:
        raise PublishError(f"YouTube 토큰 갱신 실패 (status={response.status_code}): {response.text[:300]}")
    return response.json()["access_token"]


def publish_video(
    video_path: str,
    title: str,
    description: str,
    thumbnail_path: str | None = None,
    client: httpx.Client | None = None,
) -> str:
    """유튜브에 영상을 업로드하고 성공 시 youtube_video_id를 반환한다."""
    active_client = client or httpx.Client(timeout=180.0)
    try:
        access_token = _get_access_token(active_client)
        headers = {"Authorization": f"Bearer {access_token}"}

        metadata = {
            "snippet": {"title": title, "description": description, "categoryId": "22"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
        }
        init_res = active_client.post(
            f"{UPLOAD_URL}?uploadType=resumable&part=snippet,status",
            headers={
                **headers,
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "video/mp4",
            },
            json=metadata,
        )
        if init_res.status_code >= 400:
            raise PublishError(f"업로드 세션 생성 실패 (status={init_res.status_code}): {init_res.text[:300]}")
        upload_url = init_res.headers.get("Location")
        if not upload_url:
            raise PublishError("업로드 세션 URL(Location 헤더)을 받지 못했습니다.")

        with open(video_path, "rb") as f:
            video_bytes = f.read()
        upload_res = active_client.put(upload_url, headers={"Content-Type": "video/mp4"}, content=video_bytes)
        if upload_res.status_code >= 400:
            raise PublishError(f"영상 업로드 실패 (status={upload_res.status_code}): {upload_res.text[:300]}")
        video_id = upload_res.json()["id"]

        if thumbnail_path:
            with open(thumbnail_path, "rb") as f:
                thumb_bytes = f.read()
            thumb_res = active_client.post(
                f"{THUMBNAIL_URL}?videoId={video_id}",
                headers={**headers, "Content-Type": "image/jpeg"},
                content=thumb_bytes,
            )
            if thumb_res.status_code >= 400:
                raise PublishError(f"썸네일 설정 실패 (status={thumb_res.status_code}): {thumb_res.text[:300]}")

        return video_id
    except (httpx.HTTPError, OSError) as exc:
        raise PublishError(f"업로드 중 오류: {exc}") from exc
