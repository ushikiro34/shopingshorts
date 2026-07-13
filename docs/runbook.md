# Runbook — 운영 가이드

대시보드/워커 운영 중 사람이 판단해야 하는 상황과 대응 절차. 코드로 자동화된 부분은
`AGENTS.md`/`docs/00_project_overview.md`를 참조하고, 여기서는 "무엇을 언제 눌러야 하는가"에 집중한다.

## 배포 구성 (Railway 3 프로세스)

같은 이미지(`Dockerfile`)를 공유하는 서비스 3개를 만든다. 시작 커맨드만 다르다.

| 서비스 | 시작 커맨드 | 역할 | 실패 시 리스크 |
|---|---|---|---|
| web | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` | 대시보드 + API | 대시보드 접근 불가 (운영 중단) |
| render-worker | `python -m app.media.worker` | render_jobs 폴링, 이미지/TTS/FFmpeg 조립 | 렌더링 지연(재시작하면 이어서 처리) |
| upload-worker | `python -m app.upload.queue_worker` | upload_queue 냉각기간 경과 감지(외부 API 미호출) | 낮음 — 실패해도 유튜브에 아무 일도 안 생김 |

환경변수는 `.env.example` 참조. Railway 대시보드에 그대로 등록한다.

## 게시 검토 운영법 (가장 중요 — 절대규칙 4)

1. 대시보드 홈 또는 "게시검토" 탭에서 `pending_review`(냉각중) 항목은 그냥 기다린다. 급하게 게시할 필요가 없으면 손대지 않는다.
2. 냉각기간이 지나 `ready_to_publish`(게시가능, 빨간 배지)로 바뀌면, **영상/썸네일/제목·설명을 직접 한 번 더 확인**한다.
   - 대본 오류, 부적절한 이미지, 잘못된 상품 매칭이 없는지 육안 확인.
   - `고지문구 ✅` / `딥링크 ✅` 표시를 확인한다(미디어제작 탭에서도 동일하게 표시됨).
3. 문제가 있으면 **[취소]** — 언제든 가능하고 되돌릴 수 있다.
4. 문제가 없으면 **[게시]** → 확인 다이얼로그("정말 게시할까요? 되돌릴 수 없어요")에서 한 번 더 확인 → 이 순간에만 실제 유튜브 업로드가 발생한다.
5. 게시 실패 시(`failed`) — `error_message`를 확인하고, YouTube 인증/쿼터 문제인지 확인 후 재시도(다시 큐에 넣거나 승인 단계부터 반복).

**타이머만으로 게시되는 경로는 없다.** upload-worker는 상태만 바꾸고, 실제 업로드는 사람이 [게시]를 눌러야만 실행된다(`app/upload/publisher.py`는 오직 `/publish` 엔드포인트에서만 호출됨).

## 정책 알림 대응 절차

1. cron-job.org(또는 동등한 외부 스케줄러)가 주 1회 `POST /api/policy-check/run`을 호출하도록 설정(`POLICY_CHECK_SECRET`을 `X-Policy-Check-Secret` 헤더로 전달).
2. 변경이 감지되면 대시보드 상단에 배너가 뜬다. 배너 클릭 → 정책 알림 목록(`/policy-alerts`).
3. 각 알림에서 [정책 페이지 열기]로 실제 변경 내용을 사람이 읽는다.
4. 실제 영향이 있으면(예: 광고 고지 문구 요건 변경) `docs/00_project_overview.md`/`AGENTS.md`/대본 프롬프트(`app/script/prompts.py`)를 검토·수정한다.
5. 검토가 끝나면 메모를 남기고 [검토완료]를 누른다. 이 시스템은 "변경 여부 감지"만 하지 실제 대응은 사람이 판단한다.
6. 오탐(쿠키 배너 등 무관한 변경)이면 메모에 "실제 영향 없음"이라고 남기고 검토완료 처리한다.

## failed 복구 절차

| 상태 | 원인 예시 | 복구 |
|---|---|---|
| `render_jobs.status = failed` | 이미지 URL 깨짐, TTS 실패, ffmpeg 오류 | `error_message` 확인 → 원인 수정(예: 상품 이미지 URL 갱신) → 대본을 다시 승인(`/scripts/{id}/approve`)해 새 render_job 생성 |
| `upload_queue.status = failed` | YouTube 인증 만료, 업로드 API 오류 | `error_message` 확인 → `YOUTUBE_REFRESH_TOKEN` 등 자격 증명 점검 → 게시검토 탭에서 재시도(취소 후 미디어제작 탭에서 다시 게시 준비) |
| products가 중간에 멈춤 | 워커가 처리 전 프로세스 재시작 등 | render_jobs/upload_queue의 최신 상태를 확인해 해당 status로 products를 맞추거나, 처음부터 해당 단계를 다시 트리거 |

## 로컬 개발 환경 참고

- 로컬(Windows)에서는 한글 폰트로 시스템 `malgun.ttf`를 자동으로 쓴다. 배포 이미지는 `fonts-nanum`(Debian 패키지, SIL OFL 라이선스)을 설치해 `/usr/share/fonts/truetype/nanum/NanumGothic.ttf`를 쓴다 — 별도 폰트 파일을 리포에 커밋할 필요 없음(Dockerfile로 확인 완료).
- `assets/bgm/`가 비어 있으면 BGM 없이 렌더링된다(정상 동작). 실제 트랙은 Suno Pro 웹앱에서 월 1회 수동 생성해 채운다(API 연동 없음).
- `TTS_PROVIDER` 기본값은 `edge`(무료, 키 불필요). `elevenlabs`로 바꾸려면 유료 플랜 계정의 보이스가 필요하다(무료 플랜은 라이브러리 보이스를 API로 못 씀).
