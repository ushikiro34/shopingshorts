-- Phase 7: 씬별(후킹 외 다른 씬 포함) 프롬프트 확인/재생성
-- docs/03_interfaces.md 2번(scripts), 3번(render_jobs) 스키마 참고

alter table scripts
  add column scene_preview_images jsonb not null default '{}'::jsonb;
  -- {"<seq>": {"image_path": "...", "status": "generating"|"done"|"failed"}}
  -- 씬0(후킹)은 기존 hook_preview_image_path/video_path/hook_preview_status를 그대로 쓴다 —
  -- 후킹만 영상(video_path)까지 있고 나머지는 스틸컷만 있어 스키마가 달라 분리했다.

alter table render_jobs
  add column target_seq int;
  -- kind='hook_preview'|'hook_patch' job 전용: 어느 씬을 대상으로 하는지.
  -- null이면 후킹(대본의 첫 씬, scenes[0])을 뜻한다 — 기존에 이미 쌓인 행과 하위호환.
