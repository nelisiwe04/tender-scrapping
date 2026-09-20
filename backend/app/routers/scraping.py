from fastapi import APIRouter, HTTPException, Query
from ..scraper import scrape_tenders, ScrapeError
from ..config import get_settings

settings = get_settings()
router = APIRouter(tags=["scraping"])


@router.post("/scrape")
async def scrape_only(
    status: str = Query("current"),
    max_pages: int = Query(1, ge=1, le=settings.max_pages_hard_cap),
    keyword: str = Query(None),
):
    try:
        result = await scrape_tenders(
            status=status, max_pages=max_pages,
            keyword=keyword, fetch_details=True,
        )
        return {
            "status": status,
            "source_url": result.source_url,
            "pages_scraped": result.pages_scraped,
            "count": len(result.tenders),
            "tenders": [
                {
                    "tender_number": t.tender_number,
                    "title": t.description,
                    "category": t.category,
                    "closing_date": t.closing_date,
                    "documents": len(t.documents),
                }
                for t in result.tenders
            ],
        }
    except ScrapeError as exc:
        raise HTTPException(502, str(exc))


@router.get("/scraping-logs")
async def list_logs(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    from ..main import db
    if db is None:
        raise HTTPException(500, "DB not initialized")
    rows = await db.list_scraping_logs(limit=limit, offset=offset)
    return {"limit": limit, "offset": offset, "count": len(rows), "logs": rows}


@router.get("/scraping-logs/{log_id}")
async def get_log(log_id: int):
    from ..main import db
    if db is None:
        raise HTTPException(500, "DB not initialized")
    log = await db.get_scraping_log(log_id)
    if log is None:
        raise HTTPException(404, f"Log {log_id} not found")
    return log