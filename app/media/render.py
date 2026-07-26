"""5호 직원 — FFmpeg 조립 (Phase 3).

실사 상품 이미지 + 2D 그래픽 레이어를 Ken Burns 줌 + TTS + 자막 번인 + BGM으로
합성해 완성 mp4를 만든다. 출력 규격: h264/yuv420p/1080x1920/30fps
(docs/phase3_spec.md, phase3_checklist.md 기준).

명령어 문자열을 만드는 순수 함수(build_*)와 실제로 ffmpeg/ffprobe를 실행하는
함수(run_ffmpeg, render_scene_clip 등)를 분리해, ffmpeg 없이도 문자열 조립 로직을
단위테스트할 수 있게 한다.
"""

from __future__ import annotations

import glob
import os
import random
import subprocess

from PIL import ImageFont

WIDTH = 1080
HEIGHT = 1920
FPS = 30
BGM_VOLUME_DB = -18
DISCLOSURE_OVERLAY_SEC = 2
# 기본 libx264 설정(대략 crf 23/medium)은 화질이 다소 무르게 나온다 — 자막 글자가 많은
# 영상 특성상 더 낮은 crf(고화질)+slow 프리셋으로 인코딩 품질을 올렸다. 씬 클립이 짧아서
# (몇 초) 느려진 프리셋으로 인한 전체 처리 시간 증가는 감내할 만하다고 판단.
VIDEO_ENCODE_ARGS = ["-c:v", "libx264", "-preset", "slow", "-crf", "18"]

CAPTION_FONTSIZE = 60
CAPTION_BOTTOM_MARGIN = 360
CAPTION_MAX_WIDTH = int(WIDTH * 0.88)
# 조회수 잘 나오는 쇼츠 자막 스타일(굵은 노란색 + 검정 외곽선)을 참고했다 — 흰 글씨 하나만
# 있을 때보다 훨씬 또렷하게 튀어 보인다.
CAPTION_TEXT_COLOR = "0xFFE600"
CAPTION_OUTLINE_COLOR = "black"
CAPTION_OUTLINE_WIDTH = 5
DISCLOSURE_FONTSIZE = 34
DISCLOSURE_BOTTOM_MARGIN = 140
DISCLOSURE_MAX_WIDTH = int(WIDTH * 0.90)
TEXT_LINE_HEIGHT = 70
TEXT_BOX_PADDING = 24
# 단어가 나타날 때 뚝 끊기지 않고 살짝 "팝"되는 느낌을 주는 짧은 페이드인 시간.
CAPTION_POP_FADE_SEC = 0.12

