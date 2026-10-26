"""Telegram alerting module."""

import os
import logging
import requests
from typing import Optional
from dotenv import load_dotenv
from models import FilterEvaluation

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        load_dotenv()
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        self.is_configured = bool(
            self.token
            and self.chat_id
            and not self.token.startswith("123456789:ABC")
            and self.chat_id != "123456789"
        )

    def format_message(self, eval_item: FilterEvaluation) -> str:
        listing = eval_item.listing
        city_prefix = f"[{listing.city}] " if listing.city else ""

        if eval_item.ai_checked and eval_item.ai_score:
            header = f"<b>{city_prefix}Rental Alert ({eval_item.ai_score}/100)</b>"
        elif eval_item.status == "NEEDS_REVIEW":
            header = f"<b>{city_prefix}Rental Alert (Review Recommended)</b>"
        else:
            header = f"<b>{city_prefix}Rental Alert</b>"

        specs = []
        if listing.living_area_m2:
            m2 = int(listing.living_area_m2) if listing.living_area_m2.is_integer() else listing.living_area_m2
            specs.append(f"{m2} m²")
        if listing.interior:
            specs.append(listing.interior)
        if listing.rooms:
            specs.append(f"{listing.rooms} room{'s' if listing.rooms > 1 else ''}")

        location_str = f"{listing.neighborhood}, {listing.city}" if listing.neighborhood else listing.city

        lines = [
            header,
            f"<b>{listing.title}</b>",
            f"Price: €{listing.price}/month" if listing.price else "Price: N/A",
            f"Location: {location_str}",
        ]
        if specs:
            lines.append(f"Specs: {' • '.join(specs)}")
        lines.append(f"Source: {listing.source.upper()}")
        lines.append(f"URL: {listing.url}")

        if eval_item.ai_checked and eval_item.ai_rationale:
            lines.append(f"\nNotes: {eval_item.ai_rationale}")
        elif eval_item.flags:
            lines.append("\nNotes:")
            for flag in eval_item.flags:
                lines.append(f"• {flag}")

        return "\n".join(lines)

    def send_alert(self, eval_item: FilterEvaluation, **kwargs) -> bool:
        message = self.format_message(eval_item)

        if not self.is_configured:
            logger.info("Telegram not configured or in dry-run mode. Message preview:\n%s", message)
            print("\n" + "=" * 60)
            print(f"TELEGRAM ALERT [DRY RUN]: {eval_item.listing.title}")
            print(f"Status: {eval_item.status} | URL: {eval_item.listing.url}")
            print("=" * 60)
            return True

        api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

        try:
            resp = requests.post(api_url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info("Telegram alert sent for %s", eval_item.listing.title)
                return True
            else:
                logger.warning("Failed to send Telegram alert: %s", resp.text)
                return False
        except Exception as e:
            logger.error("Telegram request error: %s", e)
            return False
