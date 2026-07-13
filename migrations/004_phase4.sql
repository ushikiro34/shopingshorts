-- Phase 4: 썸네일 + 업로드준비(홀드) + 정책 모니터링
-- docs/03_interfaces.md 1번 스키마 중 thumbnails, upload_queue, policy_snapshots, policy_alerts

create table thumbnails (
  id uuid primary key default gen_random_uuid(),
  render_job_id uuid not null references render_jobs(id) on delete cascade,
  image_path text,
  status text not null default 'queued', -- queued|done|failed
  created_at timestamptz default now()
);

create table upload_queue (
  id uuid primary key default gen_random_uuid(),
  render_job_id uuid not null references render_jobs(id) on delete cascade,
  thumbnail_id uuid references thumbnails(id),
  youtube_title text,
  youtube_description text,
  ready_at timestamptz not null,         -- 냉각기간 종료 시각. 이 시각 이후에만 publish 가능(버튼 활성화)
  status text not null default 'pending_review', -- pending_review|ready_to_publish|published|canceled|failed
  youtube_video_id text,
  created_at timestamptz default now(),
  published_at timestamptz
);

create table policy_snapshots (
  id uuid primary key default gen_random_uuid(),
  platform text not null,               -- youtube|instagram
  policy_name text not null,            -- 예: '광고 콘텐츠 정책', 'AI 생성 콘텐츠 정책'
  url text not null,
  content_hash text not null,           -- 마지막으로 확인한 페이지 본문의 해시
  last_checked_at timestamptz default now(),
  last_changed_at timestamptz
);

create table policy_alerts (
  id uuid primary key default gen_random_uuid(),
  snapshot_id uuid not null references policy_snapshots(id) on delete cascade,
  detected_at timestamptz default now(),
  reviewed boolean not null default false,
  reviewed_at timestamptz,
  note text                             -- 사람이 검토 후 남기는 메모(예: "실제 영향 없음" / "대본 규칙 수정 필요")
);

create index idx_thumbnails_render_job_id on thumbnails(render_job_id);
create index idx_upload_queue_status on upload_queue(status);
create index idx_upload_queue_ready_at on upload_queue(ready_at);
create index idx_policy_alerts_reviewed on policy_alerts(reviewed);

-- docs/03_interfaces.md 9번 / app/config.py의 MONITORED_POLICIES와 동일한 초기 시드.
-- content_hash는 최초에는 비워두고, 첫 POST /api/policy-check/run 실행 시 채워진다.
insert into policy_snapshots (platform, policy_name, url, content_hash) values
  ('youtube', '커뮤니티 가이드라인', 'https://www.youtube.com/howyoutubeworks/policies/community-guidelines/', ''),
  ('youtube', '광고 콘텐츠 정책', 'https://support.google.com/youtube/answer/154235', ''),
  ('youtube', '변경되거나 합성된 콘텐츠 정책', 'https://support.google.com/youtube/answer/14328491', ''),
  ('instagram', '커뮤니티 가이드라인', 'https://help.instagram.com/477434105621119', ''),
  ('instagram', '브랜드 콘텐츠 정책', 'https://help.instagram.com/2028067040742191', '');
