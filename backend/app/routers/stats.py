from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["stats"])


@router.get("/stats")
async def get_stats():
    from ..main import db
    if db is None:
        raise HTTPException(500, "DB not initialized")
    return await db.get_dashboard_stats()


@router.get("/health/deep")
async def deep_health():
    from ..main import db
    result = {"status": "ok"}

    # DB check
    try:
        async with db.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        result["database"] = "connected"
    except Exception as e:
        result["database"] = f"error: {e}"
        result["status"] = "degraded"

    # Chromium check
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            await browser.close()
        result["chromium"] = "available"
    except Exception as e:
        result["chromium"] = f"error: {e}"
        result["status"] = "degraded"

    return result