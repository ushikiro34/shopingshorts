# Phase 1 Spec — 상품발굴 & 후기수집 ([1][2])

## 목표

파트너스 API로 상품 후보를 조사해 자동 점수화하고(1호 직원), 사람이 선택한 상품에 리뷰를 입력하면 분석 대기 상태가 되는 뼈대를 만든다.

## 범위

**포함**
1. `migrations/001_init.sql` — interfaces.md 스키마(products, reviews 테이블 우선)
2. `app/coupang/partners.py` — HMAC 클라이언트, 상품 검색/딥링크 (v1 자산 있으면 재사용)
3. `app/discovery/scoring.py` — overview.md의 스코어링 표(리뷰개수20/증가속도20/가격10/충동구매15/계절성10/콘텐츠적합성15/스토리10) 구현. story_score는 리뷰 입력 전엔 0, 리뷰 입력 후 재계산.
4. `app/config.py`의 `EDUCATION_TRIGGER_KEYWORDS`(interfaces.md 8번 참조) 매칭 로직 — discover 시 category+product_name에 키워드가 있으면 `needs_education=true` 자동 설정
5. 엔드포인트: `POST /api/products/discover`, `GET /api/products?min_score=`(대시보드 기본값 80), `POST /api/products/{id}/reviews`, `PATCH /api/products/{id}/needs-education`(사람이 수동 토글)
6. `.env.example`, `requirements.txt`, `README.md`
7. (v2.2, 파트너스 API 키 미발급 기간 임시 경로 — overview.md "파트너스 API 키 미발급 기간의 임시 소싱 방식" 참조) `POST /api/products/manual`(API 호출 없이 수동 입력으로 상품 등록), `PATCH /api/products/{id}/deeplink`(수동 생성한 딥링크 등록)

**제외**: 후기 분석(AI), 대본, 미디어, 크롤링(절대 금지)

## Steps

1. 마이그레이션 적용
2. HMAC 클라이언트 + 상품 검색
3. 스코어링 로직 (단위 테스트: 배점 합 100 초과 불가, 각 항목 범위 검증)
4. 엔드포인트 3개, E2E: 실제 상품 1개 발굴 → 점수 확인 → 리뷰 입력 → status 전환

## 산출물

`app/coupang/`, `app/discovery/`, 엔드포인트, migrations, plan.md 산출물 요약

## 다음 phase에 넘기는 것

`reviews_collected` 상태의 product + reviews 레코드 (Phase 2 입력)
