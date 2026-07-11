# 02. 오케스트레이터 가이드 (v2)

오케스트레이터는 상주 agent가 아니라 절차 + 프롬프트 템플릿이다. 구조는 v1과 동일하며 phase 구성만 바뀌었다.

## 책임

1. 게이트 관리: 검증 통과 없이 다음 phase 착수 금지
2. 문서 규율: `01_plan.md`, `03_interfaces.md`를 실제와 일치하게 유지
3. 검증 agent는 반드시 새 세션, checklist + 산출물 요약만으로 시작
4. 반려 2회 초과 시 재작업 중단

## Phase 운영 사이클

```
[착수] 템플릿 A → 작업 agent
   ↓ 완료 (plan.md에 산출물 요약)
[검증] 새 세션, 템플릿 B → 검증 agent
   ↓
통과 → 템플릿 D(문서 갱신) → 다음 phase
반려 → 템플릿 C(반려 재작업), 2회 초과 시 사용자 개입
```

## 템플릿 A — 작업 agent 착수

```
너는 이 프로젝트의 Phase {N} 작업 agent다.
1. AGENTS.md (절대 규칙 5개, 특히 4번 업로드 홀드 규칙)
2. docs/03_interfaces.md
3. docs/phase{N}_spec.md
를 순서대로 읽고, spec 범위만 구현하라.
완료 시 docs/01_plan.md의 "Phase {N} 산출물 요약"에 파일 목록·실행 방법·환경변수를 기록하고
이력 로그에 완료 이벤트를 추가하라. 자기 판정은 하지 않는다.
```

## 템플릿 B — 검증 agent 착수 (새 세션)

```
너는 이 프로젝트의 Phase {N} 검증 agent다. 작업 과정 정보 없이 시작한다.
1. AGENTS.md (절대 규칙 위반 발견 시 즉시 반려)
2. docs/phase{N}_checklist.md
3. docs/01_plan.md의 "Phase {N} 산출물 요약"
을 읽고 전 항목을 실제 실행으로 판정하라. 코드 수정 금지.
결과를 docs/01_plan.md 이력 로그에 기록하라 (통과 또는 항목별 반려 사유+재현방법).
```

## 템플릿 C — 반려 재작업

```
너는 Phase {N} 작업 agent다. 반려됐다.
AGENTS.md, docs/phase{N}_spec.md를 읽고, docs/01_plan.md 최신 반려 사유를 확인해
반려된 항목만 수정하라. 완료 시 plan.md에 수정 내역을 기록하라.
```

## 템플릿 D — Phase 전환

```
너는 오케스트레이터다. 코드를 작성하지 않는다. Phase {N} 검증이 통과됐다.
1. docs/03_interfaces.md를 실제 구현과 대조해 갱신
2. docs/01_plan.md에서 Phase {N}을 '완료'로, 다음 phase를 '작업중'으로 변경
3. docs/phase{N+1}_spec.md의 연결점(사용할 테이블/함수/엔드포인트)이 구체적인지 확인, 모호하면 보강
4. plan.md 이력에 수행 내역 기록
```

## 검증 격리 체크

- [ ] 새 세션인가
- [ ] checklist만 주고 spec 전문은 주지 않았는가
- [ ] Phase 2는 형식 통과 후 사용자가 직접 샘플 5개 대본 품질 심사
