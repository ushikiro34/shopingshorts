# 03. Interfaces v2 — Phase 간 계약

## 1. DB 스키마

```sql
-- [1] 상품 발굴 + 스코어링
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

-- [2] 후기 수집 (수동 입력)
create table reviews (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references products(id) on delete cascade,
  reviews_raw text not null,            -- 수동 붙여넣은 원문 (분석 재료로만 사용, 절대 재배포 금지)
  rating_summary text,
  created_at timestamptz default now()
);

-- [3] AI 후기 분석
create table review_analysis (
  id uuid primary key default gen_random_uuid(),
  review_id uuid not null references reviews(id) on delete cascade,
  analysis_json jsonb not null,          -- 아래 "후기 분석 JSON 스키마"
  created_at timestamptz default now()
);

-- [4]+[5] 타겟 선정 + 대본 작성
create table scripts (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references products(id) on delete cascade,
  analysis_id uuid references review_analysis(id),
  target_persona text not null default '40-50대 여성',
  tone text not null,                    -- 불편해결|우월감|보상|생활팁|사실형|생활형|실리적
  version integer not null default 1,
  script_json jsonb not null,            -- 아래 "대본 JSON 스키마"
  approved boolean not null default false,
  created_at timestamptz default now()
);

-- [6][7][8] 미디어
create table render_jobs (
  id uuid primary key default gen_random_uuid(),
  script_id uuid not null references scripts(id) on delete cascade,
  status text not null default 'queued', -- queued|generating_images|generating_audio|assembling|done|failed
  output_path text,
  error_message text,
  created_at timestamptz default now(),
  finished_at timestamptz
);

-- [9] 썸네일
create table thumbnails (
  id uuid primary key default gen_random_uuid(),
  render_job_id uuid not null references render_jobs(id) on delete cascade,
  image_path text,
  status text not null default 'queued', -- queued|done|failed
  created_at timestamptz default now()
);

-- [10] 업로드 준비 (냉각기간 + 수동 게시)
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

-- 플랫폼 정책 모니터링 (Phase 4 부속 기능)
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
```

## 2. products.status 상태 머신

```
discovered → scored → reviews_collected → analyzed → script_generated →
script_approved → media_generated → thumbnail_generated → queued_for_upload → uploaded
(실패 시 각 단계 대응 failed_*, 재시도는 직전 단계로 롤백)
```

## 3. 후기 분석 JSON 스키마 (review_analysis.analysis_json)

Claude가 reviews_raw를 입력받아 생성. **원문을 그대로 옮기지 않고 카테고리화**한다.

```json
{
  "positives": ["부드러운 원단", "한 장씩 잘 뽑힘"],
  "complaints": ["엠보싱이 얇게 느껴질 수 있음"],
  "surprises": ["가성비 대비 만족도가 높다는 반응"],
  "repurchase_reasons": ["대용량이라 쟁여두기 좋음"],
  "emotional_keywords": ["안심", "든든함", "데일리"],
  "target_segments": ["아이 키우는 집", "생필품 재구매층"],
  "suggested_hook_angle": "믿고 쓰는 브랜드로 갈아탄 이유"
}
```

## 4. 대본 JSON 스키마 (scripts.script_json)

```json
{
  "structure": {
    "empathy": "공감 문장 (첫 3초, 타겟이 '어 이거 내 얘기네' 하는 지점)",
    "emotion": "공감을 감정으로 증폭시키는 문장 (답답함/불안/설렘 등 구체적 감정)",
    "problem": "그 감정의 원인이 되는 문제를 명확히 짚는 문장",
    "solution": "문제를 해결하는 방향성을 제시하는 문장 (아직 상품명 등장 전)",
    "product": "상품 등장 + 리뷰 근거 + CTA까지 포함하는 마무리 문장들 (가격은 언급하지 않는다)"
  },
  "educational_note": {
    "included": true,
    "text": "자외선A는 피부 노화를, 자외선B는 화상과 색소침착을 유발할 수 있어요. 흐린 날에도 자외선은 그대로 통과합니다."
  },
  "tone": "생활팁",
  "scenes": [
    {"seq": 1, "narration": "...", "caption": "...", "image_index": 0, "duration_sec": 5}
  ],
  "disclosure": "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.",
  "estimated_duration_sec": 45,
  "youtube": {
    "title": "...",
    "description": "... (마지막 줄은 반드시 disclosure와 정확히 동일한 문구)",
    "tags": ["..."]
  }
}
```

