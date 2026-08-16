# couparvi — Phase 1~4

쿠팡 파트너스 쇼츠 자동 제작 파이프라인. 현재 구현 범위는 **Phase 1(상품발굴 & 후기수집)**,
**Phase 2(AI 후기분석 & 대본작성)**, **Phase 3(미디어 파이프라인)**, **Phase 4(썸네일·업로드홀드·대시보드)**다.
전체 배경은 `docs/00_project_overview.md`, 규칙은 `AGENTS.md`, 운영 가이드는 `docs/runbook.md` 참조.

## 요구 사항

- Python 3.11+
- Supabase 프로젝트 (Postgres)
- 쿠팡 파트너스 API 액세스키/시크릿키 (없으면 `/api/products/manual` 임시 경로 사용 가능)
- Anthropic API 키 (Phase 2 — 후기 분석/대본 생성)
- TTS (Phase 3): 기본값은 `edge-tts`(키 불필요, `pip install`만 하면 바로 동작). ElevenLabs를
  쓰려면 `TTS_PROVIDER=elevenlabs` + API 키 필요(단 무료 플랜은 라이브러리 보이스가 API로 막혀있음)
- FFmpeg (`ffmpeg`, `ffprobe`가 PATH에 있어야 함, Phase 3 렌더링)
- 한글 폰트: 로컬 개발 시 Windows 시스템 폰트(malgun.ttf)를 자동으로 찾는다. `Dockerfile`이
  Debian `fonts-nanum` 패키지를 설치해 배포 환경(Linux)에서는 별도 폰트 파일 없이 동작한다
  (`/usr/share/fonts/truetype/nanum/NanumGothic.ttf`, 실제 Docker 빌드로 확인됨)
- Docker (Phase 4 배포용 이미지 빌드/실행 시)
- YouTube Data API 클라이언트 ID/시크릿/리프레시 토큰 (Phase 4 — 실제 게시. 없으면 게시 안전장치
  자체는 전부 동작하고 마지막 업로드 호출만 실패로 기록됨)

## 설치

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash
# .venv\Scripts\Activate.ps1    # PowerShell

pip install -r requirements.txt
cp .env.example .env
# .env에 COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY / SUPABASE_URL / SUPABASE_SERVICE_KEY 채우기
```

## 마이그레이션 적용

`migrations/001_init.sql` ~ `004_phase4.sql`을 순서대로 Supabase SQL Editor에 붙여넣어
실행하거나, `psql`로 적용한다.

```bash
psql "$SUPABASE_DB_URL" -f migrations/001_init.sql
psql "$SUPABASE_DB_URL" -f migrations/002_phase2.sql
psql "$SUPABASE_DB_URL" -f migrations/003_phase3.sql
psql "$SUPABASE_DB_URL" -f migrations/004_phase4.sql
```

대시보드 로그인 계정은 Supabase 대시보드(Authentication > Users)에서 수동으로 만든다
(회원가입 화면 없음, 단일 운영자 전제 — `docs/04_ui_spec.md` 0번).

## 실행

```bash
uvicorn app.main:app --reload
```

렌더링(Phase 3)과 게시 상태 전환(Phase 4)은 별도 워커 프로세스가 각각 폴링해 처리한다:

```bash
python -m app.media.worker         # render_jobs 폴링 (이미지/TTS/FFmpeg), 상시 구동(로컬 개발용)
python -m app.media.worker --once  # 큐가 비거나 제한 시간(기본 240초)을 넘기면 종료 — Railway Cron 배포용
python -m app.upload.queue_worker  # upload_queue 냉각기간 경과 감지 (외부 API 호출 없음)
```

`--once`는 render-worker를 상시 프로세스로 띄워두면 처리할 job이 없는 유휴 시간에도 계속
과금되는 문제 때문에 추가했다 — 처리할 render_job이 없으면 즉시 종료되므로 Railway Cron
Job(예: `*/5 * * * *`)으로 스케줄해 필요할 때만 컨테이너를 띄우는 용도다. 상세 배포 구성은
`docs/runbook.md` 참조.

- 헬스체크: `GET http://localhost:8000/health`
- API 문서: `http://localhost:8000/docs`
- 대시보드: `http://localhost:8000/` (로그인 필요)

### Docker로 실행

```bash
docker build -t couparvi .
docker run -p 8000:8000 --env-file .env couparvi
```

