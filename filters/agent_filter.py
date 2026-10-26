"""Listing filter for the Dutch rental housing market.

Evaluates listings against search criteria, budget limits, and common Dutch rental
nuances (registration, pet policies, guarantors, independent vs shared housing).
"""

import re
import logging
from typing import Dict, Any, List
from models import Listing, FilterEvaluation

logger = logging.getLogger(__name__)


class RentalFilter:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.tenant_profile = config.get("tenant_profile", {})
        self.search_criteria = config.get("search_criteria", {})
        self.filter_rules = config.get("filter_rules", {})

        self.max_rent = self.search_criteria.get("max_rent_eur", 2000)
        self.min_size_m2 = self.search_criteria.get("min_size_m2", 0)
        self.min_bedrooms = self.search_criteria.get("min_bedrooms", 0)

        # Policy preferences
        self.reject_roommates = self.filter_rules.get("reject_roommates_or_shared_housing", True)
        self.reject_single_only = self.filter_rules.get("reject_single_occupant_only", True)
        self.reject_explicit_no_pets = self.filter_rules.get("reject_explicit_no_pets", False)
        self.require_registration = self.filter_rules.get("require_registration_possible", True)
        self.reject_no_students = self.filter_rules.get("reject_no_students_unless_guarantors_allowed", True)

    def evaluate(self, listing: Listing) -> FilterEvaluation:
        text = f"{listing.title} {listing.description} {str(listing.raw_data)}".lower()

        reasons: List[str] = []
        flags: List[str] = []
        status = "MATCH"
        score = 80

        # 1. Availability & Price
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

        # 2. Minimum Area & Bedrooms (if configured)
        if self.min_size_m2 and listing.living_area_m2 and listing.living_area_m2 < self.min_size_m2:
            return FilterEvaluation(
                listing=listing,
                status="REJECTED",
                score=0,
                reasons=[f"Living area {listing.living_area_m2} m² is below minimum {self.min_size_m2} m²"],
            )

        if self.min_bedrooms and listing.rooms and listing.rooms < self.min_bedrooms:
            flags.append(f"Room count ({listing.rooms}) below preferred minimum ({self.min_bedrooms})")
            score -= 10

        # 3. Independent vs Shared Housing
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
                if self.reject_roommates:
                    reasons.append("Shared facilities or roommates detected")
                    status = "REJECTED"
                    score = 10
                else:
                    flags.append("Shared facilities or roommates mentioned")
                break

        if listing.property_type == "room" and is_private_no_roommates:
            if "zelfstandig" not in text and "studio" not in text:
                flags.append("Property type is 'room' - verify if facilities are private or shared")
                if status == "MATCH":
                    status = "NEEDS_REVIEW"
                score -= 20

        # 4. Couples vs Single Occupancy
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
                if self.reject_single_only:
                    reasons.append("Single occupant only (prohibits couples)")
                    status = "REJECTED"
                    score = 0
                else:
                    flags.append("Single occupant only specified")
                break

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

        # 5. Pet Policy
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
                if self.reject_explicit_no_pets:
                    reasons.append("Listing explicitly prohibits pets (geen huisdieren)")
                    status = "REJECTED"
                    score = 0
                else:
                    flags.append("Specifies no pets (negotiation may be required)")
                    score -= 10
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
            flags.append("Pets not mentioned (negotiable per standard practice)")

        # 6. Students & Guarantors
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
            flags.append("Allows guarantors (garantstellers toegestaan)")
            score += 15

        if has_no_students:
            if has_guarantor:
                flags.append("Restricts students without guarantor, but mentions guarantors accepted")
                if status == "MATCH":
                    status = "NEEDS_REVIEW"
            elif self.reject_no_students:
                flags.append("States 'no students' with no guarantor policy mentioned")
                if status == "MATCH":
                    status = "NEEDS_REVIEW"
                score -= 15

        income_match = re.search(r"(\d+)\s*x\s*(de\s*)?(bruto\s*)?huur", text)
        if income_match:
            flags.append(f"Income requirement: {income_match.group(0)}")

        # 7. Municipal Registration (Gemeente Inschrijving)
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
                if self.require_registration:
                    reasons.append("Municipal registration not possible (geen inschrijving)")
                    status = "REJECTED"
                    score = 0
                else:
                    flags.append("Municipal registration not possible")
                    score -= 20
                break

        if re.search(r"inschrijving\s*mogelijk", text) or re.search(r"registration\s*possible", text):
            registration_possible = True
            flags.append("Municipal registration confirmed")
            score += 5

        # 8. Check explicit portal metadata (Kamernet, Pararius, Funda)
        meta_reg = listing.raw_data.get("registration_allowed")
        if meta_reg is None:
            meta_reg = listing.raw_data.get("isRegistrationAllowed")
        if meta_reg is False:
            registration_possible = False
            if self.require_registration:
                reasons.append("Portal metadata confirms registration is not allowed")
                status = "REJECTED"
                score = 0
            else:
                flags.append("Registration not permitted per metadata")
        elif meta_reg is True and registration_possible is None:
            registration_possible = True
            flags.append("Registration permitted per specifications")
            score += 5

        meta_pets = listing.raw_data.get("pets_allowed")
        if meta_pets is None:
            meta_pets = listing.raw_data.get("candidatePetsAllowed")
        if meta_pets is False:
            pets_allowed = False
            if self.reject_explicit_no_pets:
                reasons.append("Portal metadata confirms pets not allowed")
                status = "REJECTED"
                score = 0
            else:
                flags.append("Pets not allowed per metadata")
                score -= 10
        elif meta_pets is True and pets_allowed is None:
            pets_allowed = True
            flags.append("Pets allowed per specifications")
            score += 10

        suitable_persons = listing.raw_data.get("suitable_for_persons")
        if suitable_persons is not None and couples_allowed is None:
            if suitable_persons == 1:
                couples_allowed = False
                if self.reject_single_only:
                    reasons.append("Portal specifications restrict occupancy to 1 person")
                    status = "REJECTED"
                    score = 0
                else:
                    flags.append("Single occupant only per metadata")
            elif suitable_persons >= 2:
                couples_allowed = True
                flags.append(f"Suitable for {suitable_persons} occupants")
                score += 10


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
        status_order = {"MATCH": 0, "NEEDS_REVIEW": 1, "REJECTED": 2}
        evaluations.sort(key=lambda e: (status_order.get(e.status, 3), -e.score))
        return evaluations


# Alias for backwards compatibility
AgentFilter = RentalFilter
