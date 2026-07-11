from functools import lru_cache

from supabase import Client, create_client

from app.config import SUPABASE_SERVICE_KEY, SUPABASE_URL


@lru_cache
def get_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_SERVICE_KEY가 설정되지 않았습니다. .env를 확인하세요."
        )
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
