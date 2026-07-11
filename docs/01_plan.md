# 01. Plan — Phase 상태판 (v2)

## 현재 상태

| Phase | 이름 | 포함 단계 | 상태 | 반려 횟수 |
|---|---|---|---|---|
| 1 | 상품발굴 & 후기수집 | [1][2] | 검증중 | 0 |
| 2 | 후기분석 & 대본작성 | [3][4][5] | 대기 | 0 |
| 3 | 미디어 파이프라인 | [6][7][8] | 대기 | 0 |
| 4 | 썸네일 & 업로드(홀드) & 배포 | [9][10] | 대기 | 0 |
| 5 | 확장 (보류) | - | 보류 | - |

상태값: `대기` → `작업중` → `검증중` → `완료` (반려 시 `작업중` 복귀)

## 의존 관계

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → (Phase 5)
```
(v1과 달리 Phase 2가 Phase 1의 스코어링·수집 결과에 강하게 의존하므로 병행 권장하지 않음)

## 게이트 규칙

1. 검증 전 항목 통과 + interfaces.md와 구현 일치 + plan.md 산출물 요약 기록 완료 시 `완료`.
2. 반려 2회 초과 시 재작업 중단, 사용자가 spec 재검토.
3. Phase 2의 "대본 품질"은 형식 검증 통과 후 사용자 직접 심사(샘플 5개 중 4개 승인)가 최종 게이트.

## 이력 로그

| 날짜 | Phase | 이벤트 | 내용 |
|---|---|---|---|
| (기입) | - | v2 재설계 | ChatGPT 대화 반영, 10단계 파이프라인으로 전면 재구성. v1 문서 폐기. |
| 2026-07-11 | 1 | 작업 완료 | 아래 산출물 요약 참조. 검증 agent 착수 대기(새 세션, phase1_checklist.md 기준). |
| 2026-07-11 | 1 | 검증(주의: 새 세션 아님) | **격리 원칙 미준수 고지**: `docs/02_orchestrator_guide.md`가 요구하는 "새 세션 검증 agent"가 아니라 작업 agent와 동일 세션에서 진행함(사용자가 별도 검증 subagent 실행을 거부). 아래 결과는 참고용이며 진짜 격리 검증은 아님. **통과(코드/구조 검증)**: 1(`.env.example` 4개 필수변수 존재), 2(마이그레이션이 interfaces.md products/reviews 스키마와 컬럼 단위 일치), 4(`pytest tests/test_scoring.py` — 합계 100 초과 없음, 항목별 clamp 확인, 14/14 통과), 6b(`detect_needs_education` 유닛테스트로 키워드 매칭 확인, PATCH 엔드포인트 존재), 7(`CoupangPartnersError`로 명확한 에러 처리, 스택트레이스 미노출 구조 — 실키 없이 401 자체는 미재현), 8(`grep -rniE "selenium\|beautifulsoup\|playwright" app/` 매치 없음, 주석 1건뿐), 9(API 키 하드코딩 grep 매치 없음). **크리덴셜 없어 미검증(코드 구조상 요구사항 충족으로 보이나 미실행)**: 3(실제 상품 발굴 E2E), 5(`min_score=80` 필터링 실동작), 6(리뷰 입력 후 상태전환 실동작) — 쿠팡 파트너스 키·Supabase 프로젝트 없음. **실패 항목 없음.** 반려 횟수 변경 없음(0 유지). 상태는 `검증중` 유지 — 실크리덴셜로 3/5/6 재검증 및 진짜 새 세션 격리 검증 후 `완료` 전환 권장. |
| 2026-07-11 | 1 | 실 Supabase 연동 검증 | 사용자가 실제 Supabase 프로젝트(`dioakjzudbgijpbmhmah`) URL+secret key 제공, 마이그레이션은 사용자가 SQL Editor에서 직접 적용. `supabase-py`를 2.9.1→2.31.0으로 업그레이드(구버전이 새 `sb_secret_...` 키 포맷을 JWT로 오인해 `Invalid API key` 발생시킴 — requirements.txt 갱신). 이후 실제 DB로 **5번, 6번 통과 확인**: `GET /api/products?min_score=80`이 테스트 상품(total_score=85)을 포함하고 `min_score=90`에서는 정확히 제외함(실동작). `POST /api/products/{id}/reviews`에 감정 키워드 4개 포함 리뷰 입력 시 status가 `scored`→`reviews_collected`로 전환되고 story_score 0→7, total_score 85→92로 정확히 재계산됨(실동작, 재계산 공식 old_total-old_story+new_story 검증). `PATCH /.../needs-education`도 실DB에서 true→false 반영 확인. 테스트 데이터는 삭제해 원복(products/reviews 0행). **여전히 미검증**: 3번(쿠팡 파트너스 키가 없어 실제 상품 발굴 E2E는 불가 — `COUPANG_ACCESS_KEY`/`COUPANG_SECRET_KEY` 필요). 실패 항목 없음, 반려 횟수 0 유지. 상태는 `검증중` 유지(3번 + 진짜 새 세션 격리 검증 후 `완료` 전환). |

### 산출물 요약

#### Phase 1
- **파일**: `migrations/001_init.sql`(products/reviews 테이블), `app/coupang/partners.py`(HMAC 클라이언트, search_products/create_deeplinks), `app/discovery/scoring.py`(7개 항목 스코어링, 합계 100 clamp), `app/discovery/education.py`(EDUCATION_TRIGGER_KEYWORDS 매칭), `app/discovery/story_heuristic.py`(리뷰 입력 후 story_score 재계산용 임시 키워드 카운트 — 정식 AI 분석은 Phase 2), `app/api/products.py`(엔드포인트 4개), `app/main.py`, `app/config.py`, `app/db.py`, `.env.example`, `requirements.txt`, `README.md`, `tests/test_scoring.py`, `tests/test_education.py`
- **실행 방법**: README.md 참조 (`pip install -r requirements.txt` → `.env` 설정 → `migrations/001_init.sql` 적용 → `uvicorn app.main:app --reload`)
- **환경변수**: `COUPANG_ACCESS_KEY`, `COUPANG_SECRET_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (Phase 1 실사용), 나머지는 `.env.example`에 향후 phase용으로 선언만 해둠
- **셀프 체크(자기 판정 아님, 검증 agent 참고용)**: `pytest tests/ -v` 14개 전부 통과, `uvicorn` 기동 후 `/health` 200 및 4개 라우트 등록 확인, `grep -rniE "selenium|beautifulsoup|playwright" app/`에 코드 매치 없음(주석만), API 키 하드코딩 grep 결과 없음. **실제 쿠팡 파트너스 키/Supabase 프로젝트로 E2E(checklist 3, 6, 6b, 7번)는 미검증** — 크리덴셜이 필요해 이 세션에서 실행하지 못함.
- **알려진 제약**: `coupang_url`로 발굴 시 크롤링 없이는 상품명/가격/이미지를 얻을 수 없어 해당 필드는 빈 값으로 저장됨(코드 주석에 명시). `review_growth_score`/`content_fit_score`/`seasonality`는 파트너스 API가 제공하지 않는 데이터라 기본값 0으로 저장되고, 추후 사람이 보완 입력할 수 있는 구조로 열어둠(PATCH 확장은 Phase 1 범위 밖).

#### Phase 2
- (미착수)

#### Phase 3
- (미착수)

#### Phase 4
- (미착수)