Railway 등에 배포할 때는 같은 이미지로 서비스 3개(web/render-worker/upload-worker)를 만들고
시작 커맨드만 다르게 지정한다 — 상세는 `docs/runbook.md` 참조.

## 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/products/discover` | body: `{coupang_url}` 또는 `{keyword}`. 상품정보+점수 계산 → `scored` |
| POST | `/api/products/manual` | (v2.2, 파트너스 키 미발급 시 임시 경로) body: `{product_name, price?, category?, image_urls?, coupang_url?, review_count?}`. API 호출 없이 등록 → `scored`, `deeplink`는 비움 |
| PATCH | `/api/products/{id}/deeplink` | (v2.2) body: `{deeplink}`. 파트너스 웹사이트에서 수동 생성한 딥링크 등록 |
| GET | `/api/products?min_score=80` | 추천 후보 목록 (기본 80점 이상) |
| POST | `/api/products/{id}/reviews` | 리뷰 원문+별점 저장 → `reviews_collected`, story_score 재계산 |
| PATCH | `/api/products/{id}/needs-education` | `needs_education` 수동 토글 |
| POST | `/api/products/{id}/analyze-reviews` | 최신 리뷰를 Claude로 분석 → `review_analysis` 저장, status `analyzed` |
| POST | `/api/products/{id}/generate-script` | body: `{tone, target_persona?}`. 구조+톤 이중 프롬프트로 대본 생성·검증 → `scripts` 저장, status `script_generated` |
| PATCH | `/api/scripts/{id}` | `script_json` 수동 수정, `version` +1 |
| POST | `/api/scripts/{id}/approve` | 대본 승인 → `render_jobs` enqueue(`status=queued`), status `script_approved` |
| GET | `/api/render-jobs/{id}` | 렌더 작업 상태 조회 (`queued/generating_images/generating_audio/assembling/done/failed`) |
| POST | `/api/render-jobs/{id}/generate-thumbnail` | 훅 텍스트+상품 실사진(또는 2D 그래픽 폴백)으로 썸네일 생성, status `thumbnail_generated` |
| POST | `/api/render-jobs/{id}/queue-upload` | body: `{cooldown_minutes?}`(기본 240). `upload_queue`에 `pending_review`로 enqueue, status `queued_for_upload` |
| GET | `/api/upload-queue?status=` | 게시 큐 목록 |
| POST | `/api/upload-queue/{id}/cancel` | 언제든 취소 → `canceled` |
| POST | `/api/upload-queue/{id}/publish` | **사람이 명시적으로 호출.** `ready_to_publish`가 아니면 403. 항상 `privacyStatus=private`로 업로드하며, 성공 시 `published`+`youtube_video_id` (실제 공개/예약은 유튜브 스튜디오에서 별도 진행) |
| POST | `/api/policy-check/run` | `MONITORED_POLICIES` fetch+해시비교, 변경 시 `policy_alerts` 생성. 헤더 `X-Policy-Check-Secret` 필요(설정 시) |
| GET | `/api/policy-alerts?reviewed=` | 정책 변경 알림 목록 |
| POST | `/api/policy-alerts/{id}/review` | body: `{note?}` → `reviewed=true` |

대시보드 페이지 라우트(`/`, `/discover`, `/scripts`, `/media`, `/publish`, `/policy-alerts`,
`/login`)는 로그인이 필요하다. `/api/*`는 Phase 1~3부터 이어진 내부 API 계약이라 인증 없이 유지한다.

`keyword`로 발굴하면 파트너스 검색 API에서 상품명·가격·이미지·카테고리·리뷰수까지 채워진다.
`coupang_url`로 발굴하면 딥링크만 생성되고 나머지 필드는 비어 있다 — 크롤링 없이는 상세정보를
가져올 수 없기 때문(AGENTS.md 절대 규칙 1). 이 경우 상품명 등은 사람이 보완 입력한다(Phase 1 이후 확장).

**쿠팡 파트너스 API 키가 아직 없다면** `/api/products/manual`로 상품을 직접 등록하고(리뷰는 어느
오픈마켓에서 복사해도 무방 — 원래도 리뷰는 사람이 수동 입력하고 AI가 재구성만 함), 딥링크는
partners.coupang.com에서 수동 생성해 `PATCH /api/products/{id}/deeplink`로 등록하면 Phase 2 이후
파이프라인을 동일하게 쓸 수 있다. 상세 배경은 `docs/00_project_overview.md`의 "파트너스 API 키
미발급 기간의 임시 소싱 방식" 참조.

