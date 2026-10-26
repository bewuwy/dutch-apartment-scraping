"""Two-phase intelligent filter for the Dutch housing market.

Performs hard elimination only on unambiguous disqualifiers, and leaves nuanced
criteria flagged for agent review so no potential apartments are missed.
"""

import re
import logging
from typing import Dict, Any, List
from models import Listing, FilterEvaluation

logger = logging.getLogger(__name__)


class AgentFilter:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.tenant_profile = config.get("tenant_profile", {})
        self.search_criteria = config.get("search_criteria", {})
        self.filter_rules = config.get("filter_rules", {})
        self.max_rent = self.search_criteria.get("max_rent_eur", 2000)

    def evaluate(self, listing: Listing) -> FilterEvaluation:
        # Combine title, description, and raw card text for evaluation
        text = f"{listing.title} {listing.description} {str(listing.raw_data)}".lower()

        reasons: List[str] = []
        flags: List[str] = []
        status = "MATCH"
        score = 80

        # --- 1. HARD REJECTION: PRICE & AVAILABILITY ---
        if not listing.is_available:
            return FilterEvaluation(
                listing=listing,
                status="REJECTED",
                score=0,
                reasons=["Listing is already rented out (Verhuurd)"],
            )

        if listing.price and listing.price > self.max_rent:
            return FilterEvaluation(
                listing=listing,
                status="REJECTED",
                score=0,
                reasons=[f"Price €{listing.price} exceeds maximum budget €{self.max_rent}"],
            )

        # --- 2. PRIVATE VS ROOMMATES / SHARED HOUSING ---
        # The user wants private accommodation (independent studio/apartment), NO roommates
        is_private_no_roommates = True
        shared_roommate_patterns = [
            r"gedeelde\s*(keuken|badkamer|toilet|woonkamer|voorzieningen)",
            r"met\s*(\d+|medebewoners|huisgenoten)\s*huisgenoten",
            r"studentenhuis\b",
            r"kamer\s*in\s*een\s*(studentenhuis|woongroep)",
            r"shared\s*(kitchen|bathroom|facilities|living\s*room|flat)",
            r"roommates\b",
            r"flatmates\b",
        ]
        for pat in shared_roommate_patterns:
            if re.search(pat, text):
                is_private_no_roommates = False
                reasons.append("Listing appears to have shared facilities or roommates")
                status = "REJECTED"
                score = 10
                break

        # Check property type: "room" is often shared unless specified as self-contained
        if listing.property_type == "room" and is_private_no_roommates:
            if "zelfstandig" not in text and "studio" not in text:
                flags.append("Property type is 'room' - verify if facilities are private or shared")
                status = "NEEDS_REVIEW"
                score -= 20

        # --- 3. COUPLES / SINGLE OCCUPANT RULES ---
        # Reject if strictly single occupant only
        couples_allowed = None
        single_only_patterns = [
            r"maximaal\s*1\s*persoon",
            r"uitsluitend\s*voor\s*1\s*persoon",
            r"geschikt\s*voor\s*max(\.|\s)1\s*persoon",
            r"niet\s*geschikt\s*voor\s*stellen",
            r"geen\s*stellen",
            r"single\s*occupancy\s*only",
            r"maximum\s*1\s*person",
            r"not\s*suitable\s*for\s*couples",
        ]
        for pat in single_only_patterns:
            if re.search(pat, text):
                couples_allowed = False
                reasons.append("Explicitly single occupant only / prohibits couples")
                status = "REJECTED"
                score = 0
                break

        # Check positive indicators for couples
        couple_positive = [
            r"geschikt\s*voor\s*(een\s*)?(stel|koppel|2\s*personen)",
            r"suitable\s*for\s*(a\s*)?(couple|2\s*persons)",
            r"stellen\s*toegestaan",
        ]
        for pat in couple_positive:
            if re.search(pat, text):
                couples_allowed = True
                score += 10
                flags.append("Explicitly permits couples")
                break

        # --- 4. PET POLICY ---
        pets_allowed = None
        no_pets_patterns = [
            r"geen\s*huisdieren(\s*toegestaan)?",
            r"huisdieren\s*(zijn\s*)?niet\s*toegestaan",
            r"no\s*pets(\s*allowed)?",
            r"pets\s*not\s*allowed",
            r"pets\s*prohibited",
        ]
        for pat in no_pets_patterns:
            if re.search(pat, text):
                pets_allowed = False
                reasons.append("Listing explicitly prohibits pets (geen huisdieren)")
                status = "REJECTED"
                score = 0
                break

        pets_positive = [
            r"huisdieren\s*(in\s*overleg|toegestaan)",
            r"pets\s*(allowed|considered|in\s*consultation)",
        ]
        for pat in pets_positive:
            if re.search(pat, text):
                pets_allowed = True
                score += 10
                flags.append("Explicitly permits pets or open in consultation")
                break

        if pets_allowed is None and status != "REJECTED":
            flags.append("Pets not mentioned (assumed negotiable per Dutch market rules)")

        # --- 5. STUDENTS & GUARANTORS ---
        guarantors_allowed = None
        no_students_patterns = [
            r"geen\s*studenten",
            r"niet\s*geschikt\s*voor\s*studenten",
            r"no\s*students",
            r"not\s*suitable\s*for\s*students",
        ]
        guarantor_positive = [
            r"garantstell(er|ing)\s*(toegestaan|mogelijk|akkoord)",
            r"guarantor(s)?\s*(accepted|allowed)",
            r"borgtocht\s*mogelijk",
        ]

        has_no_students = any(re.search(pat, text) for pat in no_students_patterns)
        has_guarantor = any(re.search(pat, text) for pat in guarantor_positive)

        if has_guarantor:
            guarantors_allowed = True
            flags.append("Explicitly allows guarantors (garantstellers toegestaan)")
            score += 15

        if has_no_students:
            if has_guarantor:
                flags.append("Says 'no students' but allows guarantors - potential fit")
                if status == "MATCH":
                    status = "NEEDS_REVIEW"
            else:
                flags.append("Says 'no students'; guarantor policy unstated - needs agent/landlord check")
                if status == "MATCH":
                    status = "NEEDS_REVIEW"
                score -= 15

        # Income multiplier warnings (e.g. 3x or 4x gross salary required)
        income_match = re.search(r"(\d+)\s*x\s*(de\s*)?(bruto\s*)?huur", text)
        if income_match:
            flags.append(f"Income requirement mentioned: {income_match.group(0)} (check if EU guarantor accepted)")

        # --- 6. REGISTRATION (GEMEENTE INSCHRIJVING) ---
        registration_possible = None
        no_reg_patterns = [
            r"geen\s*inschrijving(\s*mogelijk)?",
            r"inschrijving\s*(is\s*)?niet\s*mogelijk",
            r"no\s*registration",
            r"registration\s*not\s*possible",
        ]
        for pat in no_reg_patterns:
            if re.search(pat, text):
                registration_possible = False
                reasons.append("Explicitly states no municipality registration possible")
                status = "REJECTED"
                score = 0
                break

        if re.search(r"inschrijving\s*mogelijk", text) or re.search(r"registration\s*possible", text):
            registration_possible = True
            flags.append("Registration explicitly confirmed")
            score += 5

        # Check Kamernet raw metadata if available
        if listing.source == "kamernet" and listing.raw_data:
            k_reg = listing.raw_data.get("isRegistrationAllowed")
            if k_reg is False:
                registration_possible = False
                reasons.append("Kamernet metadata: registration is prohibited")
                status = "REJECTED"
                score = 0

            k_pets = listing.raw_data.get("candidatePetsAllowed")
            if k_pets is False:
                pets_allowed = False
                reasons.append("Kamernet metadata: pets not allowed")
                status = "REJECTED"
                score = 0

        # Construct final evaluation
        return FilterEvaluation(
            listing=listing,
            status=status,
            score=max(0, min(score, 100)),
            reasons=reasons,
            flags=flags,
            couples_allowed=couples_allowed,
            pets_allowed=pets_allowed,
            guarantors_allowed=guarantors_allowed,
            registration_possible=registration_possible,
            is_private_no_roommates=is_private_no_roommates,
        )

    def filter_all(self, listings: List[Listing]) -> List[FilterEvaluation]:
        evaluations = [self.evaluate(l) for l in listings]
        # Sort by match priority: MATCH first (descending score), then NEEDS_REVIEW, then REJECTED
        status_order = {"MATCH": 0, "NEEDS_REVIEW": 1, "REJECTED": 2}
        evaluations.sort(key=lambda e: (status_order.get(e.status, 3), -e.score))
        return evaluations
