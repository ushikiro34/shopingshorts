# Phase 4 Spec — 썸네일 & 업로드준비 & 배포 ([9][10])

## 목표

완성 영상에 썸네일을 자동 생성하고, 냉각기간을 거쳐 사람이 명시적으로 클릭해야만 실제 유튜브 게시가 일어나게 한다. 하루 3편 규모이므로 처리량보다 오발행 방지가 우선이다. 대시보드로 전 과정을 모바일에서 운영 가능하게 한다.

## 범위

**포함**
1. `app/media/thumbnail.py` — 대본의 `structure.empathy` 또는 `suggested_hook_angle` 텍스트 + 상품 이미지로 썸네일 1080×1920(또는 1280×720, 유튜브 쇼츠 커버 규격 확인) 자동 생성
2. `app/upload/queue_worker.py` — **외부 API를 호출하지 않는 내부 워커.** `upload_queue`를 폴링해 `ready_at` 경과 + `pending_review` 상태인 항목만 `ready_to_publish`로 전환한다.
3. `app/upload/publisher.py` — YouTube Data API 연동. `/publish` 엔드포인트가 호출됐을 때만 실행되며, 호출 전 status가 `ready_to_publish`인지 검증한다. 성공 시 `published`+`youtube_video_id` 기록.
4. `app/monitoring/policy_checker.py` — interfaces.md 9번의 `MONITORED_POLICIES`를 fetch해 본문 해시를 `policy_snapshots`와 비교. 변경 감지 시 `policy_alerts` 생성. 외부 스케줄러(cron-job.org, 주 1회)가 `POST /api/policy-check/run`을 호출하는 방식 — 이 프로젝트 자체에는 스케줄러를 두지 않는다(Railway 서비스는 상시 기동이 전제가 아니므로).
5. 엔드포인트: `POST /api/render-jobs/{id}/generate-thumbnail`, `POST /api/render-jobs/{id}/queue-upload`(cooldown_minutes 지정, 기본 240), `POST /api/upload-queue/{id}/cancel`, `POST /api/upload-queue/{id}/publish`, `GET /api/upload-queue?status=`, `POST /api/policy-check/run`, `GET /api/policy-alerts?reviewed=`, `POST /api/policy-alerts/{id}/review`
6. `app/web/auth.py` — Supabase Auth 이메일/비밀번호 로그인, httpOnly 세션 쿠키(`SESSION_SECRET`), 미로그인 시 전 라우트 리다이렉트. 회원가입 화면은 만들지 않는다(계정은 Supabase 대시보드에서 수동 생성).
7. 대시보드(`app/web/`, FastAPI+Jinja2) — **화면별 상세는 `docs/04_ui_spec.md` 필독, 여기 목록은 요약**
   - 로그인 화면, 대시보드 홈(요약 카드 4개 + 진행 현황)
   - 탭 4개(발굴/대본작성/미디어제작/게시검토), 소프트 게이팅 — 탭 이동 제약 없음, 큐가 비었을 때만 안내 배너
   - 탭 공통 3단 레이아웃(좌 목록/중앙 작업영역/우 액션패널), 데스크톱은 3열 동시, 모바일은 화면 전환식
   - **게시검토 탭**: `pending_review`는 남은 냉각시간 표시, `ready_to_publish`는 **[게시]** 버튼 + 확인 다이얼로그를 거쳐야만 업로드가 실행됨을 명확히 안내(경고 문구 필수). 이 화면이 절대규칙 4번의 실제 구현체.
   - **정책 알림 배너**: 미검토 policy_alerts가 있으면 전 화면 상단에 표시, 클릭 시 변경 페이지 링크와 [검토완료] 버튼
8. Railway 배포: Dockerfile(ffmpeg+한글폰트), 웹/렌더워커/업로드상태워커 프로세스 분리(업로드상태워커는 외부 API를 호출하지 않으므로 실패해도 리스크가 낮음)
9. `docs/runbook.md` — 정책 알림 발생 시 대응 절차 포함

**제외**: Phase 5(확장 옵션), AI 실사 이미지 생성(로드맵에서 완전 제외), 인스타그램 API 자동 게시(1차는 수동 다운로드-업로드), 다중 사용자/권한 관리(단일 운영자 전제)

## Steps

1. 썸네일 생성기 — 실사진(파트너스 API image_urls) 기반, AI 이미지 생성 사용 안 함
2. 게시 상태 워커(내부 전환만) + publisher(수동 트리거) + YouTube OAuth 설정 문서화
3. policy_checker + cron-job.org 연동 문서화
4. 로그인 + 대시보드 홈 + 탭 4개(3단 레이아웃) + 정책 알림 배너
5. Railway 배포, 프로덕션 E2E

## 산출물

`app/media/thumbnail.py`, `app/upload/{queue_worker,publisher}.py`, `app/web/{auth,...}.py`, `Dockerfile`, `docs/runbook.md`, plan.md 요약(배포 URL 포함)