구조는 정확히 5단계: **공감 → 감정 → 문제제기 → 해결 → 상품**. CTA는 별도 단계가 아니라 `product` 단계의 마지막 문장에 자연스럽게 포함하되, **가격은 숫자로 언급하지 않고** "제품정보는 본문에 있어요, 확인해보세요" 처럼 "본문/더보기/설명란" 등 링크 확인을 유도하는 표현으로 마무리한다(v2.2, 가격 변동·최신가 확인 유도 목적). `solution`과 `product`를 분리한 이유는, 해결책을 먼저 방향성으로 제시하고 그다음 컷에서 "그게 바로 이 상품"으로 넘어가야 광고 티가 덜 나기 때문 — 둘을 합쳐서 한 문장에 몰아 써도 무방하나 필드 자체는 유지한다.

**고지문구(disclosure) 배치(v2.2)**: `PARTNERS_DISCLOSURE` 문구는 narration(음성으로 낭독되는 모든 텍스트: `structure.*`, `scenes[].narration`)에는 절대 포함하지 않는다. `youtube.description`의 맨 마지막 줄에만 정확히 그대로 넣는다. 영상 내 마지막 장면 시각적 오버레이(Phase 3, `disclosure` 필드 사용)는 이와 별개로 항상 표시되므로 음성으로 다시 읽을 필요가 없다.

**`educational_note` (선택적, 카테고리 기반)**: `products.needs_education=true`인 상품만 채운다. "문제제기" 단계를 보강하는 1~2문장짜리 간단한 사실 설명이며, 별도 구조 단계가 아니라 problem 씬 직후에 삽입되는 부가 정보다. 자외선차단·살균·정수필터·유산균 등 "왜 필요한지"에 대한 배경지식이 설득력을 좌우하는 카테고리에 쓴다. 규칙:
- 일반적으로 널리 합의된 상식 수준의 사실만 사용 (예: "자외선은 피부 노화·화상을 유발할 수 있다"는 O, 특정 질병 진단·치료 효과를 암시하는 표현은 X)
- 의학적 조언·진단처럼 들리는 표현 금지 ("~하면 안 걸립니다", "치료됩니다" 등)
- 과장·확정적 인과 표현 대신 "~일 수 있어요", "~로 알려져 있어요" 같은 절제된 어투 사용
- `needs_education=false`인 상품은 `included: false, text: ""`로 둔다

제약: `scenes` 3~8개, 30~60초, `narration`은 reviews_raw와 8단어 이상 연속 일치 금지, `structure`의 5개 필드 모두 필수(비어있지 않음), `tone`은 7종 중 하나.

## 5. API 엔드포인트

