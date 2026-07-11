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

전 항목 통과 → 통과, plan.md 기록. 실패 시 항목별 사유+재현방법 기록.
