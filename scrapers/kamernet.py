"""Kamernet scraper leveraging Next.js page data extraction and detail enrichment."""

import sys
import os
import logging
from typing import List

KAMERNET_TOOL_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "external_tools", "kamernet-radar")
)
if KAMERNET_TOOL_DIR not in sys.path:
    sys.path.insert(0, KAMERNET_TOOL_DIR)

from radar.fetch import make_session, _extract_next_data, fetch_listing_details
from models import Listing
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
BASE_URL = "https://kamernet.nl"


class KamernetScraper(BaseScraper):
    def scrape(self) -> List[Listing]:
        max_rent = self.search_criteria.get("max_rent_eur", 2000)
        min_size = self.search_criteria.get("min_size_m2", 0)
        session = make_session(USER_AGENT)
        listings: List[Listing] = []
        seen_ids = set()

        loc = self.search_criteria.get("location", "amsterdam").lower()
        slugs = [f"appartement-{loc}", f"studio-{loc}"]

        for slug in slugs:
            url = f"{BASE_URL}/huren/{slug}"
            logger.info("[Kamernet] Fetching %s...", url)
            try:
                resp = session.get(url, timeout=20)
                if resp.status_code != 200:
                    logger.warning("[Kamernet] HTTP %d for %s", resp.status_code, url)
                    continue

                data = _extract_next_data(resp.text)
                if not data:
                    continue

                target = data.get("props", {}).get("pageProps", {}).get("targetPageProps", {})
                raw_listings = target.get("findListingsResponse", {}).get("listings", []) or []

                for item in raw_listings:
                    listing_id = str(item.get("listingId") or "")
                    if not listing_id or listing_id in seen_ids:
                        continue
                    seen_ids.add(listing_id)

                    price = item.get("totalRentalPrice") or item.get("rent")
                    if price and price > max_rent:
                        continue

                    surface = float(item["surfaceArea"]) if item.get("surfaceArea") else None
                    if min_size and surface and surface < min_size:
                        continue

                    # Enrich qualifying listing with detail page description and rules
                    try:
                        enriched = fetch_listing_details(item, session)
                    except Exception as exc:
                        logger.debug("[Kamernet] Detail enrichment skipped for %s: %s", listing_id, exc)
                        enriched = item

                    city_slug = enriched.get("citySlug") or loc
                    street_slug = enriched.get("streetSlug") or ""
                    detail_url = f"{BASE_URL}/huren/{city_slug}/{street_slug}/{listing_id}" if street_slug else url

                    title = enriched.get("detailed_title") or enriched.get("title") or f"{enriched.get('listingType', 'Property')} in {city_slug.capitalize()}"
                    description = enriched.get("detailed_description") or enriched.get("description") or ""

                    type_map = {1: "room", 2: "apartment", 3: "studio", 4: "anti-squat"}
                    raw_type = enriched.get("listingType")
                    if isinstance(raw_type, int):
                        ptype = type_map.get(raw_type, "apartment")
                    elif isinstance(raw_type, str):
                        ptype = raw_type.lower()
                    else:
                        ptype = "apartment"

                    rooms = enriched.get("num_rooms") or enriched.get("numberOfRooms")
                    postal_code = enriched.get("postal_code") or enriched.get("postalCode")
                    address = enriched.get("street") or enriched.get("streetName")
                    publish_date = enriched.get("publish_date") or enriched.get("create_date") or item.get("publish_date")

                    listing = Listing(
                        id=f"kamernet_{listing_id}",
                        title=title,
                        url=detail_url,
                        price=price,
                        city=city_slug.capitalize(),
                        address=address,
                        postal_code=postal_code,
                        neighborhood=enriched.get("neighborhood"),
                        source="kamernet",
                        property_type=ptype,
                        living_area_m2=surface,
                        rooms=rooms,
                        interior=enriched.get("furnishType"),
                        description=description,
                        is_available=True,
                        posted_at=publish_date,
                        raw_data=enriched,
                    )
                    listings.append(listing)

            except Exception as e:
                logger.error("[Kamernet] Error scraping %s: %s", slug, e)

        logger.info("[Kamernet] Found %d matching listings.", len(listings))
        return listings
