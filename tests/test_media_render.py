import os

from app.media.render import (
    build_animated_caption_filter,
    build_hook_text_filter,
    build_scene_filter_complex,
    build_text_block_filter,
    build_xfade_filter_complex,
    build_zoompan_filter,
    escape_path_for_filter,
    estimate_word_timings,
    pick_bgm_track,
    resolve_font_path,
    wrap_text_lines,
)


def test_escape_path_for_filter_handles_windows_drive_colon():
    escaped = escape_path_for_filter("C:\\work\\couparvi\\caption.txt")
    assert escaped == "C\\:/work/couparvi/caption.txt"


def test_escape_path_for_filter_handles_single_quote():
    escaped = escape_path_for_filter("C:/it's/a/path.txt")
    assert "\\'" in escaped


def test_build_zoompan_filter_frame_count_matches_duration():
    filt = build_zoompan_filter(2.0, fps=30)
    assert "d=60" in filt
    assert "s=1080x1920" in filt
    assert "fps=30" in filt


def test_build_zoompan_filter_minimum_one_frame():
    filt = build_zoompan_filter(0.0, fps=30)
    assert "d=1" in filt


def test_build_text_block_filter_contains_textfile_and_font_per_line():
    filt = build_text_block_filter(["line0.txt", "line1.txt"], "font.ttf", bottom_margin=360, fontsize=54)
    assert "textfile='line0.txt'" in filt
    assert "textfile='line1.txt'" in filt
    assert "fontfile='font.ttf'" in filt
    assert "fontcolor=white" in filt
    assert filt.count("drawtext=") == 2


def test_build_text_block_filter_has_background_drawbox():
    filt = build_text_block_filter(["line0.txt"], "font.ttf", bottom_margin=360, fontsize=54)
    assert filt.startswith("drawbox=")


def test_build_text_block_filter_box_height_scales_with_line_count():
    filt_1_line = build_text_block_filter(["a.txt"], "font.ttf", bottom_margin=360, fontsize=54)
    filt_3_lines = build_text_block_filter(
        ["a.txt", "b.txt", "c.txt"], "font.ttf", bottom_margin=360, fontsize=54
    )
    # 줄 수가 늘면 drawbox의 h(높이)도 커져야 한다 (1줄: 70+48=118, 3줄: 210+48=258)
    assert "h=118" in filt_1_line
    assert "h=258" in filt_3_lines


def test_build_text_block_filter_enable_expr_applied_to_every_node():
    filt = build_text_block_filter(
        ["d.txt"], "f.ttf", bottom_margin=140, fontsize=34, enable="gte(t,3)"
    )
    # drawbox 1개 + drawtext 1개 = enable이 2번 등장해야 한다
    assert filt.count("enable='gte(t,3)'") == 2


def test_build_text_block_filter_no_literal_newline_char_in_output():
    # \n을 그대로 drawtext 하나에 넘기면 ffmpeg가 개행문자 자체를 tofu 글리프로 그리는
    # 버그가 있어(수동 렌더링으로 확인), 줄마다 별도 파일+drawtext로 쪼갠다.
    filt = build_text_block_filter(["line0.txt", "line1.txt"], "font.ttf", bottom_margin=360, fontsize=54)
    assert "\\n" not in filt


def test_build_scene_filter_complex_without_disclosure(tmp_path):
    font = resolve_font_path()
    filt = build_scene_filter_complex(5.0, "안녕 반가워요", font, str(tmp_path), "scene1")
    assert "[0:v]" in filt
    assert "[outv]" in filt
    assert "disc" not in filt


def test_build_scene_filter_complex_with_disclosure_has_enable_gate(tmp_path):
    font = resolve_font_path()
    filt = build_scene_filter_complex(
        10.0, "안녕 반가워요", font, str(tmp_path), "scene1", disclosure_line_paths=["disc.txt"]
    )
    assert "disc.txt" in filt
    assert "enable=" in filt
    assert "gte(t,8.0)" in filt  # 10초 씬의 마지막 2초부터 노출


def test_estimate_word_timings_spans_full_duration():
    timings = estimate_word_timings("안녕 반가워요 오늘도", 6.0)
    assert len(timings) == 3
    assert timings[0][1] == 0.0
    assert timings[-1][2] == 6.0
    # 시간 순서대로 이어져야 한다 (겹치거나 비는 구간 없이)
    for (_, _, end), (_, next_start, _) in zip(timings, timings[1:]):
        assert end == next_start


def test_estimate_word_timings_longer_word_gets_more_time():
    timings = estimate_word_timings("아 안녕하세요", 3.0)
    (word_a, start_a, end_a), (word_b, start_b, end_b) = timings
    assert word_a == "아" and word_b == "안녕하세요"
    assert (end_b - start_b) > (end_a - start_a)


