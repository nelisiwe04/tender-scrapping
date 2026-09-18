from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel

@dataclass
class Tender:
    # Table listing fields (already scraped)
    category: Optional[str] = None
    description: Optional[str] = None
    e_submission: Optional[str] = None
    advertised_date: Optional[str] = None
    closing_date: Optional[str] = None
    detail_url: Optional[str] = None
    raw_cells: list[str] = field(default_factory=list)

    # Detail page fields (to be scraped)
    tender_number: Optional[str] = None
    organ_of_state: Optional[str] = None
    tender_type: Optional[str] = None
    province: Optional[str] = None
    location: Optional[str] = None
    special_conditions: Optional[str] = None
    published_date: Optional[str] = None

    # Enquiries
    contact_person: Optional[str] = None
    contact_email: Optional[str] = None
    contact_telephone: Optional[str] = None
    contact_fax: Optional[str] = None

    # Briefing session
    has_briefing: bool = False
    is_compulsory: bool = False
    briefing_datetime: Optional[str] = None
    briefing_venue: Optional[str] = None

    # Documents
    documents: list[dict] = field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