| Method | Path | 설명 | Phase |
|---|---|---|---|
| POST | `/api/products/discover` | body: `{coupang_url}` 또는 `{keyword}`. 쿠팡 파트너스 API로 상품정보+점수 계산 → `scored` | 1 |
| POST | `/api/products/manual` | (v2.2, 파트너스 API 키 미발급 시 임시 경로) body: `{product_name, price?, category?, image_urls?, coupang_url?, review_count?}`. API 호출 없이 사람이 직접 입력한 값으로 상품 등록+점수 계산 → `scored`. `deeplink`는 비워둔 채 생성되며 이후 `/deeplink`로 채운다 | 1 |
| PATCH | `/api/products/{id}/deeplink` | (v2.2) body: `{deeplink}`. 쿠팡 파트너스 웹사이트에서 사람이 수동 생성한 딥링크를 등록/수정 | 1 |
| GET | `/api/products?min_score=70` | 추천 후보 목록 | 1 |
| POST | `/api/products/{id}/reviews` | 리뷰 원문+별점 저장 → `reviews_collected` | 1 |
| POST | `/api/products/{id}/analyze-reviews` | Claude 분석 → `analyzed` | 2 |
| POST | `/api/products/{id}/generate-script` | body: `{tone, target_persona?}` → `script_generated` | 2 |
| PATCH | `/api/scripts/{id}` | 수동 수정, version+1 | 2 |
| POST | `/api/scripts/{id}/approve` | → `script_approved`, render_jobs enqueue | 3 |
| GET | `/api/render-jobs/{id}` | 렌더 상태 | 3 |
| POST | `/api/render-jobs/{id}/generate-thumbnail` | 썸네일 생성 | 4 |
| POST | `/api/render-jobs/{id}/queue-upload` | body: `{cooldown_minutes?}`(기본 240) → upload_queue 생성(`pending_review`), `queued_for_upload` | 4 |
| POST | `/api/upload-queue/{id}/cancel` | 언제든 취소 가능 → `canceled` | 4 |
| POST | `/api/upload-queue/{id}/publish` | **사람이 명시적으로 호출.** `ready_to_publish` 상태일 때만 허용, 이때 실제 유튜브 업로드 API가 호출된다 → `published` | 4 |
| GET | `/api/upload-queue?status=` | 검토/게시 대기 목록 (대시보드용) | 4 |
| POST | `/api/policy-check/run` | cron-job.org 등 외부 스케줄러가 주기 호출. 등록된 정책 페이지를 fetch해 해시 비교, 변경 시 policy_alerts 생성 | 4 |
| GET | `/api/policy-alerts?reviewed=false` | 미검토 정책 변경 알림 목록 (대시보드 배너용) | 4 |
| POST | `/api/policy-alerts/{id}/review` | body: `{note}` → reviewed=true 처리 | 4 |

내부 상태 워커: `pending_review` 항목 중 `ready_at` 경과분을 `ready_to_publish`로 전환하는 것만 수행 — **이 워커는 외부(유튜브) API를 호출하지 않는다.** 실제 유튜브 업로드는 오직 `/publish` 엔드포인트를 사람이 호출했을 때만 발생한다. Phase 4에서 구현.

## 6. 환경변수

| 변수 | 용도 |
|---|---|
| `COUPANG_ACCESS_KEY` / `COUPANG_SECRET_KEY` | 파트너스 API |
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` | DB/Storage |
| `ANTHROPIC_API_KEY` | 후기 분석, 대본 생성 |
| `TTS_PROVIDER` | (v2.2) `elevenlabs` \| `edge`. 기본값 `edge` — ElevenLabs 무료 플랜은 라이브러리 보이스를 API로 못 씀(2026-07-13 확인, `01_plan.md` 참조). edge-tts는 키 불필요 |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` | TTS (`TTS_PROVIDER=elevenlabs`일 때만 사용) |
| `EDGE_TTS_VOICE` | TTS (`TTS_PROVIDER=edge`일 때 보이스 이름, 기본값 `ko-KR-SunHiNeural`) |
| `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` / `YOUTUBE_REFRESH_TOKEN` | 업로드 (Phase 4) |
| `DEFAULT_HOLD_MINUTES` | 게시 전 냉각기간 기본값(분). 경과해야 `/publish` 버튼이 활성화됨 (기본 240) |
| `STORAGE_BUCKET` | 완성 영상/썸네일 버킷 |
| `POLICY_CHECK_SECRET` | `/api/policy-check/run` 호출 인증용(외부 스케줄러가 헤더로 전달, 무단 트리거 방지) |
| `SESSION_SECRET` | 로그인 세션 쿠키 서명용. 단일 운영자 계정은 Supabase Auth에서 수동 생성(회원가입 화면 없음) |

