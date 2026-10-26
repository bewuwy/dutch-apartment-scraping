# Dutch Apartment Hunter

A multi-source scraper, intelligent filter, and Telegram alerting system for the Dutch rental housing market. Designed for the entire Netherlands, with modular support for nationwide portals and regional rental agencies.

---

## Features

- **Nationwide & Regional Scraping:**
  - **Pararius:** Automated search across any Dutch city using Playwright stealth and robust parser logic.
  - **Kamernet:** Direct Next.js data extraction for rooms, studios, and apartments nationwide.
  - **Plug-and-Play Local Makelaars:** Dynamic auto-discovery for local agency scrapers. Simply drop any scraper subclassing `BaseScraper` into `scrapers/` and `main.py` runs it automatically.
  - **Private Branches for Regional Scrapers:** Keep public `main` clean with nationwide portals, while maintaining city-specific agency scrapers on a `private` branch with a separate origin.
- **Two Execution Modes:**
  - **Mode 1 (AI Agent Mode):** Zero-effort conversational mode. Invoke the agent in your CLI (Antigravity, Claude Code, AGY CLI) and the AI agent automatically runs the background scrapers, reviews listing descriptions, evaluates Dutch contract nuances (registration, guarantors, pets, temporary contracts), and dispatches ranked alerts.
  - **Mode 2 (Autonomous Python):** Standalone headless script (`main.py`) suitable for cron jobs or scheduled monitoring. Evaluates listings using heuristic filters and pushes clean alerts to Telegram without requiring an AI agent or external API tokens.
- **Privacy & Clean Configuration:** All sensitive credentials (`.env`) and personal search criteria (`config.json`) are decoupled and gitignored.

---

## Getting Started

### 1. Setup Environment
```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e .
playwright install chromium
```

### 2. Configure Your Search Profile
You can configure your search criteria either conversationally or manually:

#### Way A: Conversational Setup via AI Agent (Recommended)
Ask your AI coding assistant:
> *"Set up my Dutch housing preferences"* or *"Configure apartment search for [City]"*

The AI agent will interview you regarding your target municipality, budget ceiling, tenant composition, pet requirements, municipal registration (*inschrijving*), and generate `config.json` automatically.

#### Way B: Manual Setup (Without AI)
Copy the example template and edit it with your preferences:
```bash
cp config.example.json config.json
```
Edit `config.json` to customize:
- `search_criteria`: Target city, search radius, max rent, and minimum specs.
- `tenant_profile`: Occupants count, employment/student status, guarantor needs, and pet policies.
- `filter_rules`: Strictness for registration, shared housing, and guarantor acceptance.

### 3. Configure Telegram Notifications
Copy the `.env` template and add your Telegram bot credentials:
```bash
cp .env.example .env
```
- `TELEGRAM_BOT_TOKEN`: Your Telegram Bot API token from [@BotFather](https://t.me/BotFather).
- `TELEGRAM_CHAT_ID`: Your personal or group chat ID (from [@userinfobot](https://t.me/userinfobot)).

---

## How to Run

### Option 1: AI Agent Mode (Interactive & Managed)
You do not need to worry about manual script commands or database management. Simply launch your AI CLI agent (e.g. Antigravity, Claude Code) and prompt:

> *"Check for new apartments matching my config and send the best ones to Telegram."*

or invoke the skill directly:
```bash
/skill dutch-apartment-hunter
```

The AI agent will:
1. Run the scrapers to update the local listings database.
2. Review all unvetted or unsure listings, analyzing Dutch contract text and agency policies.
3. Assign match scores and explanations.
4. Dispatch the top-ranked verified alerts directly to your Telegram.

### Option 2: Autonomous Python Mode (Headless / Scheduled)
Run the automated pipeline directly from the command line:
```bash
uv run python main.py
```
- Scrapes all active portals and agencies.
- Evaluates listings against `config.json` criteria.
- Sends clean alerts to Telegram (`Rental Alert` or `Rental Alert (Unsure match)`).
- Queues unvetted listings in `data/listings.json` with `ai_checked: false` ready for future AI agent review.

---

## Expanding to Other Dutch Cities & Private Branches

The project is built to easily expand beyond default national portals:

### 1. Change the Target Location
Updating `location` in `config.json` automatically updates search queries on nationwide portals like Pararius and Kamernet.

### 2. Auto-Discovery for Local Makelaars
Any scraper placed under `scrapers/` that inherits from `BaseScraper` is automatically discovered and loaded by `main.py` at runtime.

### 3. Scaffold Local Scrapers via AI Agent
Regional makelaars often have exclusive listings before they reach national aggregators. You can ask your AI agent:
> *"Find top rental agencies in Utrecht/Rotterdam and build scrapers for them."*

The AI agent will create new scraper modules under `scrapers/<agency>.py`.

### 4. Separate Private Branch for Regional Scrapers
To keep the public repository clean and vendor-neutral, city-specific scrapers (such as the Leiden agencies) are maintained on a `private` branch with a separate origin:

```bash
# Push core framework to public repository:
git checkout main
git remote add origin git@github.com:youruser/dutch-apartment-hunter.git
git push -u origin main

# Push regional scrapers to a private repository:
git checkout private
git remote add private-origin git@github.com:youruser/dutch-apartment-hunter-private.git
git push -u private-origin private
```

---

## Project Structure

```text
├── config.example.json      # Template for search criteria & tenant profile
├── config.json              # (Gitignored) Your active search criteria
├── .env.example             # Template for Telegram bot tokens
├── .env                     # (Gitignored) Active Telegram credentials
├── models.py                # Unified Listing and FilterEvaluation dataclasses
├── scrapers/                # Scraper modules (Pararius, Kamernet, local makelaars)
│   ├── base.py              # BaseScraper abstract class
│   ├── pararius.py          # Pararius scraper (Playwright stealth)
│   ├── kamernet.py          # Kamernet scraper (Next.js data extraction)
│   └── ...                  # Regional makelaar scrapers
├── filters/                 # Heuristic Dutch market filter
├── notifications/           # Clean Telegram notification dispatcher
├── main.py                  # Standalone autonomous scraper runner
├── agent_review.py          # AI agent review & ranking CLI tool
├── .agents/skills/          # Agent skill definitions (dutch-apartment-hunter)
└── data/                    # (Gitignored) Scraped listings & alert history
```

---

## License

MIT
