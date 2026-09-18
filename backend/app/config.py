import os
from functools import lru_cache


class Settings:
    
    base_url: str = os.getenv("ETENDERS_BASE_URL", "https://www.etenders.gov.za")

    
    status_ids: dict[str, int] = {
        "current": 1,
        "awarded": 2,
        "cancelled": 3,
        "closed": 4,
    }

    
    table_wait_timeout_ms: int = int(os.getenv("ETENDERS_TABLE_TIMEOUT_MS", "20000"))

   
    max_pages_default: int = int(os.getenv("ETENDERS_MAX_PAGES_DEFAULT", "3"))
    max_pages_hard_cap: int = int(os.getenv("ETENDERS_MAX_PAGES_HARD_CAP", "20"))

    
    cache_ttl_seconds: int = int(os.getenv("ETENDERS_CACHE_TTL_SECONDS", "300"))

    user_agent: str = os.getenv(
        "ETENDERS_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
