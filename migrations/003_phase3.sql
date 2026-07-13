-- Phase 3: 미디어 파이프라인 (이미지/음성/영상)
-- docs/03_interfaces.md 1번 스키마 중 render_jobs 테이블

create table render_jobs (
  id uuid primary key default gen_random_uuid(),
  script_id uuid not null references scripts(id) on delete cascade,
  status text not null default 'queued', -- queued|generating_images|generating_audio|assembling|done|failed
  output_path text,
  error_message text,
  created_at timestamptz default now(),
  finished_at timestamptz
);

create index idx_render_jobs_script_id on render_jobs(script_id);
create index idx_render_jobs_status on render_jobs(status);
