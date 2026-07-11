# AGENTS.md — 프로젝트 공통 규칙 (v2)

> 이 프로젝트에서 작업하는 모든 AI agent(작업/검증/오케스트레이터)는 작업 시작 전 이 문서를 반드시 읽는다.
> v1 대비 변경: "완전 무인, 검수만 사람이" 방향으로 전환. 유튜브 자동 업로드는 금지가 아니라 홀드 안전장치로 관리한다.

## 프로젝트 개요

쿠팡 파트너스 상품 홍보 쇼츠를 **AI 직원 파이프라인**으로 대량 생산하고, 사람은 검수만 한다.
10단계: 상품발굴 → 후기수집 → AI후기분석 → 타겟선정 → 대본작성 → 이미지생성 → 음성생성 → 쇼츠제작 → 썸네일제작 → 업로드준비.
배경과 결정 사유는 `docs/00_project_overview.md` 참조.

## 기술 스택

| 영역 | 기술 |
|---|---|
| 백엔드 | Python 3.11+, FastAPI |
| DB / 스토리지 | Supabase (Postgres + Storage) |
| 배포/스케줄 | Railway, cron-job.org (또는 Railway cron) |
| 외부 API | 쿠팡 파트너스 API(HMAC), Anthropic Claude API, ElevenLabs TTS |
| 이미지/영상 | FFmpeg(1차: 정지이미지+Ken Burns), Suno(선택, BGM), Kling/Creatify(Phase 5 확장) |

## 절대 규칙 (위반 시 즉시 반려)

1. **쿠팡 페이지 크롤링(Selenium 등) 코드 작성 금지.** 리뷰 원문 수집은 사람이 수동 복사해 입력한다. 파트너스 계정 정지 리스크가 자동화 이득보다 크다. (챗GPT 대화에서 제안된 Selenium 옵션은 채택하지 않음 — 이유는 overview 참조)
2. **대본에 리뷰 원문 인용 금지.** 리뷰는 AI 분석(3호 직원)을 거쳐 감정/불만/칭찬으로 재구성된 뒤에만 대본 재료로 쓴다. 대본 narration이 리뷰 원문과 8단어 이상 연속 일치 금지.
3. **파트너스 고지문구 하드코딩.** 상수 `PARTNERS_DISCLOSURE`: `"이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."` — 모든 대본/유튜브 설명문에 포함.
4. **최종 게시는 반드시 사람이 명시적으로 클릭해야 실행된다.** 발굴부터 썸네일 생성까지는 전부 무인이지만, 실제 유튜브 업로드 API 호출은 `POST /api/upload-queue/{id}/publish`를 사람이 눌러야만 발생한다. 렌더링 완료 직후 즉시 클릭 가능하게 두지 않고 최소 냉각기간(`DEFAULT_HOLD_MINUTES`, 기본 240분)을 두어 `pending_review`→`ready_to_publish`로 상태만 전환한다(이 전환은 외부 API 호출이 아닌 내부 상태 변경이라 안전). 타이머 경과만으로 실제 업로드가 발생하는 코드 경로는 절대 작성하지 않는다. (하루 3편 목표에서는 자동 발행으로 얻는 이득보다 오발행 리스크가 크다는 판단.)
5. **API 키·시크릿 하드코딩 금지.** 전부 환경변수.

## 코딩 컨벤션

- 타입힌트 필수, pydantic v2
- DB 접근은 `supabase-py`, 테이블/컬럼/상태값은 `docs/03_interfaces.md` 기준 (변경 시 interfaces.md 먼저 수정)
- 외부 API 호출은 재시도 1회 + 명확한 예외 메시지
- 로그·주석은 한국어 허용

## Agent 역할 규칙

- **작업 agent**: 배정된 `phaseN_spec.md` 범위만 구현. 완료 시 `docs/01_plan.md`에 산출물 요약 기록. 자기 산출물 판정 금지.
- **검증 agent**: `phaseN_checklist.md`만 근거로 실제 실행·테스트. 코드 수정 금지. 반려 시 plan.md에 사유 기록.
- **오케스트레이터**: `docs/02_orchestrator_guide.md`의 절차·템플릿을 따른다. 코드 작성 안 함.

## 문서 맵

| 문서 | 용도 |
|---|---|
| `docs/00_project_overview.md` | 배경, 10단계 파이프라인, 결정사항, 리스크 |
| `docs/01_plan.md` | phase 상태판 + 이력 로그 |
| `docs/02_orchestrator_guide.md` | 오케스트레이터 절차 + 프롬프트 템플릿 |
| `docs/03_interfaces.md` | DB 스키마, API 계약, 대본/분석 JSON 스키마 |
| `docs/04_ui_spec.md` | 대시보드 화면별 UI 스펙 (Phase 4 작업 agent 필독) |
| `docs/phaseN_spec.md` / `phaseN_checklist.md` | phase별 작업/검증 문서 |
