# Phase 2 Spec — 후기분석 & 대본작성 ([3][4][5])

## 목표

리뷰 원문을 감정/불만/칭찬으로 분석하고(2호 직원), 그 분석을 재료로 구조(고정)+톤(가변) 이중 프롬프트로 대본을 생성한다(3호 직원). 이 프로젝트의 품질 핵심.

## 범위

**포함**
1. `app/review/analyzer.py` — reviews_raw → 후기 분석 JSON (interfaces.md 스키마). positives/complaints/surprises/repurchase_reasons/emotional_keywords/target_segments/suggested_hook_angle 전부 채움. 원문 문장을 그대로 옮기지 않고 요약·범주화한다.
2. `app/script/prompts.py` — 구조 5단계(공감→감정→문제제기→해결→상품) 고정 템플릿 + 톤 7종(불편해결/우월감/보상/생활팁/사실형/생활형/실리적)별 지시문. suggested_hook_angle과 emotional_keywords를 "공감" 단계 문장에 직접 반영하도록 프롬프트에 명시. CTA·고지문구는 별도 단계를 만들지 않고 "상품" 단계 마지막 문장에 포함하도록 지시. **`needs_education=true`인 상품은 problem 단계 뒤에 삽입할 `educational_note`를 함께 생성하도록 지시하며, 프롬프트에 다음을 명시적으로 포함한다: 널리 합의된 상식 수준 사실만 사용, 의학적 조언·진단처럼 들리는 표현 금지, 확정적 인과 대신 절제된 어투("~일 수 있어요") 사용.**
3. `app/script/generator.py` — analysis_json + product 정보 + tone 파라미터 + needs_education 플래그 → script_json
4. `app/script/validator.py` — 스키마 검증(structure 5필드: empathy/emotion/problem/solution/product 전부 필수), 원문 유출 검사(analyzer 이전의 reviews_raw와 8단어 이상 연속 일치 금지), disclosure 상수 일치, **needs_education=true인데 educational_note.included=false이거나 text가 비어있으면 반려**, **educational_note.text에 진단·치료·효능 보장을 암시하는 금지어(별도 목록: "치료됩니다","완치","100% 예방" 등) 포함 시 반려**
5. 엔드포인트: `POST /api/products/{id}/analyze-reviews`, `POST /api/products/{id}/generate-script`, `PATCH /api/scripts/{id}`
6. 품질 테스트: 상품 3개 × 톤 2종 이상 조합으로 대본 생성, `docs/phase2_samples/`에 저장. **최소 1개는 `needs_education=true` 상품(예: 자외선차단 제품)으로 테스트해 educational_note 삽입을 검증.**

**제외**: 이미지/음성/영상, UI

## Steps

1. analyzer 프롬프트 v1 + 리뷰 샘플로 스탠드얼론 테스트
2. 대본 프롬프트(구조+톤) v1 + validator
3. 엔드포인트 연결, status 전이 확인
4. 상품×톤 조합 샘플 생성, 사용자 심사용 저장

## 산출물

`app/review/`, `app/script/`, 엔드포인트 3개, `docs/phase2_samples/`, plan.md 요약

## 다음 phase에 넘기는 것

`scripts.script_json` (검증 보장됨) — Phase 3 미디어 생성의 입력
