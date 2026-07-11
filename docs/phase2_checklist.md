# Phase 2 Checklist

## 기능
- [ ] 1. `POST /api/products/{id}/analyze-reviews` 호출 시 analysis_json이 7개 필드 모두 채워져 생성되고 status가 `analyzed`로 전환된다
- [ ] 2. `POST /api/products/{id}/generate-script`에 tone 파라미터를 넣으면 해당 톤이 반영된 scripts 레코드가 생성되고 status가 `script_generated`로 전환된다
- [ ] 3. `PATCH /api/scripts/{id}` 수정 시 version+1

## 규칙 준수 (samples 전부)
- [ ] 4. analysis_json이 reviews_raw 문장을 그대로 복사하지 않았다 (요약·재구성 형태인지 육안 확인)
- [ ] 5. 모든 대본 narration이 reviews_raw와 8단어 이상 연속 일치 0건 (자동 검사)
- [ ] 6. `structure`의 5개 필드(empathy, emotion, problem, solution, product)가 모두 비어있지 않고, product 필드에 CTA·가격 언급이 포함되어 있다
- [ ] 7. `tone`이 정의된 7종 중 하나이고, 서로 다른 톤으로 생성한 같은 상품 대본 2개가 실제로 다른 접근을 취한다 (육안 비교)
- [ ] 8. disclosure 상수 일치, youtube.description에 딥링크+고지 포함
- [ ] 9. scenes 3~8개, 30~60초

## 사실설명(educational_note) — needs_education=true 상품에 한함
- [ ] 9b. `needs_education=true` 상품의 대본에 `educational_note.included=true`와 비어있지 않은 text가 있다
- [ ] 9c. `needs_education=false` 상품의 대본은 `educational_note.included=false`이다
- [ ] 9d. educational_note.text가 진단·치료·효능 보장을 암시하는 금지어를 포함하지 않는다 (자동 검사 + 육안 확인)
- [ ] 9e. educational_note.text가 확정적 인과 표현 대신 절제된 어투를 쓰고 있다 (육안 확인, 예: "~일 수 있어요" 계열)

## 견고성
- [ ] 10. analyzer/generator 모두 JSON 파싱 실패 시 1회 재시도 후 명확한 에러
- [ ] 11. validator 단위 테스트(pytest) 통과

## 판정
전 항목 통과 → "형식 검증 통과"로 기록, **사용자 품질 심사 대기**.
사용자가 samples 중 4/5 이상을 "바로 쓸 수 있는 수준"으로 승인해야 Phase 2 최종 완료.
훅 문장이 emotional_keywords/suggested_hook_angle을 반영했는지가 품질 심사의 핵심 기준.
