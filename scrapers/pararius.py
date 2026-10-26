"""Pararius scraper leveraging external_tools/pararius-scraper/utils.py with Playwright."""

import sys
import os
import logging
from typing import List, Dict, Any
from urllib.parse import urljoin

from models import Listing
from scrapers.base import BaseScraper

# Add external tool to sys.path end for its internal imports without shadowing root modules
PARARIUS_TOOL_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "external_tools", "pararius-scraper")
)
if PARARIUS_TOOL_DIR not in sys.path:
    sys.path.append(PARARIUS_TOOL_DIR)

from utils import parse_property_cards, parse_price, parse_area, parse_rooms  # cloned tool logic

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class ParariusScraper(BaseScraper):
    def scrape(self) -> List[Listing]:
        from playwright.sync_api import sync_playwright

        max_rent = self.search_criteria.get("max_rent_eur", 2000)
        location = self.search_criteria.get("location", "leiden").lower()

        # Build Pararius search URL (Dutch rental portal)
        search_url = f"https://www.pararius.nl/huurwoningen/{location}/0-{max_rent}"
        logger.info(f"[Pararius] Searching {search_url}...")

        listings: List[Listing] = []

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = browser.new_context(user_agent=USER_AGENT)
                page = context.new_page()

                # Go to search results
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)

                html = page.content()
                # Use cloned tool's card parser
                raw_properties = parse_property_cards(html)
                logger.info(f"[Pararius] Parsed {len(raw_properties)} property cards.")

                for p_data in raw_properties:
                    price = p_data.get("price")
                    if price is not None and price > max_rent:
                        continue

                    url = p_data.get("url", "")
                    title = p_data.get("street_address")
                    if not title or title == "Pararius Listing":
                        # Infer street name from URL: /appartement-te-huur/leiden/4b00d8e1/sigmaplantsoen
                        parts = url.rstrip("/").split("/")
                        street_slug = parts[-1] if len(parts) > 0 else "Property"
                        title = f"Appartement {street_slug.replace('-', ' ').title()}"
                    prop_id = p_data.get("listing_id") or url.split("/")[-1]

                    # Infer property type from url
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

                    listing = Listing(
                        id=f"pararius_{prop_id}",
                        title=title,
                        url=url,
                        price=price,
                        city=p_data.get("city", "Leiden"),
                        address=p_data.get("street_address"),
                        postal_code=p_data.get("postal_code"),
                        neighborhood=p_data.get("neighborhood"),
                        source="pararius",
                        property_type=ptype,
                        living_area_m2=p_data.get("living_area"),
                        rooms=p_data.get("rooms"),
                        interior=p_data.get("interior"),
                        description="",
                        is_available=True,
                        raw_data=p_data,
                    )
                    listings.append(listing)

                browser.close()
        except Exception as e:
            logger.error(f"[Pararius] Scraper encountered an error: {e}")

        return listings