def test_estimate_word_timings_empty_text_returns_empty_list():
    assert estimate_word_timings("", 5.0) == []


def test_build_animated_caption_filter_has_background_drawbox(tmp_path):
    font = resolve_font_path()
    filt = build_animated_caption_filter("안녕 반가워요", 4.0, font, str(tmp_path), "scene1")
    assert filt.startswith("drawbox=")


def test_build_animated_caption_filter_one_drawtext_per_word(tmp_path):
    font = resolve_font_path()
    filt = build_animated_caption_filter("안녕 반가워요 오늘도", 4.0, font, str(tmp_path), "scene1")
    assert filt.count("drawtext=") == 3


def test_build_animated_caption_filter_last_word_state_persists_to_scene_end(tmp_path):
    font = resolve_font_path()
    filt = build_animated_caption_filter("안녕 반가워요", 4.0, font, str(tmp_path), "scene1")
    assert "gte(t," in filt


def test_pick_bgm_track_returns_none_when_dir_missing(tmp_path):
    missing_dir = str(tmp_path / "no_such_dir")
    assert pick_bgm_track(missing_dir) is None


def test_pick_bgm_track_returns_none_when_dir_empty(tmp_path):
    empty_dir = tmp_path / "bgm"
    empty_dir.mkdir()
    assert pick_bgm_track(str(empty_dir)) is None


def test_pick_bgm_track_returns_a_file_when_present(tmp_path):
    bgm_dir = tmp_path / "bgm"
    bgm_dir.mkdir()
    track = bgm_dir / "track1.mp3"
    track.write_bytes(b"fake")
    picked = pick_bgm_track(str(bgm_dir))
    assert picked == str(track)


def test_resolve_font_path_finds_a_font():
    # 이 리포의 FONT_SEARCH_PATHS에는 Windows 시스템 폰트(malgun.ttf) 폴백이 있어
    # 로컬 개발 환경에서는 항상 찾아져야 한다. Phase 4에서 assets/fonts/ 번들 폰트로 교체될 예정.
    path = resolve_font_path()
    assert os.path.exists(path)


def test_wrap_text_lines_short_text_stays_one_line():
    font = resolve_font_path()
    lines = wrap_text_lines("짧은 문장", font, 54, max_width_px=900)
    assert lines == ["짧은 문장"]


def test_wrap_text_lines_long_disclosure_wraps_within_max_width():
    # 실제 렌더링에서 프레임 밖으로 삐져나갔던 고지문구로 회귀 테스트한다.
    font = resolve_font_path()
    disclosure = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
    max_width = 972  # DISCLOSURE_MAX_WIDTH와 동일한 값
    lines = wrap_text_lines(disclosure, font, 34, max_width_px=max_width)

    assert len(lines) > 1
    from PIL import ImageFont

    pil_font = ImageFont.truetype(font, 34)
    for line in lines:
        assert pil_font.getlength(line) <= max_width


def test_wrap_text_lines_respects_manual_newline():
    font = resolve_font_path()
    lines = wrap_text_lines("첫째 줄\n둘째 줄", font, 54, max_width_px=900)
    assert lines == ["첫째 줄", "둘째 줄"]


def test_build_hook_text_filter_writes_lines_and_draws_text(tmp_path):
    font = resolve_font_path()
    filt = build_hook_text_filter("이거 실화냐", font, str(tmp_path), "scene1")
    assert "drawtext=" in filt
    assert "bordercolor=black" in filt


def test_build_xfade_filter_complex_chains_all_clips():
    filt, v_label, a_label = build_xfade_filter_complex([3.0, 4.0, 2.0])
    assert filt.count("xfade=") == 2
    assert filt.count("acrossfade=") == 2
    assert v_label == "vout"
    assert a_label == "aout"


def test_build_xfade_filter_complex_offsets_account_for_overlap():
    # 2번째 전환은 (1번째 클립 길이 + 2번째 클립 길이 - 전환시간) - 전환시간 지점에서 시작해야 한다
    filt, _, _ = build_xfade_filter_complex([3.0, 4.0, 2.0], transition_dur=0.5)
    assert "offset=2.500" in filt  # 3.0 - 0.5
    assert "offset=6.000" in filt  # (3.0+4.0-0.5) - 0.5


def test_build_xfade_filter_complex_two_clips():
    filt, v_label, a_label = build_xfade_filter_complex([5.0, 5.0])
    assert filt.count("xfade=") == 1
    assert v_label == "vout"
