-- Phase 1: 상품 발굴 + 후기 수집
-- docs/03_interfaces.md 1번 스키마 중 products, reviews 테이블

create extension if not exists pgcrypto;

create table products (
  id uuid primary key default gen_random_uuid(),
  coupang_url text,
  keyword text,                         -- URL 대신 키워드 검색으로 발굴한 경우
  product_name text,
  price integer,
  discount_rate integer,
  image_urls jsonb default '[]',
  deeplink text,
  category text,
  review_count integer,
  review_growth_score int check (review_growth_score between 0 and 20),
  price_score int check (price_score between 0 and 10),
  impulse_score int check (impulse_score between 0 and 15),
  seasonality_score int check (seasonality_score between 0 and 10),
  content_fit_score int check (content_fit_score between 0 and 15),  -- 쇼츠 소재 적합성
  story_score int check (story_score between 0 and 10),              -- 공감 스토리 가능성 (리뷰 입력 후 채워짐)
  total_score int,                       -- 위 6개 합 + review_count 20점 배점
  needs_education boolean not null default false,  -- 카테고리 키워드 매칭으로 자동 설정, 사람이 재검토/수정 가능
  status text not null default 'discovered',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table reviews (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references products(id) on delete cascade,
  reviews_raw text not null,            -- 수동 붙여넣은 원문 (분석 재료로만 사용, 절대 재배포 금지)
  rating_summary text,
  created_at timestamptz default now()
);

create index idx_products_status on products(status);
create index idx_products_total_score on products(total_score);
create index idx_reviews_product_id on reviews(product_id);
