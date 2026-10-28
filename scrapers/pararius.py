"""Pararius scraper leveraging external_tools/pararius-scraper with detail enrichment."""

import sys
import os
import logging
from typing import List

from models import Listing
from scrapers.base import BaseScraper

PARARIUS_TOOL_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "external_tools", "pararius-scraper")
)
if PARARIUS_TOOL_DIR not in sys.path:
    sys.path.append(PARARIUS_TOOL_DIR)

from utils import parse_property_cards, parse_detail_page

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class ParariusScraper(BaseScraper):
    def scrape(self) -> List[Listing]:
        from playwright.sync_api import sync_playwright

        max_rent = self.search_criteria.get("max_rent_eur", 2000)
        min_size = self.search_criteria.get("min_size_m2", 0)
        location = self.search_criteria.get("location", "amsterdam").lower()

        search_url = f"https://www.pararius.nl/huurwoningen/{location}/0-{max_rent}"
        logger.info("[Pararius] Searching %s...", search_url)

        listings: List[Listing] = []

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = browser.new_context(user_agent=USER_AGENT)
                page = context.new_page()

                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)

                html = page.content()
                raw_properties = parse_property_cards(html)
                logger.info("[Pararius] Parsed %d property cards.", len(raw_properties))

                # Filter down to candidates matching budget and minimum area
                candidates = []
                for p_data in raw_properties:
                    price = p_data.get("price")
                    if price is not None and price > max_rent:
                        continue
                    area = p_data.get("living_area")
                    if min_size and area and area < min_size:
                        continue
                    candidates.append(p_data)

                # Enrich candidate properties with descriptions & details (up to 12 per run)
                max_enrich = 12
                for idx, p_data in enumerate(candidates):
                    url = p_data.get("url", "")
                    description = ""
                    if idx < max_enrich and url:
                        try:
                            logger.debug("[Pararius] Fetching details for %s", url)
                            page.goto(url, wait_until="domcontentloaded", timeout=15000)
                            page.wait_for_timeout(1000)
                            content = page.content()
                            details = parse_detail_page(content)
                            description = details.get("description", "")
                            from bs4 import BeautifulSoup
                            soup = BeautifulSoup(content, "lxml")
                            title_elem = soup.select_one(".listing-detail-summary__title, h1.listing-detail-summary__title, .page-title")
                            if title_elem and not any(w in title_elem.get_text().lower() for w in ("pararius", "listing")):
                                details["title"] = title_elem.get_text(strip=True)
                            elif "title" in details and any(w in str(details["title"]).lower() for w in ("pararius", "listing")):
                                del details["title"]
                            # Merge details into p_data
                            p_data.update(details)
                        except Exception as e:
                            logger.debug("[Pararius] Could not fetch detail page for %s: %s", url, e)

                    prop_id = p_data.get("listing_id") or (url.split("/")[-1] if url else f"pararius_{idx}")

                    url_lower = url.lower()
                    if "appartement" in url_lower:
                        ptype = "apartment"
                    elif "studio" in url_lower:
                        ptype = "studio"
                    elif "kamer" in url_lower:
                        ptype = "room"
                    elif "woonhuis" in url_lower or "huis" in url_lower:
                        ptype = "house"
                    else:
                        ptype = "apartment"

                    title = p_data.get("title") or p_data.get("street_address")
                    if not title or any(w in title.lower() for w in ("pararius", "listing", "huurwoningen")):
                        parts = url.rstrip("/").split("/")
                        street_slug = parts[-1] if parts else "Property"
                        clean_street = street_slug.replace('-', ' ').title()
                        type_prefix = "Appartement" if ptype == "apartment" else ptype.capitalize()
                        title = f"{type_prefix} {clean_street}"

                    address = p_data.get("street_address")
                    if not address or any(w in address.lower() for w in ("pararius", "listing")):
                        parts = url.rstrip("/").split("/")
                        street_slug = parts[-1] if parts else ""
                        address = street_slug.replace('-', ' ').title() if street_slug else None

                    offered_since = p_data.get("offered_since") or p_data.get("date") or p_data.get("publish_date")

                    listing = Listing(
                        id=f"pararius_{prop_id}",
                        title=title,
                        url=url,
                        price=p_data.get("price"),
                        city=p_data.get("city", location.capitalize()),
                        address=address,
                        postal_code=p_data.get("postal_code"),
                        neighborhood=p_data.get("neighborhood"),
                        source="pararius",
                        property_type=ptype,
                        living_area_m2=p_data.get("living_area"),
                        rooms=p_data.get("rooms"),
                        interior=p_data.get("interior"),
                        description=description,
                        is_available=True,
                        posted_at=offered_since,
                        raw_data=p_data,
                    )
                    listings.append(listing)

                browser.close()
        except Exception as e:
            logger.error("[Pararius] Scraper encountered an error: %s", e)

        return listings
