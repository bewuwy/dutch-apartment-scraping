"""Minimalist Web UI Server for Dutch Apartment Hunter.

Provides API endpoints for listing matches and triggering scrape runs,
and serves the Svelte + Pico CSS frontend.
"""

import sys
import os
import json
import logging
import argparse
import mimetypes
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from models import calculate_posted_days_ago

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("server")

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
LISTINGS_FILE = DATA_DIR / "listings.json"
WEB_DIST_DIR = ROOT_DIR / "web" / "dist"

# Global state for scraper background process
scraper_lock = threading.Lock()
scraper_state = {
    "is_fetching": False,
    "status": "idle",  # "idle", "running", "completed", "error"
    "message": "Ready",
    "started_at": None,
    "finished_at": None,
    "exit_code": None,
    "recent_logs": "",
}


def _run_scraper_task():
    global scraper_state
    with scraper_lock:
        scraper_state["is_fetching"] = True
        scraper_state["status"] = "running"
        scraper_state["message"] = "Fetching listings..."
        scraper_state["started_at"] = datetime.now(timezone.utc).isoformat()
        scraper_state["finished_at"] = None
        scraper_state["exit_code"] = None
        scraper_state["recent_logs"] = ""

    log_lines = []
    try:
        logger.info("Starting scraper pipeline (main.py --no-alert)...")
        cmd = [sys.executable, str(ROOT_DIR / "main.py"), "--no-alert"]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(ROOT_DIR),
            text=True,
            bufsize=1,
        )

        for line in proc.stdout:
            log_lines.append(line)
            if len(log_lines) > 200:
                log_lines.pop(0)

        proc.wait()
        exit_code = proc.returncode

        with scraper_lock:
            scraper_state["is_fetching"] = False
            scraper_state["finished_at"] = datetime.now(timezone.utc).isoformat()
            scraper_state["exit_code"] = exit_code
            scraper_state["recent_logs"] = "".join(log_lines[-50:])

            if exit_code == 0:
                scraper_state["status"] = "completed"
                scraper_state["message"] = "Scraping completed successfully."
                logger.info("Scraper completed successfully.")
            else:
                scraper_state["status"] = "error"
                scraper_state["message"] = f"Scraper exited with code {exit_code}."
                logger.error("Scraper failed with exit code %s.", exit_code)

    except Exception as exc:
        logger.exception("Unexpected error while running scraper: %s", exc)
        with scraper_lock:
            scraper_state["is_fetching"] = False
            scraper_state["status"] = "error"
            scraper_state["finished_at"] = datetime.now(timezone.utc).isoformat()
            scraper_state["message"] = f"Error: {str(exc)}"


class ApartmentHunterHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Connection", "close")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()
        try:
            self.wfile.flush()
        except Exception:
            pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/listings":
            self.handle_get_listings(parsed)
        elif path == "/api/status":
            self.handle_get_status()
        elif path.startswith("/api/"):
            self.send_json({"error": "Endpoint not found"}, status=404)
        else:
            self.serve_static_file(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/fetch":
            self.handle_post_fetch()
        else:
            self.send_json({"error": "Endpoint not found"}, status=404)

    def send_json(self, data: any, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def handle_get_listings(self, parsed):
        params = parse_qs(parsed.query)
        status_filter = params.get("status", ["MATCH"])[0].upper()

        if not LISTINGS_FILE.exists():
            self.send_json({
                "status": "ok",
                "total": 0,
                "matches_count": 0,
                "needs_review_count": 0,
                "rejected_count": 0,
                "last_updated": None,
                "listings": [],
            })
            return

        try:
            mtime = datetime.fromtimestamp(
                LISTINGS_FILE.stat().st_mtime, tz=timezone.utc
            ).isoformat()

            with open(LISTINGS_FILE, "r", encoding="utf-8") as f:
                raw_evaluations = json.load(f)

            # Ensure posted_at and posted_days_ago are populated and fresh
            for item in raw_evaluations:
                l = item.get("listing", {})
                if not l.get("posted_at"):
                    raw = l.get("raw_data", {})
                    l["posted_at"] = (
                        raw.get("publish_date")
                        or raw.get("create_date")
                        or raw.get("offered_since")
                        or raw.get("publication_date")
                    )
                if l.get("posted_at"):
                    l["posted_days_ago"] = calculate_posted_days_ago(l["posted_at"])
                elif l.get("posted_days_ago") is None:
                    l["posted_days_ago"] = calculate_posted_days_ago(mtime)

            total = len(raw_evaluations)
            matches_count = sum(1 for e in raw_evaluations if e.get("status") == "MATCH")
            needs_review_count = sum(1 for e in raw_evaluations if e.get("status") == "NEEDS_REVIEW")
            rejected_count = sum(1 for e in raw_evaluations if e.get("status") == "REJECTED")

            if status_filter == "ALL":
                filtered = raw_evaluations
            else:
                filtered = [e for e in raw_evaluations if e.get("status") == status_filter]

            self.send_json({
                "status": "ok",
                "total": total,
                "matches_count": matches_count,
                "needs_review_count": needs_review_count,
                "rejected_count": rejected_count,
                "last_updated": mtime,
                "listings": filtered,
            })
        except Exception as exc:
            logger.error("Error reading listings: %s", exc)
            self.send_json({"error": "Could not read listings file"}, status=500)

    def handle_get_status(self):
        with scraper_lock:
            state = dict(scraper_state)
        self.send_json(state)

    def handle_post_fetch(self):
        global scraper_state
        with scraper_lock:
            if scraper_state["is_fetching"]:
                self.send_json({
                    "status": "already_running",
                    "message": "Scraper is already running.",
                }, status=409)
                return

        thread = threading.Thread(target=_run_scraper_task, daemon=True)
        thread.start()

        self.send_json({
            "status": "started",
            "message": "Scraper pipeline started.",
        })

    def serve_static_file(self, path: str):
        if not WEB_DIST_DIR.exists():
            msg = (
                "<html><body><h2>Frontend not built yet.</h2>"
                "<p>Run <code>pnpm build</code> to compile the Svelte UI, or use <code>pnpm dev</code> for development.</p>"
                "<p><a href='/api/listings'>View API Listings</a> | <a href='/api/status'>View Scraper Status</a></p>"
                "</body></html>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
            self.wfile.flush()
            return

        clean_path = path.lstrip("/") or "index.html"
        target_path = WEB_DIST_DIR / clean_path

        # If file doesn't exist, fall back to index.html for SPA routing
        if not target_path.exists() or target_path.is_dir():
            target_path = WEB_DIST_DIR / "index.html"

        if not target_path.exists():
            self.send_response(404)
            self.end_headers()
            return

        ctype, _ = mimetypes.guess_type(str(target_path))
        if not ctype:
            ctype = "application/octet-stream"

        try:
            with open(target_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            self.wfile.flush()
        except Exception as exc:
            logger.error("Error serving static file %s: %s", target_path, exc)
            self.send_response(500)
            self.end_headers()

    def log_message(self, format, *args):
        logger.info("%s - - [%s] %s", self.client_address[0], self.log_date_time_string(), format % args)


def run_server(host: str = "127.0.0.1", port: int = 8000):
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, ApartmentHunterHandler)
    logger.info("Dutch Apartment Hunter UI server running at http://%s:%s", host, port)
    logger.info("API endpoints: http://%s:%s/api/listings, http://%s:%s/api/status", host, port, host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dutch Apartment Hunter Web Server")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"), help="Server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")), help="Server port (default: 8000)")
    args = parser.parse_args()

    run_server(host=args.host, port=args.port)
