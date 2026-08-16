# Runbook — 운영 가이드

대시보드/워커 운영 중 사람이 판단해야 하는 상황과 대응 절차. 코드로 자동화된 부분은
`AGENTS.md`/`docs/00_project_overview.md`를 참조하고, 여기서는 "무엇을 언제 눌러야 하는가"에 집중한다.

## 배포 구성 (Railway — web/upload-worker 상시 + render-worker Cron)

같은 이미지(`Dockerfile`)를 공유하는 서비스 3개를 만든다. 시작 커맨드만 다르다.

| 서비스 | 시작 커맨드 | 역할 | 실패 시 리스크 |
|---|---|---|---|
| web | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` | 대시보드 + API | 대시보드 접근 불가 (운영 중단) |
| render-worker | `python -m app.media.worker --once` (Cron Job, 예: `*/5 * * * *`) | render_jobs 폴링, 이미지/TTS/FFmpeg 조립 | 렌더링 지연(다음 스케줄에 이어서 처리) |
| upload-worker | `python -m app.upload.queue_worker` | upload_queue 냉각기간 경과 감지(외부 API 미호출) | 낮음 — 실패해도 유튜브에 아무 일도 안 생김 |

render-worker는 상시 프로세스로 띄워두면 처리할 job이 없는 유휴 시간에도 계속 과금되는
문제(사용자 피드백, 2026-08-17)가 있어 Railway Cron Job으로 전환했다. `--once`는 큐가
비거나 제한 시간(기본 240초, `run_worker_batch`의 `max_duration_sec`)을 넘기면 프로세스를
종료한다 — 이미 시작한 렌더링 하나는 중간에 끊지 않고 끝까지 실행한다. 크론 주기보다
렌더링이 길어져 다음 스케줄과 겹치더라도, `poll_and_process_once`가 `queued`→`claimed`
원자적 업데이트로 job을 선점하므로 같은 job이 두 인스턴스에서 동시에 처리되지 않는다.
크론 주기는 렌더 1건의 평균 소요 시간보다 짧게 잡지 않는다(너무 짧으면 겹침만 늘고 실익이
없다) — 트래픽이 늘면 주기를 좁히거나 상시 프로세스로 되돌리는 것을 고려한다.

환경변수는 `.env.example` 참조. Railway 대시보드에 그대로 등록한다.

## 운영 시작 전 점검 TODO (2026-07-27 기록)

- **POST 후 리다이렉트 URL에 상품 ID/토스트 메시지가 쿼리스트링으로 노출되는 문제.** 대본 생성/승인,
  게시 준비 등 POST 액션 처리 후 `RedirectResponse(f"/scripts?selected={{id}}&view=detail&toast=...")`
  형태로 302를 돌려주는데, 브라우저가 이 리다이렉트 대상(GET) URL로 주소창을 갱신하면서 상품 ID와
  토스트 문구가 그대로 URL에 남는다 — POST/Redirect/GET 패턴 자체의 정상 동작이라 로컬이든 Railway든
  동일하게 나타난다(호스팅 환경 차이가 아님).
  - 사용자 피드백: 로직이 어느 정도 구현되고 실제 운영(Railway) 단계에 들어가기 전에 보안 관점에서
    다시 점검하고 싶다고 요청함 (2026-07-27).
  - 점검 시 고려할 방향: 쿼리스트링 대신 경로 기반(`/scripts/{id}`)으로 바꾸거나, `toast` 메시지를
    쿼리스트링이 아니라 세션(플래시 메시지)으로 옮겨서 URL에서 최소한 토스트 문구라도 제거하는 방법 등.
  - 지금 당장 코드를 바꾸지 않고 TODO로만 남겨둔 상태 — 실제 우선순위와 방식은 운영 시작 전에 다시 논의.

## 게시 검토 운영법 (가장 중요 — 절대규칙 4)

1. 대시보드 홈 또는 "게시검토" 탭에서 `pending_review`(냉각중) 항목은 그냥 기다린다. 급하게 게시할 필요가 없으면 손대지 않는다.
2. 냉각기간이 지나 `ready_to_publish`(게시가능, 빨간 배지)로 바뀌면, **영상/썸네일/제목·설명을 직접 한 번 더 확인**한다.
   - 대본 오류, 부적절한 이미지, 잘못된 상품 매칭이 없는지 육안 확인.
   - `고지문구 ✅` / `딥링크 ✅` 표시를 확인한다(미디어제작 탭에서도 동일하게 표시됨).
3. 문제가 있으면 **[취소]** — 언제든 가능하고 되돌릴 수 있다.
4. 문제가 없으면 **[업로드]** → 확인 다이얼로그에서 한 번 더 확인 → 이 순간에만 실제 유튜브 업로드가 발생한다.
5. **업로드는 항상 비공개(private)로 이루어진다(2026-08-17~).** 이 앱은 검토를 마친 영상을 유튜브에 올리는 것까지만 책임지고, 실제로 언제 공개할지는 사람이 [유튜브 스튜디오에서 공개 설정] 링크로 들어가 직접 예약/공개해야 한다 — 이 앱을 상시 서버에 띄워두지 않고 작업할 때만 로컬에서 켜는 운영 방식으로 바꾸면서, 공개 타이밍 관리를 유튜브 스튜디오 쪽으로 넘겼다.
6. 게시 실패 시(`failed`) — `error_message`를 확인하고, YouTube 인증/쿼터 문제인지 확인 후 재시도(다시 큐에 넣거나 승인 단계부터 반복).

**타이머만으로 업로드되는 경로는 없다.** upload-worker는 상태만 바꾸고, 실제 업로드는 사람이 [업로드]를 눌러야만 실행된다(`app/upload/publisher.py`는 오직 `/publish` 엔드포인트에서만 호출됨). 업로드 이후 실제 공개로 전환하는 것도 이 앱이 아니라 사람이 유튜브 스튜디오에서 별도로 진행한다.

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
