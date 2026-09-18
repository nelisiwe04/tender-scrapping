from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from .config import get_settings
from .scraper import scrape_tenders, ScrapeError
from .database import TenderDB

settings = get_settings()
db: TenderDB | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db
    db = await TenderDB.connect()
    yield
    await db.close()


app = FastAPI(title="eTenders Scraper API", lifespan=lifespan)


@app.get("/scrape-and-save")
async def scrape_and_save(
    status: str = Query("current"),
    max_pages: int = Query(1, ge=1, le=settings.max_pages_hard_cap),
):
    if db is None:
        raise HTTPException(500, "DB not initialized")

    log_id = await db.start_log("etenders_portal")
    found = 0
    added = 0

    try:
        result = await scrape_tenders(
            status=status, max_pages=max_pages, fetch_details=True
        )
        found = len(result.tenders)

        for tender in result.tenders:
            if await db.save_tender(tender, source="etenders_portal"):
                added += 1

        await db.complete_log(log_id, found, added, "Completed")
        return {"log_id": log_id, "found": found, "added": added}

    except Exception as exc:
        await db.complete_log(log_id, found, added, "Failed", str(exc))
        raise HTTPException(500, str(exc))