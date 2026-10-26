"""Main orchestrator for the Dutch apartment hunting system (Autonomous / Non-AI Mode)."""

import os
import sys
import json
import logging
from typing import List, Dict, Any
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
from filters.agent_filter import AgentFilter
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


def load_all_scrapers(config: Dict[str, Any]) -> List[tuple]:
    """Load core nationwide scrapers and auto-discover any local or custom agency scrapers."""
    import pkgutil
    import importlib
    import scrapers as scrapers_pkg

    scrapers = [
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
                    logger.info("Discovered and loaded agency scraper: %s (%s)", scraper_name, module_name)
        except Exception as e:
            logger.debug("Could not load optional scraper from %s: %s", module_name, e)

    return scrapers


def run_pipeline() -> List[FilterEvaluation]:
    # Load environment variables
    load_dotenv()

    # Load configuration
    config = load_config()
    target_city = config.get("search_criteria", {}).get("location", "Netherlands")
    max_rent = config.get("search_criteria", {}).get("max_rent_eur", 2000)
    logger.info("Configuration loaded. Search target: %s region <= €%s", target_city, max_rent)

    # Load all available scrapers (nationwide + any discovered local agency scrapers)
    scrapers = load_all_scrapers(config)

    all_listings: List[Listing] = []
    seen_urls = set()

    for name, scraper in scrapers:
        logger.info(f"--- Running {name} scraper ---")
        try:
            results = scraper.scrape()
            for item in results:
                normalized_url = item.url.split("?")[0].rstrip("/")
                if normalized_url not in seen_urls:
                    seen_urls.add(normalized_url)
                    all_listings.append(item)
            logger.info(f"[{name}] Extracted {len(results)} listings.")
        except Exception as e:
            logger.error(f"Failed running {name}: {e}")

    logger.info(f"Total deduplicated listings gathered: {len(all_listings)}")

    # Run heuristic Dutch market filter
    agent_filter = AgentFilter(config)
    evaluations = agent_filter.filter_all(all_listings)

    # Load existing evaluations if any to preserve previous AI assessments
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
            logger.warning(f"Could not load previous listings: {e}")

    # Preserve AI metadata on re-scraped listings
    for e in evaluations:
        if e.listing.id in existing_evals:
            prev = existing_evals[e.listing.id]
            e.ai_checked = prev.get("ai_checked", False)
            e.ai_verdict = prev.get("ai_verdict")
            e.ai_score = prev.get("ai_score")
            e.ai_rationale = prev.get("ai_rationale")
            e.ai_pros = prev.get("ai_pros", [])
            e.ai_cons = prev.get("ai_cons", [])
            e.alerted_standalone = prev.get("alerted_standalone", False)
            e.alerted_ai = prev.get("alerted_ai", False)

    matches = [e for e in evaluations if e.status == "MATCH"]
    reviews = [e for e in evaluations if e.status == "NEEDS_REVIEW"]
    rejected = [e for e in evaluations if e.status == "REJECTED"]
    pending_ai = [e for e in (matches + reviews) if not e.ai_checked]

    print("\n" + "=" * 70)
    print(f"📊 SUMMARY OF APARTMENT HUNTING RUN ({target_city.upper()})")
    print(f"Total Scraped: {len(all_listings)}")
    print(f"✅ Prime Matches: {len(matches)}")
    print(f"🔍 Borderline / Unsure Listings: {len(reviews)} (Included for alerts)")
    print(f"❌ Disqualified (Budget/Pets/Roommates): {len(rejected)}")
    print(f"⏳ Pending AI Review: {len(pending_ai)}")
    print("=" * 70 + "\n")

    # Track alerted listings so repeat runs only alert on NEW discoveries
    alerted_file = data_dir / "alerted_ids.json"
    alerted_ids = set()
    if alerted_file.exists():
        try:
            with open(alerted_file, "r", encoding="utf-8") as f:
                alerted_ids = set(json.load(f))
        except Exception:
            alerted_ids = set()

    notifier = TelegramNotifier()
    # Alert on BOTH matches and unsure listings (false-positives welcome)
    alerts_to_send = [e for e in (matches + reviews) if e.listing.id not in alerted_ids]

    print(f"--- Top {min(len(alerts_to_send), 5)} New Recommendations to Alert ---")
    new_alerts_sent = 0
    for idx, item in enumerate(alerts_to_send[:5], 1):
        l = item.listing
        print(f"[{idx}] {item.status} ({item.score} pts) | {l.source.upper()} | €{l.price} | {l.title}")
        print(f"     URL: {l.url}")
        if item.flags:
            print(f"     Notes: {'; '.join(item.flags)}")
        sent = notifier.send_alert(item, is_ai_mode=False)
        if sent:
            item.alerted_standalone = True
            alerted_ids.add(l.id)
            new_alerts_sent += 1

    # Mark remaining candidate IDs as indexed so we don't spam on subsequent runs
    for e in (matches + reviews):
        alerted_ids.add(e.listing.id)

    with open(alerted_file, "w", encoding="utf-8") as f:
        json.dump(list(alerted_ids), f, indent=2)

    logger.info(f"Telegram alerts sent for {new_alerts_sent} new properties.")

    # Persist updated data
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump([e.to_dict() for e in evaluations], f, indent=2, ensure_ascii=False)
    logger.info(f"Results saved to {out_file}")

    return evaluations


if __name__ == "__main__":
    run_pipeline()
