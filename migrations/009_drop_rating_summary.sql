-- Phase 9: 별점 요약(rating_summary) 필드 삭제
-- 상품선택 탭에서 UI를 걷어내면서 관련 로직(app/web/dashboard.py discover_analyze,
-- app/api/products.py ReviewInput/add_review)도 함께 정리했다 — 더 이상 어디서도
-- 읽거나 쓰지 않으므로 컬럼도 삭제한다.

alter table reviews
  drop column if exists rating_summary;
