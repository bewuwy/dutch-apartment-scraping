# Agent Instructions & Conventions (`AGENTS.md`)

## Project Overview

`dutch-apartment-hunter` is a Python-based scraper, filter, and alerting tool for the Dutch rental housing market. It monitors national real estate portals (Pararius, Kamernet) and local estate agencies (*makelaars*), filters listings against tenancy rules and budget constraints, and dispatches alerts to Telegram.

---

## Architecture & Codebase Map

- **`models.py`**:
  - `Listing`: Dataclass capturing unified property data (id, title, url, price, city, address, rooms, living area, interior, property type, source, raw data).
  - `FilterEvaluation`: Dataclass capturing filter verdicts (`MATCH`, `NEEDS_REVIEW`, `REJECTED`), heuristic score (0–100), flags, reasons, review metadata (`ai_checked`, `ai_verdict`, `ai_score`, `ai_rationale`), and notification state (`alerted`).
- **`scrapers/`**:
  - `base.py`: Contains `BaseScraper` abstract class. Requires implementing `scrape(self) -> List[Listing]`.
  - `pararius.py`: Nationwide scraper using Playwright and card parsing utilities.
  - `kamernet.py`: Nationwide scraper extracting Next.js JSON state for apartments and studios.
  - `*`: Any additional file under `scrapers/` containing a subclass of `BaseScraper` is automatically discovered and executed by `main.py`.
- **`filters/agent_filter.py`**:
  - `RentalFilter` (aliased as `AgentFilter`): Evaluates listings against `config.json` rules:
    - Hard eliminations: unavailable/rented properties, over-budget properties, below minimum area.
    - Dutch market checks: municipal registration (*gemeente inschrijving*), independent accommodation vs. shared rooms, pet policies, couples vs. single occupancy, and student/guarantor acceptance (*garantstelling*).
- **`notifications/telegram.py`**:
  - `TelegramNotifier`: Formats HTML alerts and dispatches via the Telegram Bot API. Falls back to a local console preview (dry-run mode) when credentials in `.env` are unset or placeholders.
- **`main.py`**:
  - Orchestrates the full pipeline: loads config, executes scrapers, deduplicates URLs, runs filters, preserves previous review metadata, dispatches new alerts to Telegram, and persists results to `data/listings.json` and `data/alerted_ids.json`.
  - Supports `--config <path>` and `--no-alert`.
- **`agent_review.py`**:
  - Review CLI for inspecting candidate listings (`pending`), recording scores and rationales (`update`), and dispatching alerts (`notify`).
- **`external_tools/`**:
  - Git submodules and cloned tools for portal parsers (Funda, Kamernet, Pararius). Referenced for card parsing and session construction.
- **`data/`**:
  - Gitignored directory containing `listings.json` (scraped/evaluated listings) and `alerted_ids.json` (deduplication set of already notified listing IDs).

---

## Branch Strategy

- **`main` (Public Remote: `origin`)**:
  - Contains core framework, national portal scrapers, filter engine, and documentation.
  - Must remain vendor-neutral, sanitized of personal search configs, and free of API keys or local database records.
- **`private` (Private Remote: `private`)**:
  - Contains personal search parameters (`config.json`) and regional/local agency scrapers (e.g. Leiden-specific makelaars like 123Wonen, NederWoon, Living Today, Tweelwonen).
  - **CRITICAL RULE:** Never push `private` branch commits to `origin/main`. Only rebase `private` on top of `main`.

---

## Development & Code Conventions

1. **Commit Messages:**
   - Use [Conventional Commits](https://www.conventionalcommits.org/):
     - `feat:` for new capabilities or scraper implementations.
     - `fix:` for bug fixes.
     - `refactor:` for code restructurings without behavior changes.
     - `docs:` for documentation updates.
     - `chore:` for dependency or build maintenance.
2. **Writing Style & Tone:**
   - Write clear, concise, direct documentation and commit messages.
   - Avoid buzzwords and marketing filler ("intelligent", "cutting-edge", "game-changing", "plug-and-play", "zero-effort").
   - Maintain documentation integrity: factual, technical, and accurate to the code.
3. **Data Integrity & Alert Deduplication:**
   - Never mark listings as alerted in `data/alerted_ids.json` unless an alert was actually delivered (or confirmed sent).
   - Preserve existing review metadata (`ai_checked`, `ai_score`, etc.) when re-scraping previously discovered listings.
4. **Scraper Error Handling:**
   - Scrapers must catch exceptions locally and log errors rather than throwing unhandled exceptions that terminate the orchestration pipeline.
5. **Dutch Real Estate Nuances:**
   - Preserve domain accuracy for terms like *inschrijving* (city hall registration), *gestoffeerd* (unfurnished with flooring/curtains), *gemeubileerd* (furnished), *borgtocht* / *garantstelling* (guarantor), and *zelfstandige woonruimte* (independent living space).
