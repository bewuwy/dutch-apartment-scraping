"""Main orchestrator for the Dutch apartment hunting scraper and filter."""

import os
import sys
import json
import logging
import argparse
from typing import List, Dict, Any, Tuple
from pathlib import Path
from dotenv import load_dotenv

# Ensure workspace root is in python path
WORKSPACE_ROOT = os.path.dirname(os.path.abspath(__file__))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from models import Listing, FilterEvaluation
from scrapers.base import BaseScraper
from scrapers.pararius import ParariusScraper
from scrapers.kamernet import KamernetScraper
from filters.agent_filter import RentalFilter
from notifications.telegram import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dutch-apartment-hunter")


def load_config(config_path: str = None) -> Dict[str, Any]:
    if config_path and Path(config_path).exists():
        target = Path(config_path)
    elif os.environ.get("HOUSING_CONFIG") and Path(os.environ["HOUSING_CONFIG"]).exists():
        target = Path(os.environ["HOUSING_CONFIG"])
    elif Path("config.json").exists():
        target = Path("config.json")
    elif Path("config.example.json").exists():
        target = Path("config.example.json")
    else:
        raise FileNotFoundError("No config file found (checked config.json, config.example.json).")

    logger.info("Using configuration file: %s", target.name)
    with open(target, "r", encoding="utf-8") as f:
        return json.load(f)


def load_all_scrapers(config: Dict[str, Any]) -> List[Tuple[str, BaseScraper]]:
    """Load core nationwide scrapers and auto-discover any local agency scrapers."""
    import pkgutil
    import importlib
    import scrapers as scrapers_pkg

    scrapers: List[Tuple[str, BaseScraper]] = [
        ("Pararius", ParariusScraper(config)),
        ("Kamernet", KamernetScraper(config)),
    ]

    # Auto-discover any additional custom or local agency scrapers in scrapers/
    for _, module_name, _ in pkgutil.iter_modules(scrapers_pkg.__path__):
        if module_name in ("base", "pararius", "kamernet"):
            continue
        try:
            mod = importlib.import_module(f"scrapers.{module_name}")
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if isinstance(attr, type) and issubclass(attr, BaseScraper) and attr is not BaseScraper:
                    scraper_name = attr_name.replace("Scraper", "")
                    scrapers.append((scraper_name, attr(config)))
                    logger.info("Loaded agency scraper: %s (%s)", scraper_name, module_name)
        except Exception as e:
            logger.debug("Could not load optional scraper from %s: %s", module_name, e)

    return scrapers


def run_pipeline(config_path: str = None, skip_alerts: bool = False) -> List[FilterEvaluation]:
    load_dotenv()

    config = load_config(config_path)
    target_city = config.get("search_criteria", {}).get("location", "Netherlands")
    max_rent = config.get("search_criteria", {}).get("max_rent_eur", 2000)
    logger.info("Search target: %s region <= €%s", target_city, max_rent)

    scrapers = load_all_scrapers(config)

    all_listings: List[Listing] = []
    seen_urls = set()

    for name, scraper in scrapers:
        logger.info("Running %s scraper...", name)
        try:
            results = scraper.scrape()
            for item in results:
                normalized_url = item.url.split("?")[0].rstrip("/")
                if normalized_url not in seen_urls:
                    seen_urls.add(normalized_url)
                    all_listings.append(item)
            logger.info("[%s] Extracted %d listings.", name, len(results))
        except Exception as e:
            logger.error("Failed running %s scraper: %s", name, e)

    logger.info("Total deduplicated listings gathered: %d", len(all_listings))

    # Evaluate listings
    listing_filter = RentalFilter(config)
    evaluations = listing_filter.filter_all(all_listings)

    # Load existing evaluations if any to preserve previous review assessments
    data_dir = Path(WORKSPACE_ROOT) / "data"
    data_dir.mkdir(exist_ok=True)
    out_file = data_dir / "listings.json"
    existing_evals: Dict[str, Dict[str, Any]] = {}
    if out_file.exists():
        try:
            with open(out_file, "r", encoding="utf-8") as f:
                prev_list = json.load(f)
                for item in prev_list:
                    l_id = item.get("listing", {}).get("id")
                    if l_id:
                        existing_evals[l_id] = item
        except Exception as e:
            logger.warning("Could not load previous listings: %s", e)

    # Preserve review metadata on re-scraped listings
    for e in evaluations:
        if e.listing.id in existing_evals:
            prev = existing_evals[e.listing.id]
            e.ai_checked = prev.get("ai_checked", False)
            e.ai_verdict = prev.get("ai_verdict")
            e.ai_score = prev.get("ai_score")
            e.ai_rationale = prev.get("ai_rationale")
            e.ai_pros = prev.get("ai_pros", [])
            e.ai_cons = prev.get("ai_cons", [])
            e.alerted = prev.get("alerted", prev.get("alerted_standalone", False) or prev.get("alerted_ai", False))

    matches = [e for e in evaluations if e.status == "MATCH"]
    reviews = [e for e in evaluations if e.status == "NEEDS_REVIEW"]
    rejected = [e for e in evaluations if e.status == "REJECTED"]
    pending = [e for e in (matches + reviews) if not e.ai_checked]

    print("\n" + "=" * 65)
    print(f"Summary for {target_city}:")
    print(f"- Total scraped:    {len(all_listings)}")
    print(f"- Direct matches:   {len(matches)}")
    print(f"- Needs review:     {len(reviews)}")
    print(f"- Disqualified:     {len(rejected)}")
    print(f"- Pending review:   {len(pending)}")
    print("=" * 65 + "\n")

    if not skip_alerts:
        alerted_file = data_dir / "alerted_ids.json"
        alerted_ids = set()
        if alerted_file.exists():
            try:
                with open(alerted_file, "r", encoding="utf-8") as f:
                    alerted_ids = set(json.load(f))
            except Exception:
                alerted_ids = set()

        notifier = TelegramNotifier()
        alerts_to_send = [e for e in (matches + reviews) if e.listing.id not in alerted_ids]
        max_alerts = config.get("telegram", {}).get("max_alerts_per_run", 5)

        new_alerts_sent = 0
        if alerts_to_send:
            print(f"Alerting on {min(len(alerts_to_send), max_alerts)} new listings:")
            for idx, item in enumerate(alerts_to_send[:max_alerts], 1):
                l = item.listing
                print(f"[{idx}] {item.status} ({item.score} pts) | {l.source.upper()} | €{l.price} | {l.title}")
                print(f"     URL: {l.url}")
                if item.flags:
                    print(f"     Notes: {'; '.join(item.flags)}")
                sent = notifier.send_alert(item)
                if sent:
                    item.alerted = True
                    alerted_ids.add(l.id)
                    new_alerts_sent += 1

            with open(alerted_file, "w", encoding="utf-8") as f:
                json.dump(sorted(list(alerted_ids)), f, indent=2)

        logger.info("Telegram alerts sent for %d new properties.", new_alerts_sent)

    # Persist updated data
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump([e.to_dict() for e in evaluations], f, indent=2, ensure_ascii=False)
    logger.info("Results saved to %s", out_file)

    return evaluations


def main():
    parser = argparse.ArgumentParser(description="Dutch Rental Housing Scraper & Filter")
    parser.add_argument("--config", "-c", help="Path to config JSON file")
    parser.add_argument("--no-alert", action="store_true", help="Skip sending Telegram alerts")
    args = parser.parse_args()

    run_pipeline(config_path=args.config, skip_alerts=args.no_alert)


if __name__ == "__main__":
    main()
