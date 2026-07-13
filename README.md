# couparvi — Phase 1 + Phase 2

쿠팡 파트너스 쇼츠 자동 제작 파이프라인. 현재 구현 범위는 **Phase 1(상품발굴 & 후기수집)**과
**Phase 2(AI 후기분석 & 대본작성)**다. 전체 배경은 `docs/00_project_overview.md`, 규칙은 `AGENTS.md` 참조.

## 요구 사항

- Python 3.11+
- Supabase 프로젝트 (Postgres)
- 쿠팡 파트너스 API 액세스키/시크릿키
- Anthropic API 키 (Phase 2 — 후기 분석/대본 생성)

## 설치

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash
# .venv\Scripts\Activate.ps1    # PowerShell

pip install -r requirements.txt
cp .env.example .env
# .env에 COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY / SUPABASE_URL / SUPABASE_SERVICE_KEY 채우기
```

## 마이그레이션 적용

`migrations/001_init.sql`, `migrations/002_phase2.sql`을 순서대로 Supabase SQL Editor에
붙여넣어 실행하거나, `psql`로 적용한다.

```bash
psql "$SUPABASE_DB_URL" -f migrations/001_init.sql
psql "$SUPABASE_DB_URL" -f migrations/002_phase2.sql
```

## 실행

```bash
uvicorn app.main:app --reload
```

- 헬스체크: `GET http://localhost:8000/health`
- API 문서: `http://localhost:8000/docs`

## 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/products/discover` | body: `{coupang_url}` 또는 `{keyword}`. 상품정보+점수 계산 → `scored` |
| POST | `/api/products/manual` | (v2.2, 파트너스 키 미발급 시 임시 경로) body: `{product_name, price?, category?, image_urls?, coupang_url?, review_count?}`. API 호출 없이 등록 → `scored`, `deeplink`는 비움 |
| PATCH | `/api/products/{id}/deeplink` | (v2.2) body: `{deeplink}`. 파트너스 웹사이트에서 수동 생성한 딥링크 등록 |
| GET | `/api/products?min_score=80` | 추천 후보 목록 (기본 80점 이상) |
| POST | `/api/products/{id}/reviews` | 리뷰 원문+별점 저장 → `reviews_collected`, story_score 재계산 |
| PATCH | `/api/products/{id}/needs-education` | `needs_education` 수동 토글 |
| POST | `/api/products/{id}/analyze-reviews` | 최신 리뷰를 Claude로 분석 → `review_analysis` 저장, status `analyzed` |
| POST | `/api/products/{id}/generate-script` | body: `{tone, target_persona?}`. 구조+톤 이중 프롬프트로 대본 생성·검증 → `scripts` 저장, status `script_generated` |
| PATCH | `/api/scripts/{id}` | `script_json` 수동 수정, `version` +1 |

`keyword`로 발굴하면 파트너스 검색 API에서 상품명·가격·이미지·카테고리·리뷰수까지 채워진다.
`coupang_url`로 발굴하면 딥링크만 생성되고 나머지 필드는 비어 있다 — 크롤링 없이는 상세정보를
가져올 수 없기 때문(AGENTS.md 절대 규칙 1). 이 경우 상품명 등은 사람이 보완 입력한다(Phase 1 이후 확장).

**쿠팡 파트너스 API 키가 아직 없다면** `/api/products/manual`로 상품을 직접 등록하고(리뷰는 어느
오픈마켓에서 복사해도 무방 — 원래도 리뷰는 사람이 수동 입력하고 AI가 재구성만 함), 딥링크는
partners.coupang.com에서 수동 생성해 `PATCH /api/products/{id}/deeplink`로 등록하면 Phase 2 이후
파이프라인을 동일하게 쓸 수 있다. 상세 배경은 `docs/00_project_overview.md`의 "파트너스 API 키
미발급 기간의 임시 소싱 방식" 참조.

`tone`은 `불편해결/우월감/보상/생활팁/사실형/생활형/실리적` 7종 중 하나. 생성된 대본은
`app/script/validator.py`가 구조(5필드)·톤·disclosure·scenes 개수/길이·리뷰 원문 유출(8단어 이상
연속 일치)·`educational_note` 규칙을 모두 통과해야 저장된다. 검증 실패 시 422와 함께 사유 목록을 반환한다.

## 테스트

```bash
pytest tests/ -v
```

- `tests/test_scoring.py`: 스코어링 배점(overview.md 표)이 항목별 상한을 넘지 않고 합계가 100을 초과하지 않는지 검증
- `tests/test_education.py`: `EDUCATION_TRIGGER_KEYWORDS` 매칭 검증
- `tests/test_script_validator.py`: 대본 스키마/원문유출/educational_note 규칙 검증 (API 키 불필요)
- `tests/test_review_script_generation.py`: analyzer/generator의 JSON 파싱·재시도 로직을 가짜(fake) Anthropic 클라이언트로 검증 (API 키 불필요)

## 제외 범위 (Phase 1~2가 아님)

미디어 파이프라인(이미지/음성/영상), 대시보드 UI, 업로드, 쿠팡 페이지 크롤링(절대 금지) —
`docs/phase1_spec.md`, `docs/phase2_spec.md` 참조.
