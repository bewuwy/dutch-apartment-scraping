"""Unified data models for Dutch apartment search."""

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

DUTCH_MONTHS = {
    "januari": 1, "jan": 1, "january": 1,
    "februari": 2, "feb": 2, "february": 2,
    "maart": 3, "mrt": 3, "march": 3,
    "april": 4, "apr": 4,
    "mei": 5, "may": 5,
    "juni": 6, "jun": 6, "june": 6,
    "juli": 7, "jul": 7, "july": 7,
    "augustus": 8, "aug": 8, "august": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "okt": 10, "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def calculate_posted_days_ago(date_val: Any) -> Optional[int]:
    """Calculate the number of days ago an advert was posted."""
    if not date_val:
        return None
    if isinstance(date_val, (int, float)):
        return max(0, int(date_val))

    s = str(date_val).strip().lower()

    if "vandaag" in s or "today" in s:
        return 0
    if "gisteren" in s or "yesterday" in s:
        return 1

    m_hours = re.search(r"(\d+)\s*(?:uur|hour|hours)", s)
    if m_hours:
        return 0

    m_days = re.search(r"(\d+)\s*(?:dag|dagen|day|days)", s)
    if m_days:
        return int(m_days.group(1))

    m_weeks = re.search(r"(\d+)\s*(?:week|weken|weeks)", s)
    if m_weeks:
        return int(m_weeks.group(1)) * 7

    m_months = re.search(r"(\d+)\s*(?:maand|maanden|month|months)", s)
    if m_months:
        return int(m_months.group(1)) * 30

    # Try ISO timestamp (e.g. 2026-10-21T14:04:37)
    try:
        iso_clean = s.replace("z", "+00:00")
        dt = datetime.fromisoformat(iso_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = now - dt
        return max(0, diff.days)
    except Exception:
        pass

    # Try DD-MM-YYYY or DD/MM/YYYY
    m_dmy = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", s)
    if m_dmy:
        try:
            day, month, year = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
            dt = datetime(year, month, day, tzinfo=timezone.utc)
            diff = datetime.now(timezone.utc) - dt
            return max(0, diff.days)
        except Exception:
            pass

    # Try "24 oktober 2026"
    for m_name, m_num in DUTCH_MONTHS.items():
        if m_name in s:
            m_dmy2 = re.search(rf"(\d{{1,2}})\s+{m_name}\s+(\d{{4}})", s)
            if m_dmy2:
                try:
                    day = int(m_dmy2.group(1))
                    year = int(m_dmy2.group(2))
                    dt = datetime(year, m_num, day, tzinfo=timezone.utc)
                    diff = datetime.now(timezone.utc) - dt
                    return max(0, diff.days)
                except Exception:
                    pass

    return None


@dataclass
class Listing:
    id: str
    title: str
    url: str
    price: Optional[int]
    city: str
    address: Optional[str] = None
    postal_code: Optional[str] = None
    neighborhood: Optional[str] = None
    source: str = ""  # pararius, kamernet, or local agency
    property_type: Optional[str] = None  # apartment, studio, room, house
    living_area_m2: Optional[float] = None
    rooms: Optional[int] = None
    interior: Optional[str] = None  # gestoffeerd, gemeubileerd, kaal
    description: str = ""
    is_available: bool = True
    posted_at: Optional[str] = None  # e.g. "2026-10-21T14:04:37" or relative text
    posted_days_ago: Optional[int] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.posted_days_ago is None and self.posted_at:
            self.posted_days_ago = calculate_posted_days_ago(self.posted_at)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FilterEvaluation:
    listing: Listing
    status: str  # "MATCH", "NEEDS_REVIEW", "REJECTED"
    score: int   # 0 to 100
    reasons: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    couples_allowed: Optional[bool] = None
    pets_allowed: Optional[bool] = None  # True, False, or None (unmentioned/negotiable)
    guarantors_allowed: Optional[bool] = None
    registration_possible: Optional[bool] = None
    is_private_no_roommates: Optional[bool] = None

    # Review metadata
    ai_checked: bool = False
    ai_verdict: Optional[str] = None  # "STRONG_MATCH", "POTENTIAL_MATCH", "DISQUALIFIED"
    ai_score: Optional[int] = None    # 0 to 100
    ai_rationale: Optional[str] = None
    ai_pros: List[str] = field(default_factory=list)
    ai_cons: List[str] = field(default_factory=list)

    # Notification tracking
    alerted: bool = False
    alerted_standalone: bool = False  # retained for backward compatibility
    alerted_ai: bool = False          # retained for backward compatibility

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FilterEvaluation":
        data_copy = dict(data)
        listing_data = data_copy.pop("listing")
        if isinstance(listing_data, dict):
            if "posted_at" not in listing_data:
                raw = listing_data.get("raw_data", {})
                listing_data["posted_at"] = (
                    raw.get("publish_date")
                    or raw.get("create_date")
                    or raw.get("offered_since")
                    or raw.get("publication_date")
                )
            listing = Listing(**listing_data)
        else:
            listing = listing_data
        data_copy["alerted"] = data_copy.get(
            "alerted",
            data_copy.get("alerted_standalone", False) or data_copy.get("alerted_ai", False),
        )
        return cls(listing=listing, **data_copy)
