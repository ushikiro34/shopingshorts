import os

from dotenv import load_dotenv

load_dotenv()

# AGENTS.md 절대 규칙 3 — 모든 대본/유튜브 설명문에 하드코딩으로 포함해야 하는 고지문구.
PARTNERS_DISCLOSURE = (
    "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
)

# 게시 전 냉각기간 기본값(분). 경과해야 /publish 버튼이 활성화된다 (Phase 4).
DEFAULT_HOLD_MINUTES = int(os.getenv("DEFAULT_HOLD_MINUTES", "240"))

# docs/03_interfaces.md 8번 — 상품 발굴 시 category+product_name에 포함되면 needs_education=true 자동 설정.
# 목록은 초기값이며 운영하면서 보강한다.
EDUCATION_TRIGGER_KEYWORDS = [
    "자외선", "UV", "차단제", "선크림",
    "살균", "항균", "소독",
    "정수", "필터", "공기청정",
    "유산균", "프로바이오틱스",
    "탈취", "제습",
]

COUPANG_ACCESS_KEY = os.getenv("COUPANG_ACCESS_KEY", "")
COUPANG_SECRET_KEY = os.getenv("COUPANG_SECRET_KEY", "")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")

# 상품 스코어링 — docs/00_project_overview.md의 "충동구매 가능성" 임계값.
IMPULSE_PRICE_THRESHOLD = 30000

# GET /api/products 기본 노출 임계값 (하루 3편 목표라 70 -> 80으로 상향, overview.md v2.1 참조).
DEFAULT_MIN_SCORE = 80

# docs/00_project_overview.md "대본 설계" — 대본 톤 7종.
SCRIPT_TONES = ["불편해결", "우월감", "보상", "생활팁", "사실형", "생활형", "실리적"]

DEFAULT_TARGET_PERSONA = "40-50대 여성"

# docs/03_interfaces.md 4번 — educational_note에 절대 포함되면 안 되는 진단/치료/효능보장 암시 표현.
# 목록은 초기값이며 운영하면서 보강한다.
EDUCATION_FORBIDDEN_KEYWORDS = [
    "치료됩니다", "완치", "100% 예방", "완치됩니다", "예방됩니다",
    "질병을 낫게", "효과가 보장", "부작용 없이 치료", "즉시 완쾌",
]
