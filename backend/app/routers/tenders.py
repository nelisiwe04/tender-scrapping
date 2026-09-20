from fastapi import APIRouter, HTTPException, Query
from datetime import datetime
from typing import Optional

router = APIRouter(prefix="/tenders", tags=["tenders"])


def _db(request):
    from ..main import db
    if db is None:
        raise HTTPException(500, "DB not initialized")
    return db


@router.get("")
async def list_tenders(
    request=None,
    status: Optional[str] = Query(None, description="Open, Closed, Awarded"),
    province: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    organisation: Optional[str] = Query(None),
    closing_before: Optional[str] = Query(None, description="ISO date, e.g. 2026-12-31"),
    closing_after: Optional[str] = Query(None, description="ISO date"),
    keyword: Optional[str] = Query(None, description="Search in title / description / number / org"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    db = _db(request)
    rows = await db.list_tenders(
        status=status, province=province, category=category,
        organisation=organisation,
        closing_before=closing_before, closing_after=closing_after,
        keyword=keyword, limit=limit, offset=offset,
    )
    total = await db.count_tenders(
        status=status, province=province, category=category,
        organisation=organisation,
        closing_before=closing_before, closing_after=closing_after,
        keyword=keyword,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "count": len(rows),
        "tenders": rows,
    }


@router.get("/search")
async def search_tenders(
    q: str = Query(..., min_length=1, description="Search keyword"),
    limit: int = Query(50, ge=1, le=200),
):
    db = _db(None)
    rows = await db.list_tenders(keyword=q, limit=limit)
    return {"query": q, "count": len(rows), "tenders": rows}


@router.get("/{tender_number}")
async def get_tender(tender_number: str):
    db = _db(None)
    detail = await db.get_tender_detail(tender_number)
    if detail is None:
        raise HTTPException(404, f"Tender {tender_number} not found")
    return detail