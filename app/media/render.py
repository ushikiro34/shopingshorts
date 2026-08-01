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
# 오가닉 쇼츠 세이프존(하단 350~400px) 기준으론 부족하지만, 바로 위 CTA 자막 박스
# (CTA_CAPTION_BOTTOM_MARGIN=390 기준 화면 하단에서 390px 지점)와 겹치면 안 돼서 그 밑에
# 최대한 붙여 끌어올릴 수 있는 한계값이다 — 기존 140에서 두 배 이상 개선.
DISCLOSURE_BOTTOM_MARGIN = 290
DISCLOSURE_LINE_HEIGHT = 42  # 폰트 34px에 맞춘 줄간격 — 일반 자막용 TEXT_LINE_HEIGHT(70)는 과함
DISCLOSURE_OUTLINE_WIDTH = 3
DISCLOSURE_MAX_WIDTH = int(WIDTH * 0.90)
TEXT_LINE_HEIGHT = 70
TEXT_BOX_PADDING = 24

# 마지막 씬(CTA 자막)은 일반 자막보다 글자를 작게, 화면 더 아래쪽에 배치한다(사용자 피드백).
# 고지문구 오버레이(DISCLOSURE_BOTTOM_MARGIN=140, 마지막 2초간 노출)와 겹치지 않는 선에서
# 최대한 낮췄다.
CTA_CAPTION_FONTSIZE = 46
CTA_CAPTION_LINE_HEIGHT = 54
# 오가닉 쇼츠 세이프존 기준(한국 크리에이터 가이드: 하단 350~400px) — 유료 광고 세이프존
# 표(672px)까지는 과함, CTA는 일반 자막보다 여백을 더 줘야 한다는 리서치에 맞춰 상향.
CTA_CAPTION_BOTTOM_MARGIN = 390
# 단어가 나타날 때 뚝 끊기지 않고 살짝 "팝"되는 느낌을 주는 짧은 페이드인 시간.
CAPTION_POP_FADE_SEC = 0.12

# 상단(후킹+제품명)/중간(영상)/하단(자막·CTA) 3단 레이아웃 절충안(사용자 피드백)의 하단
# 파트 — 씬마다 짧은 CTA 문구를 자막 바로 아래 작게 상시 노출한다. 자막(margin=360)과
# 안 겹치게 그 밑에 둬야 해서, 오가닉 세이프존 권장 하한(350~400px)보다는 아래로 내려간다
# — CTA 배너는 핵심 정보(자막·마지막씬 CTA)가 아니라 보조 리마인더라 감내할 만하다고 판단.
STICKY_CTA_FONTSIZE = 32
STICKY_CTA_LINE_HEIGHT = 38
STICKY_CTA_BOTTOM_MARGIN = 190
STICKY_CTA_OUTLINE_WIDTH = 3
STICKY_CTA_MAX_WIDTH = int(WIDTH * 0.90)

