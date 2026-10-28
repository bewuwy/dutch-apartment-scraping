# Dutch Apartment Hunter

A Python-based scraper, filter, and Telegram notification tool for the Dutch rental housing market. It monitors national portals (Pararius, Kamernet) and local estate agencies (makelaars), filters listings according to budget and Dutch tenancy conditions, and delivers alerts to Telegram.

## Features

- **Multi-Source Scraping:**
  - **Pararius:** Automated search and detail enrichment using Playwright.
  - **Kamernet:** Direct Next.js page data extraction and listing detail enrichment (registration, pets, deposit).
  - **Funda:** Nationwide rental listing scraper leveraging reverse-engineered mobile APIs.
  - **Custom Agency Scrapers:** Dynamic auto-discovery for agency scrapers. Dropping any class inheriting from `BaseScraper` into `scrapers/` runs it automatically.
- **Tenancy-Aware Filtering:**
  - Evaluates Dutch rental specifics: municipal registration (*gemeente inschrijving*), independent vs. shared accommodation, pet policies, and student/guarantor acceptance.
  - Hard-eliminates over-budget or rented properties, and flags borderline properties for review.
- **Deduplication & Alerts:**
  - Prevents repeat Telegram alerts across runs using persistent ID tracking.
  - Dry-run mode for previewing alerts locally when Telegram credentials are not configured.
- **Review CLI:**
  - `agent_review.py` allows inspecting pending listings, recording detailed verdicts or contract notes, and sending verified alerts.

## Installation

### Prerequisites
- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) or `pip`

### Setup
```bash
# Clone the repository
git clone <repo-url>
cd dutch-apartment-hunter

# Create virtual environment and install dependencies
uv venv .venv
source .venv/bin/activate
uv pip install -e .

# Install Playwright browser binaries
playwright install chromium
```

## Configuration

### 1. Search Criteria (`config.json`)
Copy the example template:
```bash
cp config.example.json config.json
```

Adjust the parameters to match your search:
```json
{
  "search_criteria": {
    "location": "amsterdam",
    "max_rent_eur": 2000,
    "min_size_m2": 45,
    "min_bedrooms": 1
  },
  "filter_rules": {
    "reject_roommates_or_shared_housing": true,
    "reject_single_occupant_only": true,
    "reject_explicit_no_pets": false,
    "require_registration_possible": true,
    "reject_no_students_unless_guarantors_allowed": true
  },
  "tenant_profile": {
    "tenants": "Couple",
    "occupants_count": 2,
    "status": "Working professional",
    "income": "Employment salary",
    "has_pets": false,
    "registration_required": true
  },
  "telegram": {
    "max_alerts_per_run": 5
  }
}
```

### 2. Telegram Notifications (`.env`)
Copy the `.env.example` template:
```bash
cp .env.example .env
```

Configure your Telegram bot credentials:
- `TELEGRAM_BOT_TOKEN`: Bot token from [@BotFather](https://t.me/BotFather).
- `TELEGRAM_CHAT_ID`: Chat ID from [@userinfobot](https://t.me/userinfobot) or your channel ID.

*(If left unconfigured, the system runs in dry-run mode and prints alerts to the terminal).*

## Usage

### Running the Scraper
Run the full scraping, filtering, and alert pipeline:
```bash
python main.py
```

CLI options:
```bash
python main.py --config config.json  # Specify a custom config file
python main.py --no-alert            # Run scrapers and filters without sending alerts
```

### Web UI (Svelte + Pico CSS)

Run the minimalist web UI:

```bash
# Start backend server & Svelte dev server (with hot reload)
pnpm dev

# Build the production frontend
pnpm build

# Start the production server (served at http://localhost:8000)
pnpm start

# Run Svelte linter
pnpm lint
```

### Reviewing Listings (`agent_review.py`)
To review unvetted or flagged listings:

```bash
# 1. View listings awaiting review
python agent_review.py pending

# 2. Record a verdict for a specific listing
python agent_review.py update \
    --id "pararius_8abd13ec" \
    --verdict STRONG_MATCH \
    --score 90 \
    --rationale "Central location, registration permitted, independent apartment." \
    --pros "Modern kitchen" "Close to station" \
    --cons "Excludes utilities"

# 3. Send top verified listings to Telegram
python agent_review.py notify --top 5
```

## Adding Custom Agency Scrapers

To scrape regional agencies (e.g. 123Wonen, NederWoon, Living Today), create a new file in `scrapers/` inheriting from `BaseScraper`:

```python
# scrapers/my_agency.py
from typing import List
from models import Listing
from scrapers.base import BaseScraper

class MyAgencyScraper(BaseScraper):
    def scrape(self) -> List[Listing]:
        location = self.search_criteria.get("location")
        max_rent = self.search_criteria.get("max_rent_eur")
        # Scrape and return a list of Listing objects
        return []
```

`main.py` automatically detects and executes any `BaseScraper` subclasses in `scrapers/`.

## Project Structure

```text
├── config.example.json      # Template search criteria and filter rules
├── config.json              # (Gitignored) Your active search criteria
├── .env.example             # Template for Telegram credentials
├── .env                     # (Gitignored) Active credentials
├── models.py                # Listing and FilterEvaluation dataclasses
├── scrapers/                # Scraper modules
│   ├── base.py              # BaseScraper abstract base class
│   ├── pararius.py          # Pararius scraper (Playwright)
│   ├── kamernet.py          # Kamernet scraper (Next.js data extraction)
│   └── funda.py             # Funda scraper (pyfunda)
├── filters/
│   └── agent_filter.py      # Tenancy rules and criteria evaluator
├── notifications/
│   └── telegram.py          # Telegram alert formatter and dispatcher
├── main.py                  # Main scraping and filtering pipeline
├── agent_review.py          # Listing review and curation CLI
├── pyproject.toml           # Project packaging and dependencies
└── data/                    # (Gitignored) Cached listings and alert history
```

## License

MIT
