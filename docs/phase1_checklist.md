# Phase 1 Checklist

- [ ] 1. `.env.example` 필요 변수 존재, README대로 기동됨
- [ ] 2. migration이 interfaces.md products/reviews 스키마와 일치
- [ ] 3. `POST /api/products/discover`에 실제 URL 입력 시 상품정보+딥링크+7개 점수 항목이 채워지고 `total_score`가 정확히 합산된다 (수동 재계산으로 대조)
- [ ] 4. `total_score`가 100을 초과하지 않는다 (스코어링 단위 테스트 통과)
- [ ] 5. `GET /api/products?min_score=80`이 기준 미달 상품을 제외하고 반환한다 (하루 3편 목표라 임계값을 70→80으로 상향)
- [ ] 6. `POST /api/products/{id}/reviews`로 리뷰 입력 시 status가 `reviews_collected`로 전환되고 story_score가 재계산된다
- [ ] 6b. `category`/`product_name`에 `EDUCATION_TRIGGER_KEYWORDS`(예: "자외선")가 포함된 상품을 discover하면 `needs_education=true`가 자동 설정되고, `PATCH /api/products/{id}/needs-education`으로 수동 변경도 가능하다
- [ ] 7. 잘못된 인증키에 명확한 에러 응답 (스택트레이스 노출 없음)
- [ ] 8. 코드베이스에 쿠팡 페이지 크롤링(Selenium/requests로 HTML 파싱) 코드가 없다
- [ ] 9. API 키 하드코딩 없음 (git grep)

## 수동 소싱 경로 (v2.2, 파트너스 API 키 미발급 기간 임시 경로)
- [ ] 10. `POST /api/products/manual`이 쿠팡 API를 호출하지 않고 사람이 입력한 값(product_name/price/category/image_urls/review_count)만으로 상품을 등록하고 점수를 계산한다 (`discover`와 동일한 status/점수 체계)
- [ ] 11. `PATCH /api/products/{id}/deeplink`로 딥링크를 등록/수정할 수 있다
- [ ] 12. `product_name` 없이 `POST /api/products/manual` 호출 시 명확한 422 에러 (pydantic 검증, `discover`의 기존 패턴과 동일)

전 항목 통과 → 통과, plan.md 기록. 실패 시 항목별 사유+재현방법 기록.
(9번까지는 실제 파트너스 키가 있어야 완전히 재현 가능 — 키 미발급 기간에는 10~12번만으로 이 임시 경로의 판정을 별도 진행할 수 있다.)