# assets/fonts/NanumGothic.ttf(SIL OFL, google/fonts 저장소에서 번들)를 최우선으로 쓴다 —
# 이게 없으면 Railway(리눅스) 배포 시 시스템에 한글 폰트가 없어 렌더링 자체가 실패한다.
# 아래 나머지 경로는 로컬 개발 환경 폴백용.
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
    enable: str | None = None,
    fontcolor: str = "white",
    outline_width: int = DISCLOSURE_OUTLINE_WIDTH,
) -> str:
    """여러 줄을 줄마다 별도 drawtext로 그리는 filtergraph 조각을 만든다.

    배경 박스(drawbox) 없이 글자에 검정 외곽선만 둘러 가독성을 확보한다 — 반투명 박스가
    화면을 답답하게 가린다는 피드백으로 없앴다(원래는 고지문구 전용이었는데, 상시노출
    CTA 배너도 같은 스타일을 재사용한다).

    ffmpeg drawtext에 개행문자(\\n)가 포함된 텍스트를 한 번에 넘기면, 줄바꿈 위치 계산은
    맞게 하면서도 개행문자 자체를 빈 네모(tofu) 글리프로 그려버리는 문제가 있다.
    그래서 줄 단위로 미리 쪼개 각각 별도 drawtext 노드로 그린다.
    """
    escaped_font = escape_path_for_filter(font_path)
    block_height = line_height * len(line_paths)
    enable_suffix = f":enable='{enable}'" if enable else ""

    filters = []
    for i, path in enumerate(line_paths):
        escaped_text = escape_path_for_filter(path)
        y = f"h-{bottom_margin}-{block_height}+{i * line_height}"
        filters.append(
            f"drawtext=fontfile='{escaped_font}':textfile='{escaped_text}':fontcolor={fontcolor}:"
            f"bordercolor=black:borderw={outline_width}:"
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
# 오가닉 쇼츠 세이프존 기준(한국 크리에이터 가이드: 상단 250~300px) — 상단 프로필/로고
# UI와 겹치지 않도록 상향.
HOOK_TOP_MARGIN = 260
HOOK_MAX_WIDTH = int(WIDTH * 0.86)
HOOK_LINE_HEIGHT = HOOK_FONTSIZE + 14

# 상단 후킹 문구 바로 아래 작게 얹는 제품명 — 캡션 강조색(노란색)으로 헤드라인과
# 구분되게 한다(3단 레이아웃 절충안: 상단 후킹+제품명, 중간 영상, 하단 자막/CTA).
HOOK_PRODUCT_NAME_FONTSIZE = 34
HOOK_PRODUCT_NAME_GAP = 12


def build_hook_text_filter(
    text: str, font_path: str, work_dir: str, basename: str, product_name: str | None = None
) -> str:
    """첫 씬 상단에 처음부터(단어 등장 없이) 큼직하게 박아두는 후킹 문구(+제품명).

    쇼츠 초반 1~2초 안에 시선을 붙잡는 "패턴 인터럽트" 문구 관행을 참고했다 — 하단의
    단어별 등장 자막과 별개로, 화면 위쪽에 고정된 굵은 헤드라인을 하나 더 얹는다.

    product_name을 넘기면 후킹 문구 바로 아래 작게 브랜드/제품명을 한 줄 더 얹는다 —
    상단(후킹+제품명)/중간(영상)/하단(자막·CTA) 3단 레이아웃 절충안(사용자 피드백)의
    상단 파트. 첫 씬(문제 상황)에만 표시하고 이후 씬에는 반복하지 않는다.
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

    if product_name:
        path = os.path.join(work_dir, f"{basename}.hook_product.txt")
        _write_text_file(product_name, path)
        escaped_text = escape_path_for_filter(path)
        y = HOOK_TOP_MARGIN + len(lines) * HOOK_LINE_HEIGHT + HOOK_PRODUCT_NAME_GAP
        filters.append(
            f"drawtext=fontfile='{escaped_font}':textfile='{escaped_text}':fontcolor={CAPTION_TEXT_COLOR}:"
            f"bordercolor=black:borderw=4:fontsize={HOOK_PRODUCT_NAME_FONTSIZE}:x=(w-text_w)/2:y={y}:text_shaping=0"
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
    caption_fontsize: int = CAPTION_FONTSIZE,
    caption_bottom_margin: int = CAPTION_BOTTOM_MARGIN,
    caption_line_height: int = TEXT_LINE_HEIGHT,
    product_name: str | None = None,
    sticky_cta_text: str | None = None,
) -> str:
    """이미지 한 장을 Ken Burns + 자막(+ 첫 씬은 상단 후킹 문구, 마지막 씬은
    고지 오버레이)까지 입힌 filter_complex를 만든다.

    caption_text가 비어있으면 하단 자막 자체를 그리지 않는다 — 첫 씬은 상단 후킹 문구와
    하단 자막이 같은 문장을 중복으로 보여주는 게 어색하다는 피드백으로, 후킹이 있는 씬은
    하단 자막을 생략할 수 있게 한다.

    product_name은 hook_text와 함께(첫 씬에만) 상단에 작게 얹는다. sticky_cta_text는
    자막 바로 아래에 작게 상시 노출하는 CTA 배너다 — 3단 레이아웃 절충안(사용자 피드백).
    """
    zoompan = build_zoompan_filter(duration_sec)
    blocks = []
    if caption_text:
        blocks.append(
            build_animated_caption_filter(
                caption_text, font_path, work_dir, basename,
                fontsize=caption_fontsize, bottom_margin=caption_bottom_margin, line_height=caption_line_height,
            )
        )
    if hook_text:
        blocks.append(build_hook_text_filter(hook_text, font_path, work_dir, basename, product_name=product_name))
    if sticky_cta_text:
        sticky_paths = _write_lines(
            sticky_cta_text, work_dir, f"{basename}.sticky_cta", font_path, STICKY_CTA_FONTSIZE, STICKY_CTA_MAX_WIDTH
        )
        blocks.append(
            build_text_block_filter(
                sticky_paths, font_path,
                bottom_margin=STICKY_CTA_BOTTOM_MARGIN, fontsize=STICKY_CTA_FONTSIZE,
                line_height=STICKY_CTA_LINE_HEIGHT, fontcolor=CAPTION_TEXT_COLOR,
                outline_width=STICKY_CTA_OUTLINE_WIDTH,
            )
        )

    if blocks:
        stage = f"[0:v]{zoompan}[zoomed];[zoomed]{','.join(blocks)}"
    else:
        # 자막도 후킹도 없으면(이론상으로만 발생) zoompan 출력을 라벨 없이 그대로 이어간다 —
        # 아래 disclosure/format 단계가 콤마로 이어붙일 수 있는 "열린" 체인 상태를 유지한다.
        stage = f"[0:v]{zoompan}"

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
        line_height=DISCLOSURE_LINE_HEIGHT,
        enable=enable_expr,
    )
    return f"{stage}[capped];[capped]{disclosure_block},format=yuv420p[outv]"


def build_video_scene_filter_complex(
    caption_text: str,
    font_path: str,
    work_dir: str,
    basename: str,
    hook_text: str | None = None,
    caption_fontsize: int = CAPTION_FONTSIZE,
    caption_bottom_margin: int = CAPTION_BOTTOM_MARGIN,
    caption_line_height: int = TEXT_LINE_HEIGHT,
    product_name: str | None = None,
    sticky_cta_text: str | None = None,
) -> str:
    """AI로 생성한 실제 영상(Veo) 한 클립에 자막(+후킹 문구)만 입힌 filter_complex를 만든다.

    build_scene_filter_complex와 달리 Ken Burns(zoompan)를 적용하지 않는다 — 입력 자체가
    이미 실제 움직임이 있는 영상이라 정지 이미지용 팬/줌 효과가 필요 없고 오히려 어색해진다.
    출력 해상도만 캔버스 규격(1080x1920)에 맞춘다.
    """
    blocks = []
    if caption_text:
        blocks.append(
            build_animated_caption_filter(
                caption_text, font_path, work_dir, basename,
                fontsize=caption_fontsize, bottom_margin=caption_bottom_margin, line_height=caption_line_height,
            )
        )
    if hook_text:
        blocks.append(build_hook_text_filter(hook_text, font_path, work_dir, basename, product_name=product_name))
    if sticky_cta_text:
        sticky_paths = _write_lines(
            sticky_cta_text, work_dir, f"{basename}.sticky_cta", font_path, STICKY_CTA_FONTSIZE, STICKY_CTA_MAX_WIDTH
        )
        blocks.append(
            build_text_block_filter(
                sticky_paths, font_path,
                bottom_margin=STICKY_CTA_BOTTOM_MARGIN, fontsize=STICKY_CTA_FONTSIZE,
                line_height=STICKY_CTA_LINE_HEIGHT, fontcolor=CAPTION_TEXT_COLOR,
                outline_width=STICKY_CTA_OUTLINE_WIDTH,
            )
        )

    # Veo가 요청한 9:16과 정확히 일치하지 않는 해상도로 응답하면, scale=W:H로 그냥 강제
    # 리사이즈할 경우 화면이 가로/세로 비율이 안 맞게 눌리거나 늘어나 보인다(비율 왜곡
    # 피드백) — 종횡비를 유지한 채 캔버스를 꽉 채우도록 확대한 뒤 초과분만 크롭한다.
    scale = f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},setsar=1"
    if blocks:
        stage = f"[0:v]{scale}[scaled];[scaled]{','.join(blocks)}"
    else:
        stage = f"[0:v]{scale}"
    return f"{stage},format=yuv420p[outv]"


def render_video_scene_clip(
    video_path: str,
    audio_path: str,
    duration_sec: float,
    caption_text: str,
    output_path: str,
    work_dir: str,
    font_path: str | None = None,
    hook_text: str | None = None,
    caption_fontsize: int = CAPTION_FONTSIZE,
    caption_bottom_margin: int = CAPTION_BOTTOM_MARGIN,
    caption_line_height: int = TEXT_LINE_HEIGHT,
    product_name: str | None = None,
    sticky_cta_text: str | None = None,
) -> str:
    """AI 생성 영상(Veo)+나레이션 오디오 한 씬을 자막까지 입힌 mp4 클립으로 렌더링한다.

    영상 자체에 Veo가 붙인 오디오(대사·효과음)가 있지만 우리 나레이션으로 완전히 대체한다 —
    1:a(나레이션)만 매핑하고 0:a(영상 자체 오디오)는 매핑하지 않는다. 영상 길이가 씬
    duration_sec보다 길면(Veo는 보통 8초 고정) -t 옵션이 그만큼만 잘라 쓴다.
    """
    active_font = font_path or resolve_font_path()
    basename = os.path.splitext(os.path.basename(output_path))[0]

    filter_complex = build_video_scene_filter_complex(
        caption_text, active_font, work_dir, basename, hook_text,
        caption_fontsize=caption_fontsize, caption_bottom_margin=caption_bottom_margin,
        caption_line_height=caption_line_height,
        product_name=product_name, sticky_cta_text=sticky_cta_text,
    )

    run_ffmpeg(
        [
            "-i", video_path, "-i", audio_path,
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", "1:a",
            *VIDEO_ENCODE_ARGS, "-pix_fmt", "yuv420p", "-color_range", "tv", "-r", str(FPS),
            "-t", str(duration_sec),
            "-c:a", "aac", "-shortest",
            output_path,
        ]
    )
    return output_path


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
# 하한을 0.85에서 0.95로 좁혔다 — 짧은 CTA 문장에서 duration_sec이 실제보다 넉넉하게
# 잡히는 경우가 흔한데, 0.85까지 느려지면 목소리가 눈에 띄게 늘어져 들린다는 피드백이 있었다
# (실측: "제품정보는 본문에 있어요, 확인해보세요." 실제 3.3초를 4초에 맞추려다 0.85로 clamp됨).
# 목표 시간에 못 미치는 건 감내하고, 대신 부자연스러운 저속 재생은 피한다.
MIN_NARRATION_SPEED = 0.95
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
    caption_fontsize: int = CAPTION_FONTSIZE,
    caption_bottom_margin: int = CAPTION_BOTTOM_MARGIN,
    caption_line_height: int = TEXT_LINE_HEIGHT,
    product_name: str | None = None,
    sticky_cta_text: str | None = None,
) -> str:
    """이미지+오디오 한 씬을 Ken Burns+자막(+고지)까지 입힌 mp4 클립으로 렌더링한다."""
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
        caption_fontsize=caption_fontsize, caption_bottom_margin=caption_bottom_margin,
        caption_line_height=caption_line_height,
        product_name=product_name, sticky_cta_text=sticky_cta_text,
    )

    inputs = ["-loop", "1", "-i", image_path, "-i", audio_path]

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
# "fade"(디졸브)는 두 씬 화면이 겹쳐 보이는 구간이 생기는데, 씬마다 AI로 독립 생성한 이미지라
# 구도·인물 위치가 서로 달라서 그 겹침이 이중노출처럼 보여 "오류 같다"는 피드백이 있었다.
# "fadeblack"은 화면을 검은색으로 살짝 거쳐가서 두 이미지가 동시에 겹쳐 보이지 않는다.
TRANSITION_STYLE = "fadeblack"


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
