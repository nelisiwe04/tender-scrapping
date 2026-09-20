from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .scraper import scrape_tenders, ScrapeError
from .database import TenderDB
from .auth import require_api_key
from .routers import tenders as tenders_router
from .routers import stats as stats_router
from .routers import scraping as scraping_router

settings = get_settings()
db: TenderDB | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db
    db = await TenderDB.connect()
    yield
    await db.close()


app = FastAPI(
    title="eTenders API",
    description="Scraper + read API for South Africa's National Treasury eTenders portal.",
    version="1.2.1",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Global exception handler ----------
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    import traceback
    print(f"\n[UNHANDLED] {request.method} {request.url.path}")
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={
            "error": type(exc).__name__,
            "message": str(exc),
            "path": request.url.path,
        },
    )


# ---------- Routers ----------
app.include_router(tenders_router.router)
app.include_router(stats_router.router)
app.include_router(scraping_router.router)


# ---------- Scrape-and-save ----------
@app.get(
    "/scrape-and-save",
    tags=["scraping"],
    dependencies=[Depends(require_api_key)],
)
async def scrape_and_save(
    status: str = Query("current"),
    max_pages: int = Query(1, ge=1, le=settings.max_pages_hard_cap),
):
    if db is None:
        raise HTTPException(500, "DB not initialized")

    log_id = await db.start_log("etenders_portal")
    found = 0
    added = 0
    updated = 0
    skipped = 0

    try:
        result = await scrape_tenders(
            status=status, max_pages=max_pages, fetch_details=True
        )
        found = len(result.tenders)

        for tender in result.tenders:
            status_str = await db.save_tender(tender, source="etenders_portal")
            if status_str == "new":
                added += 1
            elif status_str == "updated":
                updated += 1
            else:
                skipped += 1

        await db.complete_log(log_id, found, added, "Completed")
        return {
            "log_id": log_id,
            "found": found,
            "added": added,
            "updated": updated,
            "skipped": skipped,
        }

    except Exception as exc:
        try:
            await db.complete_log(log_id, found, added, "Failed", str(exc))
        except Exception as log_exc:
            print(f"[LOG ERROR] {log_exc}")
        raise


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}


@app.get("/", tags=["root"])
async def root():
    return {
        "message": "eTenders API",
        "docs": "/docs",
        "endpoints": {
            "list_tenders":    "GET /tenders",
            "search_tenders":  "GET /tenders/search?q=internet",
            "tender_detail":   "GET /tenders/{tender_number}",
            "stats":           "GET /stats",
            "deep_health":     "GET /health/deep",
            "scrape_only":     "POST /scrape  (X-API-Key required)",
            "scrape_and_save": "GET  /scrape-and-save  (X-API-Key required)",
            "scraping_logs":   "GET /scraping-logs",
            "log_detail":      "GET /scraping-logs/{id}",
        },
    }