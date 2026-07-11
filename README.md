# couparvi — Phase 1

쿠팡 파트너스 쇼츠 자동 제작 파이프라인. 현재 구현 범위는 **Phase 1(상품발굴 & 후기수집)**만이다.
전체 배경은 `docs/00_project_overview.md`, 규칙은 `AGENTS.md` 참조.

## 요구 사항

- Python 3.11+
- Supabase 프로젝트 (Postgres)
- 쿠팡 파트너스 API 액세스키/시크릿키

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

`migrations/001_init.sql`을 Supabase SQL Editor에 붙여넣어 실행하거나, `psql`로 적용한다.

```bash
psql "$SUPABASE_DB_URL" -f migrations/001_init.sql
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
| GET | `/api/products?min_score=80` | 추천 후보 목록 (기본 80점 이상) |
| POST | `/api/products/{id}/reviews` | 리뷰 원문+별점 저장 → `reviews_collected`, story_score 재계산 |
| PATCH | `/api/products/{id}/needs-education` | `needs_education` 수동 토글 |

`keyword`로 발굴하면 파트너스 검색 API에서 상품명·가격·이미지·카테고리·리뷰수까지 채워진다.
`coupang_url`로 발굴하면 딥링크만 생성되고 나머지 필드는 비어 있다 — 크롤링 없이는 상세정보를
가져올 수 없기 때문(AGENTS.md 절대 규칙 1). 이 경우 상품명 등은 사람이 보완 입력한다(Phase 1 이후 확장).

## 테스트

```bash
pytest tests/ -v
```

`tests/test_scoring.py`는 스코어링 배점(overview.md 표)이 항목별 상한을 넘지 않고 합계가 100을
초과하지 않는지 검증한다. `tests/test_education.py`는 `EDUCATION_TRIGGER_KEYWORDS` 매칭을 검증한다.

## 제외 범위 (Phase 1이 아님)

후기 분석(AI), 대본 생성, 미디어 파이프라인, 대시보드 UI, 쿠팡 페이지 크롤링(절대 금지) —
`docs/phase1_spec.md` 참조.
