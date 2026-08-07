-- Phase 6: 후킹(첫 씬) 프롬프트 확인/재생성 단계
-- docs/03_interfaces.md 2번(scripts), 3번(render_jobs) 스키마 참고

alter table scripts
  add column hook_preview_image_path text,   -- 확인 단계에서 만든 씬0 스틸컷 경로
  add column hook_preview_video_path text,   -- 확인 단계에서 만든 씬0 후킹 영상 경로
  add column hook_preview_status text;       -- null | 'generating' | 'done' | 'failed'

alter table render_jobs
  add column kind text not null default 'full',  -- 'full' | 'hook_preview' | 'hook_patch'
  add column source_render_job_id uuid references render_jobs(id);
  -- hook_patch job 전용: 어느 완료된 render_job의 후킹만 다시 만들지 가리킨다
