-- Phase 2: AI 후기 분석 + 타겟 선정 + 대본 작성
-- docs/03_interfaces.md 1번 스키마 중 review_analysis, scripts 테이블

create table review_analysis (
  id uuid primary key default gen_random_uuid(),
  review_id uuid not null references reviews(id) on delete cascade,
  analysis_json jsonb not null,          -- docs/03_interfaces.md 3번 "후기 분석 JSON 스키마"
  created_at timestamptz default now()
);

create table scripts (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references products(id) on delete cascade,
  analysis_id uuid references review_analysis(id),
  target_persona text not null default '40-50대 여성',
  tone text not null,                    -- 불편해결|우월감|보상|생활팁|사실형|생활형|실리적
  version integer not null default 1,
  script_json jsonb not null,            -- docs/03_interfaces.md 4번 "대본 JSON 스키마"
  approved boolean not null default false,
  created_at timestamptz default now()
);

create index idx_review_analysis_review_id on review_analysis(review_id);
create index idx_scripts_product_id on scripts(product_id);