`tone`은 `불편해결/우월감/보상/생활팁/사실형/생활형/실리적` 7종 중 하나. 생성된 대본은
`app/script/validator.py`가 구조(5필드)·톤·disclosure·scenes 개수/길이·리뷰 원문 유출(8단어 이상
연속 일치)·`educational_note`·가격 미표기·본문 유도 CTA 규칙을 모두 통과해야 저장된다. 검증 실패 시
422와 함께 사유 목록을 반환한다.

`approve` 후 실제 렌더링은 `python -m app.media.worker`(또는 `app.media.worker.poll_and_process_once`)가
`render_jobs`를 폴링해 처리한다. 이미지는 `products.image_urls`(파트너스 실사진)를 그대로 쓰고,
`needs_education=true`인 상품의 사실설명 씬과 실사 이미지가 없는 경우는 2D 그래픽(`app/media/graphics.py`)으로
대체한다. BGM은 `assets/bgm/*.mp3`가 있으면 무작위로 섞고, 없으면 BGM 없이 진행한다.

## 테스트

```bash
pytest tests/ -v
```

- `tests/test_scoring.py`: 스코어링 배점(overview.md 표)이 항목별 상한을 넘지 않고 합계가 100을 초과하지 않는지 검증
- `tests/test_education.py`: `EDUCATION_TRIGGER_KEYWORDS` 매칭 검증
- `tests/test_script_validator.py`: 대본 스키마/원문유출/educational_note 규칙 검증 (API 키 불필요)
- `tests/test_review_script_generation.py`: analyzer/generator의 JSON 파싱·재시도 로직을 가짜(fake) Anthropic 클라이언트로 검증 (API 키 불필요)
- `tests/test_media_images.py`, `test_media_graphics.py`: 이미지 캔버스 합성·2D 그래픽 생성 검증 (합성 이미지, 네트워크/API 키 불필요)
- `tests/test_media_tts.py`: ElevenLabs/edge-tts 양쪽 경로의 재시도 로직을 가짜 client/factory로 검증 + 실제 edge-tts 네트워크 호출 1건(키 불필요) + ffprobe 실측(ffmpeg 필요)
- `tests/test_media_render.py`: ffmpeg 명령/필터 문자열 조립 로직 검증 (ffmpeg 실행 불필요)
- `tests/test_media_render_integration.py`: 실제 ffmpeg로 2-scene 영상을 끝까지 조립해 해상도/코덱/길이 검증 (ffmpeg 필요, `ffmpeg`가 없으면 자동 skip)
- `tests/test_media_thumbnail.py`: 훅 텍스트 자동 줄바꿈 포함 썸네일 생성 검증
- `tests/test_upload_publisher.py`: YouTube 업로드 흐름(토큰→업로드→썸네일 설정)을 가짜 client로 검증
- `tests/test_upload_queue_worker.py`: 냉각기간 경과 항목만 정확히 `ready_to_publish`로 전환하는지 검증 (가짜 client, 외부 API 호출 없음)

## 게시 안전장치 (AGENTS.md 절대 규칙 4)

`app/upload/queue_worker.py`(내부 상태 전환만, 외부 API 미호출)와 `app/upload/publisher.py`
(실제 유튜브 업로드, `/publish` 엔드포인트에서만 호출)로 분리되어 있다. 냉각기간(기본 240분) +
사람의 명시적 클릭 + 대시보드 확인 다이얼로그, 3중 안전장치 — 상세 운영법은 `docs/runbook.md`.

업로드는 항상 `privacyStatus=private`로 이루어진다(2026-08-17~) — 이 앱은 검토를 마친 영상을
유튜브에 올리는 것까지만 책임지고, 실제 전체공개 전환/예약은 사람이 유튜브 스튜디오에서 직접
진행한다. 상시 서버를 띄워두지 않고 작업할 때만 로컬에서 켜는 운영 방식과 맞춘 결정이다.

## 제외 범위 (Phase 1~4가 아님)

Phase 5(확장), AI 실사 이미지 생성(로드맵에서 완전 제외), 인스타그램 API 자동 게시(수동 다운로드-업로드만),
다중 사용자/권한 관리(단일 운영자 전제) — `docs/phase1_spec.md` ~ `docs/phase4_spec.md` 참조.
