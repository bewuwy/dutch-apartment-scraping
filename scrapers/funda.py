"""Funda rental scraper leveraging pyfunda."""

import sys
import os
import logging
from typing import List

# Ensure external pyfunda package directory is on sys.path
PYFUNDA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "external_tools", "pyfunda")
)
if PYFUNDA_DIR not in sys.path:
    sys.path.insert(0, PYFUNDA_DIR)

from models import Listing
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class FundaScraper(BaseScraper):
    def scrape(self) -> List[Listing]:
        location = self.search_criteria.get("location", "amsterdam").lower()
        max_rent = self.search_criteria.get("max_rent_eur", 2000)
        min_size = self.search_criteria.get("min_size_m2", 0)
        min_bedrooms = self.search_criteria.get("min_bedrooms", 0)

        listings: List[Listing] = []
        logger.info("[Funda] Searching rental listings for %s (max €%d)...", location, max_rent)

        try:
            from funda import Funda
            with Funda() as client:
                search_kwargs = {
                    "category": "rent",
                    "max_price": max_rent,
                }
                if min_size > 0:
                    search_kwargs["min_area"] = min_size
                if min_bedrooms > 0:
                    search_kwargs["min_bedrooms"] = min_bedrooms

                results = client.search(location, **search_kwargs)
                logger.info("[Funda] Retrieved %d listings.", len(results))

                for item in results:
                    price_val = item.price.amount if item.price else None
                    if price_val and price_val > max_rent:
                        continue

                    raw_data = item.to_dict() if hasattr(item, "to_dict") else {}
                    interior = item.characteristic("Inrichting") if hasattr(item, "characteristic") else None
                    full_url = item.url or (f"https://www.funda.nl{item.detail_url}" if getattr(item, "detail_url", None) else "")

                    title = item.title or f"Woning in {item.city or location.capitalize()}"
                    address = getattr(item.address, "street_name", None) or title
                    city_name = item.city or location.capitalize()

                    status_str = getattr(item, "status", "") or ""
                    is_available = "verhuurd" not in status_str.lower()
                    pub_date = getattr(item, "publication_date", None)
                    if not pub_date and hasattr(item, "characteristic"):
                        pub_date = item.characteristic("Aangeboden sinds")

                    listing = Listing(
                        id=f"funda_{item.id}",
                        title=title,
                        url=full_url,
                        price=price_val,
                        city=city_name,
                        address=address,
                        postal_code=item.postcode,
                        neighborhood=getattr(item.address, "neighbourhood", None),
                        source="funda",
                        property_type=getattr(item.property_details, "object_type", "apartment") or "apartment",
                        living_area_m2=float(item.living_area) if item.living_area else None,
                        rooms=item.rooms_count,
                        interior=interior,
                        description=item.description or "",
                        is_available=is_available,
                        posted_at=str(pub_date) if pub_date else None,
                        raw_data=raw_data,
                    )
                    listings.append(listing)

        except Exception as e:
            logger.warning("[Funda] Scraper encountered an error (bot protection or network): %s", e)

        return listings