## 8. 사실설명(educational_note) 트리거 키워드

`app/config.py`의 `EDUCATION_TRIGGER_KEYWORDS` 상수. 상품 발굴 시 `category`+`product_name`에 아래 키워드가 포함되면 `needs_education=true`로 자동 설정한다(사람이 대시보드에서 재검토·수정 가능).

```python
EDUCATION_TRIGGER_KEYWORDS = [
    "자외선", "UV", "차단제", "선크림",
    "살균", "항균", "소독",
    "정수", "필터", "공기청정",
    "유산균", "프로바이오틱스",
    "탈취", "제습",
]
```

목록은 초기값이며 운영하면서 대시보드에서 상품별로 수동 토글한 이력을 모아 주기적으로 보강한다.

## 9. 정책 모니터링 대상 (policy_snapshots 초기 시드)

`app/config.py`의 `MONITORED_POLICIES` 상수 — 최초 배포 시 이 목록으로 policy_snapshots를 시드한다.

```python
MONITORED_POLICIES = [
    {"platform": "youtube", "policy_name": "커뮤니티 가이드라인", "url": "https://www.youtube.com/howyoutubeworks/policies/community-guidelines/"},
    {"platform": "youtube", "policy_name": "광고 콘텐츠 정책", "url": "https://support.google.com/youtube/answer/154235"},
    {"platform": "youtube", "policy_name": "변경되거나 합성된 콘텐츠 정책", "url": "https://support.google.com/youtube/answer/14328491"},
    {"platform": "instagram", "policy_name": "커뮤니티 가이드라인", "url": "https://help.instagram.com/477434105621119"},
    {"platform": "instagram", "policy_name": "브랜드 콘텐츠 정책", "url": "https://help.instagram.com/2028067040742191"},
]
```

정확한 URL은 Phase 4 착수 시 최신 링크로 재확인 후 반영한다(정책 페이지 경로는 종종 바뀐다). cron-job.org에서 주 1회 `POST /api/policy-check/run`을 호출하도록 설정한다. 해시 비교는 페이지 전체 텍스트 기준이라 쿠키 배너 등 무관한 변경도 오탐지될 수 있음을 감안하고, 알림은 "확인이 필요하다"는 신호로만 쓴다 — 실제 정책 위반 여부 판단은 사람이 한다.

## 10. 프로젝트 구조 (목표)

```
app/
├── main.py
├── config.py               # PARTNERS_DISCLOSURE, DEFAULT_HOLD_MINUTES 등
├── db.py
├── coupang/partners.py     # HMAC, 상품 검색, 딥링크
├── discovery/scoring.py    # 1호 직원: 스코어링 로직 (Phase 1)
├── review/analyzer.py      # 2호 직원: 후기 분석 (Phase 2)
├── script/generator.py     # 3호 직원: 구조+톤 대본 생성 (Phase 2)
├── script/validator.py     # 원문유출 검사, 스키마 검증 (Phase 2)
├── media/images.py         # 4호 직원: 실사 상품 이미지 가공 (Phase 3)
├── media/graphics.py       # 4호 직원: 2D 그래픽 배경/카드/아이콘 레이어 (Phase 3, C안)
├── media/tts.py            # 4호 직원: TTS (Phase 3)
├── media/render.py         # 5호 직원: FFmpeg 조립 (Phase 3)
├── media/thumbnail.py      # 5호 직원: 썸네일 (Phase 4)
├── upload/queue_worker.py  # 냉각기간 경과 시 상태만 전환 (외부 API 호출 없음, Phase 4)
├── upload/publisher.py     # /publish 호출 시에만 실제 유튜브 업로드 실행 (Phase 4)
├── monitoring/policy_checker.py  # 정책 페이지 해시 비교, 변경 감지 (Phase 4)
└── web/                    # 대시보드 (Phase 4)
```
