-- Phase 5: 씬별 캡션/후킹/상시CTA 위치·스타일 편집 (렌더 이후, CapCut식 드래그 에디터)
-- docs/03_interfaces.md 1번 스키마(render_jobs) + 4-1번 "캡션 오버라이드 JSON 스키마"

alter table render_jobs
  add column base_video_path text,   -- 자막 없는 합성본(크로스페이드+BGM까지 끝난 상태). 캡션 편집 재합성의 원본
  add column scene_timeline jsonb,   -- base_video_path 기준 씬별 절대 구간: [{seq, start_sec, end_sec}]
  add column caption_overrides jsonb; -- 씬별 캡션/후킹/상시CTA 위치·스타일 편집값. null이면 기본값