# Phase 4에서 Docker 이미지에 라이선스가 명확한 한글 폰트(예: Nanum Gothic, SIL OFL)를
# assets/fonts/에 번들할 예정. 그 전까지는 로컬 개발 환경의 시스템 폰트를 폴백으로 쓴다.
FONT_SEARCH_PATHS = [
    "assets/fonts/NanumGothic.ttf",
    "C:/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]


class RenderError(RuntimeError):
    """ffmpeg/ffprobe 실행 실패를 감싸는 명확한 예외."""


def resolve_font_path() -> str:
    for path in FONT_SEARCH_PATHS:
        if os.path.exists(path):
            return path
    raise RenderError(
        "한글 폰트를 찾을 수 없습니다. assets/fonts/에 폰트 파일을 추가하거나 "
        "FONT_SEARCH_PATHS에 시스템 폰트 경로를 등록하세요."
    )


def pick_bgm_track(bgm_dir: str = "assets/bgm") -> str | None:
    """assets/bgm/ 풀에서 무작위로 BGM 트랙을 고른다. 없으면 None(BGM 없이 진행)."""
    if not os.path.isdir(bgm_dir):
        return None
    candidates = glob.glob(os.path.join(bgm_dir, "*.mp3"))
    if not candidates:
        return None
    return random.choice(candidates)


def escape_path_for_filter(path: str) -> str:
    """ffmpeg filtergraph 안에 경로를 넣을 때 콜론(드라이브 문자)·백슬래시·따옴표를 이스케이프한다."""
    escaped = path.replace("\\", "/")
    escaped = escaped.replace(":", "\\:")
    escaped = escaped.replace("'", "\\'")
    return escaped


# 항상 x=0,y=0(기본값)이면 확대할수록 좌상단에 고정된 채 나머지가 우하단으로 빠져나가는
# 느낌만 나서 모든 씬의 이동 방향이 똑같아 보였다 — 씬마다 이 중 하나를 랜덤으로 골라 다양한
# 방향으로 팬 되게 한다. zoompan 표현식에서 iw/ih는 입력(스케일된) 프레임 크기를 가리킨다.
ZOOM_PAN_DIRECTIONS: dict[str, tuple[str, str]] = {
    "top_left": ("0", "0"),
    "top_right": ("iw-iw/zoom", "0"),
    "bottom_left": ("0", "ih-ih/zoom"),
    "bottom_right": ("iw-iw/zoom", "ih-ih/zoom"),
    "center": ("iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
}


def build_zoompan_filter(duration_sec: float, fps: int = FPS, pan: str | None = None) -> str:
    """Ken Burns 줌 효과 filter 문자열을 만든다.

    pan을 지정하지 않으면 ZOOM_PAN_DIRECTIONS 중 하나를 랜덤으로 고른다(테스트 등에서
    특정 방향을 고정하고 싶으면 pan에 키 이름을 넘기면 된다).
    """
    frames = max(int(round(duration_sec * fps)), 1)
    direction = pan or random.choice(list(ZOOM_PAN_DIRECTIONS))
    x_expr, y_expr = ZOOM_PAN_DIRECTIONS[direction]
    return (
        f"scale={WIDTH * 2}:{HEIGHT * 2},"
        f"zoompan=z='min(zoom+0.0006,1.15)':x='{x_expr}':y='{y_expr}':d={frames}:s={WIDTH}x{HEIGHT}:fps={fps},setsar=1"
    )


def build_text_block_filter(
    line_paths: list[str],
    font_path: str,
    bottom_margin: int,
    fontsize: int,
    line_height: int = TEXT_LINE_HEIGHT,
    box_padding: int = TEXT_BOX_PADDING,
    enable: str | None = None,
) -> str:
    """여러 줄을 배경 박스(drawbox) + 줄마다 별도 drawtext로 그리는 filtergraph 조각을 만든다.

    ffmpeg drawtext에 개행문자(\\n)가 포함된 텍스트를 한 번에 넘기면, 줄바꿈 위치 계산은
    맞게 하면서도 개행문자 자체를 빈 네모(tofu) 글리프로 그려버리는 문제가 있다.
    그래서 줄 단위로 미리 쪼개 각각 별도 drawtext 노드로 그린다.
    """
    escaped_font = escape_path_for_filter(font_path)
    box_height = line_height * len(line_paths) + box_padding * 2
    # drawbox 표현식 안에서 h는 (이 필터가 그리는) 박스 자신의 높이를 가리키고, 프레임 높이는
    # ih(input height)다 — 여기 h를 썼던 탓에 자막 배경 박스가 화면에 전혀 안 보이던 버그가
    # 있었다(drawtext는 반대로 h가 프레임 높이라 텍스트 자체는 정상 위치에 있었다).
    box_top = f"ih-{bottom_margin}-{box_height}"

    enable_suffix = f":enable='{enable}'" if enable else ""
    filters = [f"drawbox=x=0:y={box_top}:w=iw:h={box_height}:color=black@0.55:t=fill{enable_suffix}"]

    for i, path in enumerate(line_paths):
        escaped_text = escape_path_for_filter(path)
        y = f"h-{bottom_margin}-{box_height}+{box_padding + i * line_height}"
        filters.append(
            f"drawtext=fontfile='{escaped_font}':textfile='{escaped_text}':fontcolor=white:"
            f"fontsize={fontsize}:x=(w-text_w)/2:y={y}:text_shaping=0{enable_suffix}"
        )
    return ",".join(filters)


def build_animated_caption_filter(
    text: str,
    font_path: str,
    work_dir: str,
    basename: str,
    bottom_margin: int = CAPTION_BOTTOM_MARGIN,
    fontsize: int = CAPTION_FONTSIZE,
    max_width_px: int = CAPTION_MAX_WIDTH,
    line_height: int = TEXT_LINE_HEIGHT,
    box_padding: int = TEXT_BOX_PADDING,
) -> str:
    """자막 문장 전체를 씬 시작과 동시에 페이드인시켜 끝까지 그대로 보여준다.

    이전엔 단어가 하나씩 늘어나며 문장이 완성되어가는("노래방 자막") 방식이었는데, 실제로
    보니 그 완성되어가는 모습이 어색하다는 피드백을 받아 문장 전체를 한 번에 드러내는
    방식으로 바꿨다.
    """
    escaped_font = escape_path_for_filter(font_path)
    lines = wrap_text_lines(text, font_path, fontsize, max_width_px)
    box_height = line_height * len(lines) + box_padding * 2
    box_top = f"ih-{bottom_margin}-{box_height}"

    filters = [f"drawbox=x=0:y={box_top}:w=iw:h={box_height}:color=black@0.55:t=fill"]
    # 씬 시작(t=0)부터 CAPTION_POP_FADE_SEC 동안 alpha가 0에서 1로 올라가고, 이후 씬이
    # 끝날 때까지 그대로 유지된다 — 뚝 나타나는 대신 살짝 페이드인되는 느낌만 남긴다.
    alpha = f"min(t/{CAPTION_POP_FADE_SEC},1)"
    for line_i, line in enumerate(lines):
        # drawtext에서는 (drawbox와 반대로) h가 이미 프레임 높이를 가리킨다 — ih를 쓰면 안 된다.
        y = f"h-{bottom_margin}-{box_height}+{box_padding + line_i * line_height}"
        path = os.path.join(work_dir, f"{basename}.caption.line{line_i}.txt")
        _write_text_file(line, path)
        escaped_text = escape_path_for_filter(path)
        filters.append(
            f"drawtext=fontfile='{escaped_font}':textfile='{escaped_text}':fontcolor={CAPTION_TEXT_COLOR}:"
            f"bordercolor={CAPTION_OUTLINE_COLOR}:borderw={CAPTION_OUTLINE_WIDTH}:alpha='{alpha}':"
            f"fontsize={fontsize}:x=(w-text_w)/2:y={y}:text_shaping=0"
        )
    return ",".join(filters)


HOOK_FONTSIZE = 66
HOOK_TOP_MARGIN = 160
HOOK_MAX_WIDTH = int(WIDTH * 0.86)
HOOK_LINE_HEIGHT = HOOK_FONTSIZE + 14


def build_hook_text_filter(text: str, font_path: str, work_dir: str, basename: str) -> str:
    """첫 씬 상단에 처음부터(단어 등장 없이) 큼직하게 박아두는 후킹 문구.

    쇼츠 초반 1~2초 안에 시선을 붙잡는 "패턴 인터럽트" 문구 관행을 참고했다 — 하단의
    단어별 등장 자막과 별개로, 화면 위쪽에 고정된 굵은 헤드라인을 하나 더 얹는다.
    """
    escaped_font = escape_path_for_filter(font_path)
    lines = wrap_text_lines(text, font_path, HOOK_FONTSIZE, HOOK_MAX_WIDTH)
    filters = []
    for i, line in enumerate(lines):
        path = os.path.join(work_dir, f"{basename}.hook.line{i}.txt")
        _write_text_file(line, path)
        escaped_text = escape_path_for_filter(path)
        y = HOOK_TOP_MARGIN + i * HOOK_LINE_HEIGHT
        filters.append(
            f"drawtext=fontfile='{escaped_font}':textfile='{escaped_text}':fontcolor=white:"
            f"bordercolor=black:borderw=6:fontsize={HOOK_FONTSIZE}:x=(w-text_w)/2:y={y}:text_shaping=0"
        )
    return ",".join(filters)


def build_scene_filter_complex(
    duration_sec: float,
    caption_text: str,
    font_path: str,
    work_dir: str,
    basename: str,
    disclosure_line_paths: list[str] | None = None,
    hook_text: str | None = None,
    has_icon: bool = False,
) -> str:
    """이미지 한 장을 Ken Burns + 자막(+ 첫 씬은 상단 후킹 문구, 마지막 씬은
    아이콘 오버레이 + 고지 오버레이)까지 입힌 filter_complex를 만든다."""
    zoompan = build_zoompan_filter(duration_sec)
    caption_block = build_animated_caption_filter(caption_text, font_path, work_dir, basename)
    hook_block = build_hook_text_filter(hook_text, font_path, work_dir, basename) if hook_text else None

    stage = f"[0:v]{zoompan}[zoomed];[zoomed]{caption_block}"
    if hook_block:
        stage = f"{stage}[capped_caption];[capped_caption]{hook_block}"

    if has_icon:
        # 아이콘을 상품 사진에 직접 합성해두면 Ken Burns 확대/이동에 같이 크롭돼 랜덤
        # 팬 방향에 따라 화면 밖으로 밀려날 수 있다 — 줌 이후 단계에서 오버레이로 얹어
        # 팬/줌과 무관하게 항상 같은 위치에 고정되게 한다. 아이콘은 입력 인덱스 2번
        # (0=이미지, 1=오디오, 2=아이콘)로 들어온다.
        stage = f"{stage}[precap];[precap][2:v]overlay=x=W-w-60:y=100"

    if disclosure_line_paths is None:
        # JPEG 소스는 풀레인지(yuvj420p)로 디코딩되기 쉬워 명시적으로 yuv420p(리미티드 레인지)로
        # 재태깅한다 — 안 그러면 libx264가 yuvj420p로 인코딩해 phase3_checklist 3번(pix_fmt) 위반.
        return f"{stage},format=yuv420p[outv]"

    enable_expr = f"gte(t,{max(duration_sec - DISCLOSURE_OVERLAY_SEC, 0)})"
    disclosure_block = build_text_block_filter(
        disclosure_line_paths,
        font_path,
        bottom_margin=DISCLOSURE_BOTTOM_MARGIN,
        fontsize=DISCLOSURE_FONTSIZE,
        enable=enable_expr,
    )
    return f"{stage}[capped];[capped]{disclosure_block},format=yuv420p[outv]"


def _write_text_file(text: str, path: str) -> str:
    # newline="" — Windows에서 "\n"이 "\r\n"으로 자동 변환되면 ffmpeg drawtext가 "\r"을
    # 빈 네모(tofu) 글리프로 그려버린다. LF만 그대로 쓰기 위해 자동 변환을 끈다.
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


def wrap_text_lines(text: str, font_path: str, fontsize: int, max_width_px: int) -> list[str]:
    """수동 개행("\\n")은 그대로 지키면서, 각 줄이 max_width_px를 넘으면 단어 단위로 추가 줄바꿈한다.

    실제 폰트 메트릭(Pillow)으로 폭을 재기 때문에, 긴 고지문구 등이 프레임 밖으로
    삐져나가는 것을 방지한다(수동 렌더링 확인 중 발견한 버그).
    """
    font = ImageFont.truetype(font_path, fontsize)
    result: list[str] = []
    for hard_line in text.split("\n"):
        words = hard_line.split(" ")
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if not current or font.getlength(candidate) <= max_width_px:
                current = candidate
            else:
                result.append(current)
                current = word
        result.append(current)
    return result or [""]


def _write_lines(
    text: str,
    work_dir: str,
    prefix: str,
    font_path: str,
    fontsize: int,
    max_width_px: int,
) -> list[str]:
    """줄바꿈까지 적용한 텍스트를 줄 단위로 쪼개 각각 파일로 저장한다 (build_text_block_filter와 짝)."""
    paths = []
    for i, line in enumerate(wrap_text_lines(text, font_path, fontsize, max_width_px)):
        path = os.path.join(work_dir, f"{prefix}.line{i}.txt")
        _write_text_file(line, path)
        paths.append(path)
    return paths


def run_ffmpeg(args: list[str]) -> None:
    try:
        subprocess.run(["ffmpeg", "-y", *args], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise RenderError(f"ffmpeg 실행 실패: {exc.stderr[-2000:]}") from exc
    except FileNotFoundError as exc:
        raise RenderError("ffmpeg 실행 파일을 찾을 수 없습니다.") from exc


def pad_audio_with_silence(audio_path: str, gap_sec: float, output_path: str) -> str:
    """오디오 끝에 무음을 이어붙인다 — 씬 사이 나레이션이 곧바로 이어져 부자연스럽던 문제를
    해결하기 위해, 각 씬 오디오 뒤에 짧은 무음 구간을 넣어 다음 씬으로 넘어가기 전 숨 고를
    틈을 만든다(씬 전환은 크로스페이드로 자연스럽게 겹치지만, 그 겹침 구간이 이 무음
    구간과 맞물리게 해서 실제 목소리끼리는 겹치지 않는다)."""
    run_ffmpeg(["-i", audio_path, "-af", f"apad=pad_dur={gap_sec}", output_path])
    return output_path


# 나레이션이 다소 늘어지는 느낌이라는 피드백으로 도입한 기본 배속 — scenes[].duration_sec이
# 없거나 못 믿을 값일 때(0 이하 등)만 이 고정값으로 폴백한다. 정상적인 경우엔 씬마다
# calc_narration_speed로 계산한 배율을 쓴다(대본이 계획한 씬 길이를 실제 렌더링에 반영).
NARRATION_SPEED = 1.1
# atempo 배율의 상하한 — 대본이 잡은 duration_sec과 실제 TTS 길이 차이가 너무 크면(예: 문장은
# 짧은데 계획한 시간은 김) 배율을 그대로 걸었을 때 목소리가 부자연스럽게 빠르거나 느려진다.
# 자연스러운 범위 안에서만 목표 시간에 맞추고, 그 이상 벗어나면 clamp된 배율만큼만 반영한다.
MIN_NARRATION_SPEED = 0.85
MAX_NARRATION_SPEED = 1.3


def speed_up_audio(audio_path: str, output_path: str, speed: float = NARRATION_SPEED) -> str:
    """나레이션 오디오를 speed배로 재생 속도만 높인다(피치는 atempo가 자동 보정해 유지)."""
    run_ffmpeg(["-i", audio_path, "-af", f"atempo={speed}", output_path])
    return output_path


def calc_narration_speed(actual_duration_sec: float, target_duration_sec: float | None) -> float:
    """실제 TTS 길이를 목표 duration_sec에 맞추는 데 필요한 배속을 자연스러운 범위로 clamp해 돌려준다.

    target_duration_sec이 없거나 0 이하면(대본에 값이 없거나 이상치) NARRATION_SPEED로 폴백한다.
    """
    if not target_duration_sec or target_duration_sec <= 0:
        return NARRATION_SPEED
    speed = actual_duration_sec / target_duration_sec
    return max(MIN_NARRATION_SPEED, min(speed, MAX_NARRATION_SPEED))


def render_scene_clip(
    image_path: str,
    audio_path: str,
    duration_sec: float,
    caption_text: str,
    output_path: str,
    work_dir: str,
    font_path: str | None = None,
    disclosure_text: str | None = None,
    hook_text: str | None = None,
    icon_path: str | None = None,
) -> str:
    """이미지+오디오 한 씬을 Ken Burns+자막(+고지+아이콘)까지 입힌 mp4 클립으로 렌더링한다."""
    active_font = font_path or resolve_font_path()
    # output_path 기반으로 고유 파일명을 만든다 — 여러 씬이 같은 work_dir을 공유할 때
    # 고정 파일명을 쓰면 다음 씬이 이전 씬의 캡션 파일을 덮어써버린다.
    basename = os.path.splitext(os.path.basename(output_path))[0]
    disclosure_paths = None
    if disclosure_text:
        disclosure_paths = _write_lines(
            disclosure_text,
            work_dir,
            f"{basename}.disclosure",
            active_font,
            DISCLOSURE_FONTSIZE,
            DISCLOSURE_MAX_WIDTH,
        )

    filter_complex = build_scene_filter_complex(
        duration_sec, caption_text, active_font, work_dir, basename, disclosure_paths, hook_text,
        has_icon=bool(icon_path),
    )

    inputs = ["-loop", "1", "-i", image_path, "-i", audio_path]
    if icon_path:
        inputs += ["-loop", "1", "-i", icon_path]

    run_ffmpeg(
        [
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", "1:a",
            *VIDEO_ENCODE_ARGS, "-pix_fmt", "yuv420p", "-color_range", "tv", "-r", str(FPS),
            "-t", str(duration_sec),
            "-c:a", "aac", "-shortest",
            output_path,
        ]
    )
    return output_path


def _escape_path_for_concat_list(path: str) -> str:
    """concat 데뮤서 목록 파일은 filter_complex와 파서가 달라 콜론 이스케이프가 필요 없다."""
    return path.replace("\\", "/").replace("'", "'\\''")


def concat_clips(clip_paths: list[str], list_file_path: str, output_path: str) -> str:
    lines = [f"file '{_escape_path_for_concat_list(os.path.abspath(p))}'" for p in clip_paths]
    _write_text_file("\n".join(lines), list_file_path)
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", list_file_path, "-c", "copy", output_path])
    return output_path


TRANSITION_DURATION_SEC = 0.4
TRANSITION_STYLE = "fade"


def build_xfade_filter_complex(
    durations: list[float], transition: str = TRANSITION_STYLE, transition_dur: float = TRANSITION_DURATION_SEC
) -> tuple[str, str, str]:
    """xfade(영상)+acrossfade(오디오)를 씬 개수만큼 체인으로 엮은 filter_complex를 만든다.

    concat 데뮤서(-c copy)는 클립을 그냥 이어붙이기만 해서 컷이 딱딱 끊긴다 — 화면이
    자연스럽게 겹쳐 넘어가도록 각 전환마다 짧게 크로스페이드를 넣는다. 반환값은
    (filter_complex 문자열, 최종 비디오 라벨, 최종 오디오 라벨).
    """
    n = len(durations)
    parts = []
    v_label, a_label = "0:v", "0:a"
    cumulative = durations[0]
    for i in range(1, n):
        next_v, next_a = f"{i}:v", f"{i}:a"
        out_v = "vout" if i == n - 1 else f"v{i}"
        out_a = "aout" if i == n - 1 else f"a{i}"
        offset = max(cumulative - transition_dur, 0)
        parts.append(f"[{v_label}][{next_v}]xfade=transition={transition}:duration={transition_dur}:offset={offset:.3f}[{out_v}]")
        parts.append(f"[{a_label}][{next_a}]acrossfade=d={transition_dur}[{out_a}]")
        v_label, a_label = out_v, out_a
        cumulative = cumulative + durations[i] - transition_dur
    return ";".join(parts), v_label, a_label


def concat_clips_with_transitions(
    clip_paths: list[str],
    durations: list[float],
    output_path: str,
    transition: str = TRANSITION_STYLE,
    transition_dur: float = TRANSITION_DURATION_SEC,
) -> str:
    """씬 클립들을 하드컷 대신 짧은 크로스페이드로 이어붙인다.

    xfade/acrossfade는 스트림을 다시 인코딩해야 해서(-c copy 불가) concat_clips보다 느리지만,
    씬 전환이 뚝뚝 끊기지 않고 자연스럽게 넘어간다.
    """
    if len(clip_paths) == 1:
        run_ffmpeg(["-i", clip_paths[0], "-c", "copy", output_path])
        return output_path

    filter_complex, v_label, a_label = build_xfade_filter_complex(durations, transition, transition_dur)
    inputs = []
    for p in clip_paths:
        inputs += ["-i", p]
    run_ffmpeg(
        [
            *inputs,
            "-filter_complex", filter_complex,
            "-map", f"[{v_label}]", "-map", f"[{a_label}]",
            *VIDEO_ENCODE_ARGS, "-pix_fmt", "yuv420p", "-color_range", "tv", "-r", str(FPS),
            "-c:a", "aac",
            output_path,
        ]
    )
    return output_path


def mix_bgm(video_path: str, bgm_path: str | None, output_path: str) -> str:
    if bgm_path is None:
        run_ffmpeg(["-i", video_path, "-c", "copy", output_path])
        return output_path

    filter_complex = (
        f"[1:a]volume={BGM_VOLUME_DB}dB[bgm];"
        "[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )
    run_ffmpeg(
        [
            "-i", video_path,
            "-stream_loop", "-1", "-i", bgm_path,
            "-filter_complex", filter_complex,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            output_path,
        ]
    )
    return output_path
