import asyncpg                       
import os
from datetime import datetime
from typing import Optional

from .models import Tender

DB_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://tender_scrapping_agent:tender%40scrapping@129.151.181.87:5433/tender_scrapping_db",
)


def _parse_ts(value):
    """Best-effort parse of a date/time string from the portal."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    for fmt in (
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
        "%A, %d %B %Y - %H:%M", "%A, %d %B %Y",
        "%d/%m/%Y %H:%M", "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(value.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None


class TenderDB:
    def __init__(self, pool: asyncpg.Pool):          
        self.pool = pool

    @classmethod
    async def connect(cls) -> "TenderDB":
        pool = await asyncpg.create_pool(            
            DB_DSN, min_size=1, max_size=5
        )
        return cls(pool)

    async def close(self):
        await self.pool.close()

    # --------------------------------------------------------------
    # Logging
    # --------------------------------------------------------------
    async def start_log(self, source: str) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "CALL start_scraping_log($1, NULL)", source
            )
            return row["p_log_id"]

    async def complete_log(
        self,
        log_id: int,
        found: int,
        added: int,
        status: str,
        error: Optional[str] = None,
    ) -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "CALL complete_scraping_log($1, $2, $3, $4, $5, NULL)",
                log_id, found, added, status, error,
            )
            return row["p_success"]

    # --------------------------------------------------------------
    # Tender save
    # --------------------------------------------------------------
    async def save_tender(self, tender: Tender, source: str) -> bool:
        """Returns True if a NEW tender was inserted, False if updated."""
        if not tender.tender_number:
            return False

        async with self.pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM tenders WHERE tender_number = $1",
                tender.tender_number,
            )
            is_new = exists is None

            async with conn.transaction():
                # 1. Upsert main tender + contact + briefing
                row = await conn.fetchrow(
                    """
                    CALL upsert_full_tender(
                        $1, $2, $3, $4, $5, $6, $7, $8,
                        $9, $10, $11, $12, $13,
                        $14, $15, $16, $17,
                        $18, $19, $20, $21,
                        NULL
                    )
                    """,
                    tender.tender_number,
                    (tender.description or "")[:200],   # title fallback
                    tender.description,
                    tender.organ_of_state or "Unknown",
                    tender.category or "Uncategorised",
                    tender.tender_type,
                    tender.province,
                    tender.location,
                    _parse_ts(tender.published_date),
                    _parse_ts(tender.closing_date),
                    tender.special_conditions,
                    tender.detail_url,
                    source,
                    tender.contact_person,
                    tender.contact_email,
                    tender.contact_telephone,
                    tender.contact_fax,
                    tender.has_briefing,
                    tender.is_compulsory,
                    _parse_ts(tender.briefing_datetime),
                    tender.briefing_venue,
                )
                tender_id = row["p_tender_id"]

                # 2. Documents
                for doc in tender.documents:
                    try:
                        await conn.fetchrow(
                            "CALL add_tender_document($1, $2, $3, $4, NULL)",
                            tender_id,
                            doc["name"][:255],
                            doc.get("type"),
                            doc["url"],
                        )
                    except Exception as e:
                        print(f"[DB WARN] Doc insert failed for {doc['url']}: {e}")

                return is_new