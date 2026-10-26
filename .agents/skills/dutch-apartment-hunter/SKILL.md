---
name: dutch-apartment-hunter
description: Scrape, filter, and monitor Dutch apartment rentals (Pararius, Kamernet, and local agencies) and send notifications via Telegram. Use when searching for housing in the Netherlands, setting up criteria, adding local scrapers, or running housing scans.
---

# Dutch Apartment Hunter

A tool for scraping and monitoring the Dutch rental housing market across municipalities (Amsterdam, Leiden, Utrecht, Rotterdam, The Hague, Eindhoven, etc.).

## Workflows

### 1. Configuration Setup
If `config.json` does not exist, copy `config.example.json` to `config.json` and adjust:
- **Location & Budget:** City name, maximum rent (EUR), minimum area (m²), and room count.
- **Filter Rules:**
  - `reject_roommates_or_shared_housing`: Exclude shared apartments/rooms.
  - `reject_single_occupant_only`: Exclude listings strictly for 1 person if searching as a couple.
  - `reject_explicit_no_pets`: Exclude listings explicitly banning pets.
  - `require_registration_possible`: Exclude listings where municipal registration (*inschrijving*) is prohibited.
  - `reject_no_students_unless_guarantors_allowed`: Check student and guarantor policies.
- **Telegram:** Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to `.env`.

### 2. Running Scrapers & Filtering
Run the scraper pipeline:
```bash
python main.py
```
Options:
- `--config <path>`: Use a custom config file.
- `--no-alert`: Run scrapers and filters without sending Telegram alerts.

### 3. Reviewing Listings (`agent_review.py`)
To inspect unvetted or flagged listings:
```bash
# List pending candidate listings
python agent_review.py pending

# Update verdict and review notes
python agent_review.py update \
    --id "<listing_id>" \
    --verdict <STRONG_MATCH|POTENTIAL_MATCH|DISQUALIFIED> \
    --score <1-100> \
    --rationale "<explanation>" \
    --pros "Pro 1" "Pro 2" \
    --cons "Con 1"

# Dispatch top verified listings via Telegram
python agent_review.py notify --top 5
```

### 4. Adding Local Agency Scrapers
Any scraper placed under `scrapers/` subclassing `BaseScraper` from `scrapers/base.py` is automatically discovered by `main.py`.
1. Subclass `BaseScraper` in `scrapers/<agency_name>.py`.
2. Implement `scrape(self) -> List[Listing]`.
3. The scraper will automatically execute on subsequent runs.
