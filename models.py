"""Unified data models for Dutch apartment search."""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any


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
    source: str = ""  # pararius, kamernet, 123wonen, nederwoon, tweelwonen, livingtoday
    property_type: Optional[str] = None  # apartment, studio, room, house
    living_area_m2: Optional[float] = None
    rooms: Optional[int] = None
    interior: Optional[str] = None  # gestoffeerd, gemeubileerd, kaal
    description: str = ""
    is_available: bool = True
    raw_data: Dict[str, Any] = field(default_factory=dict)

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

    # AI Verification metadata (populated when run by an AI Agent)
    ai_checked: bool = False
    ai_verdict: Optional[str] = None  # "STRONG_MATCH", "POTENTIAL_MATCH", "DISQUALIFIED"
    ai_score: Optional[int] = None    # 0 to 100
    ai_rationale: Optional[str] = None
    ai_pros: List[str] = field(default_factory=list)
    ai_cons: List[str] = field(default_factory=list)

    # Notification tracking
    alerted_standalone: bool = False
    alerted_ai: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["listing"] = self.listing.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FilterEvaluation":
        listing_data = data.pop("listing")
        listing = Listing(**listing_data)
        return cls(listing=listing, **data)
