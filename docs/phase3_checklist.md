# Phase 3 Checklist

- [ ] 1. 승인된 대본 1개로 approve → 워커 처리 → render_jobs.status `done`, output_path mp4 실재
- [ ] 2. products.status 전이: `script_approved`→(중간 상태들)→`media_generated`
- [ ] 3. ffprobe: 해상도 1080×1920, h264, yuv420p, 30fps
- [ ] 4. 오디오 트랙 존재, 전체 길이가 scene TTS 실측 합 ±10%
- [ ] 5. 임의 구간 프레임 추출 시 자막이 정확히 렌더링, 한글 깨짐 없음
- [ ] 6. 마지막 2초 구간에 고지문구 표시
- [ ] 7. 이미지에 Ken Burns 줌 효과가 실제로 적용됨 (프레임 간 스케일 변화 확인)
- [ ] 7b. 임의 구간 프레임에서 배경/장식이 2D 그래픽(단색·그라디언트·아이콘·카드)이고, 사진처럼 보이는 AI 생성 배경이나 인물이 없다
- [ ] 8. 인위적 실패(이미지 404) 시 `failed`+error_message, products는 `script_approved`로 롤백 후 재시도 성공
- [ ] 9. 코드베이스에 Kling 등 외부 AI 영상클립 API 호출 코드와, AI 이미지 생성(실사/인물) API 호출 코드가 없다 (graphics.py는 도형·아이콘 기반이어야 함)
- [ ] 9b. 코드베이스에 Suno(또는 비공식 Suno API 래퍼) 호출 코드가 없다 — BGM은 `assets/bgm/` 사전 준비 풀에서만 선택한다

전 항목 통과 → 통과. "보기 좋음"(자막 타이밍, BGM 밸런스)은 사용자가 샘플 영상 직접 확인.
