# Phase 3 Spec — 미디어 파이프라인 ([6][7][8])

## 목표

승인된 대본을 입력으로 이미지 가공 → TTS → FFmpeg 조립을 거쳐 완성 mp4를 생성한다. 이미지 방식은 **C안(실사 상품 + 2D 그래픽 배경/카드)**으로 확정 — AI 생성 실사 인물·장면은 사용하지 않는다. Kling 등 AI 클립 생성도 Phase 5로 미룬다.

## 이미지 방식: C안 상세

- **상품**: `products.image_urls`(파트너스 API 실사진) 그대로 사용. AI로 재생성하지 않는다.
- **배경/장식**: 2D 그래픽만 사용 — 단색·그라디언트 배경, 아이콘, 강조 카드, 자막 배경 박스. 사진처럼 보이는 배경(AI 생성 사실적 배경 포함)은 쓰지 않는다.
- **사람 등장 없음**: 실사든 AI 생성이든 인물(가상 인물 포함)은 영상에 넣지 않는다 — 초상권·아동 등장·소비자 오인 리스크를 원천 차단하기 위함(상세 사유는 overview.md 참조).
- **educational_note 장면**: 사실 설명 씬도 2D 그래픽(아이콘, 다이어그램 스타일)으로 표현하고 실사 이미지를 만들지 않는다.

## 범위

**포함**
1. `app/media/images.py` — products.image_urls 다운로드 → 1080×1920 캔버스 배치(블러 확대 배경 채움), 자막 안전영역 확보
2. `app/media/graphics.py` — **C안의 2D 그래픽 레이어**: 배경 그라디언트, 아이콘(카테고리별 프리셋), 강조 카드, educational_note용 간단 다이어그램 템플릿. 벡터/도형 기반으로 생성(AI 이미지 생성 API 사용 안 함)
3. `app/media/tts.py` — ElevenLabs, scene별 mp3 + 실제 길이 측정 (렌더링 타이밍 기준은 duration_sec이 아니라 TTS 실측)
4. `app/media/render.py` — FFmpeg 조립: 실사 상품 이미지 + 2D 그래픽 레이어 합성 + Ken Burns 줌 + TTS + 자막 번인(한글 폰트 임베드) + **BGM(`assets/bgm/` 풀에서 무작위 선택, -18dB 덕킹)** + 마지막 scene 고지 오버레이. 출력 h264/1080×1920/30fps
5. `app/media/worker.py` — render_jobs 폴링 워커 (queued→generating_images→generating_audio→assembling→done/failed)
6. 엔드포인트: `POST /api/scripts/{id}/approve`(enqueue), `GET /api/render-jobs/{id}`

**제외**: 썸네일(Phase 4), 업로드(Phase 4), AI 생성 실사 이미지/인물(로드맵에서 완전 제외), Kling 등 AI 영상클립(Phase 5)

## Steps

1. 이미지 캔버스 가공(실사 상품)
2. 2D 그래픽 레이어(graphics.py) — 배경/아이콘/카드/다이어그램 템플릿
3. TTS + 실측 길이
4. FFmpeg 조립 스크립트(실사+2D 합성), 고정 샘플로 반복 렌더 테스트
5. 워커 + approve 연결, E2E

## BGM 에셋 준비 (API 연동 아님)

`assets/bgm/`에 인스트루멘털 트랙 10~20개를 미리 채워둔다. **Suno API를 코드에서 호출하지 않는다** — Suno 공식 API가 없고 시중 제공자는 전부 비공식 래퍼라 자동화 파이프라인에 실시간으로 물리지 않는다. 대신 Suno Pro 웹앱에서 월 1회 정도 수동으로 인스트루멘털 곡을 생성·다운로드해 이 디렉토리(또는 Storage `bgm/` 버킷)를 채운다. `render.py`는 이 로컬/Storage 풀에서 무작위로 선택할 뿐, 외부 음악 생성 API를 호출하지 않는다.

## 산출물

`app/media/{images,graphics,tts,render,worker}.py`, BGM/폰트/아이콘 에셋, 렌더 샘플 mp4, plan.md 요약

## 다음 phase에 넘기는 것

`render_jobs.output_path`의 완성 mp4 — Phase 4 썸네일/업로드 입력
