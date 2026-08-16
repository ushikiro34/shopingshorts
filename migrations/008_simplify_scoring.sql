-- Phase 8: 상품 스코어링을 리뷰수/가격/스토리 3항목만 남기고 정리
-- 증가속도/충동구매/계절성/소재적합 4개 항목은 쿠팡 파트너스 API도, 대시보드 UI도
-- 실제 값을 채워 넣는 경로가 하나도 없어(항상 0점 고정) 죽은 배점이었다(사용자 피드백).
-- app/discovery/scoring.py 참고 — 총점 만점이 100 -> 40으로 줄었다.

alter table products
  drop column if exists review_growth_score,
  drop column if exists impulse_score,
  drop column if exists seasonality_score,
  drop column if exists content_fit_score;
