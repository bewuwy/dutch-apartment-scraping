"""AI Agent review and curation CLI.

Used when an AI Agent (e.g., Antigravity CLI / Claude Code) evaluates,
scores, and curates candidate housing listings without external API tokens.
"""

import sys
import os
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any

WORKSPACE_ROOT = os.path.dirname(os.path.abspath(__file__))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from models import FilterEvaluation
from notifications.telegram import TelegramNotifier

DATA_FILE = Path(WORKSPACE_ROOT) / "data" / "listings.json"
AI_ALERTED_FILE = Path(WORKSPACE_ROOT) / "data" / "alerted_ai_ids.json"


def load_evaluations() -> List[FilterEvaluation]:
    if not DATA_FILE.exists():
        print(f"No listings data found at {DATA_FILE}. Run `python main.py` first.")
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [FilterEvaluation.from_dict(d) for d in data]


def save_evaluations(evaluations: List[FilterEvaluation]) -> None:
    DATA_FILE.parent.mkdir(exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump([e.to_dict() for e in evaluations], f, indent=2, ensure_ascii=False)


def get_pending_listings() -> List[FilterEvaluation]:
    evaluations = load_evaluations()
    # Return any listing that hasn't been verified by an AI agent yet
    return [e for e in evaluations if not e.ai_checked and e.status in ("MATCH", "NEEDS_REVIEW")]


def list_pending():
    pending = get_pending_listings()
    print(f"\n📋 FOUND {len(pending)} PENDING LISTINGS AWAITING AI REVIEW\n" + "=" * 65)
    for idx, e in enumerate(pending, 1):
        l = e.listing
        print(f"[{idx}] ID: {l.id}")
        print(f"     Title: {l.title} | Source: {l.source.upper()} | €{l.price}/mo")
        print(f"     Status: {e.status} | Heuristic Score: {e.score}")
        print(f"     URL: {l.url}")
        if e.flags:
            print(f"     Flags: {'; '.join(e.flags)}")
        if l.description:
            snippet = l.description.strip().replace("\n", " ")[:250]
            print(f"     Desc Snippet: {snippet}...")
        print("-" * 65)


def update_verdict(listing_id: str, verdict: str, score: int, rationale: str, pros: List[str] = None, cons: List[str] = None):
    evaluations = load_evaluations()
    target = None
    for e in evaluations:
        if e.listing.id == listing_id:
            target = e
            break

    if not target:
        print(f"❌ Listing with ID '{listing_id}' not found.")
        return False

    target.ai_checked = True
    target.ai_verdict = verdict.upper()
    target.ai_score = max(0, min(score, 100))
    target.ai_rationale = rationale
    if pros:
        target.ai_pros = pros
    if cons:
        target.ai_cons = cons

    if target.ai_verdict == "DISQUALIFIED":
        target.status = "REJECTED"
    elif target.ai_verdict == "STRONG_MATCH":
        target.status = "MATCH"
    elif target.ai_verdict == "POTENTIAL_MATCH":
        target.status = "NEEDS_REVIEW"

    save_evaluations(evaluations)
    print(f"✅ Listing '{listing_id}' updated by AI: {target.ai_verdict} ({target.ai_score}/100)")
    return True


def notify_verified(top_n: int = 5):
    from dotenv import load_dotenv
    load_dotenv()

    evaluations = load_evaluations()
    ai_verified = [e for e in evaluations if e.ai_checked and e.status in ("MATCH", "NEEDS_REVIEW")]
    # Sort by AI score descending
    ai_verified.sort(key=lambda e: (e.ai_score or 0), reverse=True)

    alerted_ids = set()
    if AI_ALERTED_FILE.exists():
        try:
            with open(AI_ALERTED_FILE, "r", encoding="utf-8") as f:
                alerted_ids = set(json.load(f))
        except Exception:
            alerted_ids = set()

    notifier = TelegramNotifier()
    to_send = [e for e in ai_verified if e.listing.id not in alerted_ids]

    print(f"\n🤖 SENDING {min(len(to_send), top_n)} AI-VERIFIED LISTINGS VIA TELEGRAM\n")
    sent_count = 0
    for e in to_send[:top_n]:
        sent = notifier.send_alert(e, is_ai_mode=True)
        if sent:
            alerted_ids.add(e.listing.id)
            sent_count += 1

    with open(AI_ALERTED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(alerted_ids), f, indent=2)

    print(f"✅ Dispatched {sent_count} AI-verified alerts.")


def main():
    parser = argparse.ArgumentParser(description="AI Agent Housing Review Utility")
    subparsers = parser.add_subparsers(dest="command")

    # Command: pending
    subparsers.add_parser("pending", help="List properties pending AI verification")

    # Command: update
    update_p = subparsers.add_parser("update", help="Update AI evaluation for a property")
    update_p.add_argument("--id", required=True, help="Listing ID")
    update_p.add_argument("--verdict", choices=["STRONG_MATCH", "POTENTIAL_MATCH", "DISQUALIFIED"], required=True)
    update_p.add_argument("--score", type=int, required=True, help="Score 0-100")
    update_p.add_argument("--rationale", required=True, help="AI rationale/justification")
    update_p.add_argument("--pros", nargs="*", default=[], help="List of pros")
    update_p.add_argument("--cons", nargs="*", default=[], help="List of cons/caveats")

    # Command: notify
    notify_p = subparsers.add_parser("notify", help="Send top AI-verified listings to Telegram")
    notify_p.add_argument("--top", type=int, default=5, help="Number of listings to send")

    args = parser.parse_args()

    if args.command == "pending":
        list_pending()
    elif args.command == "update":
        update_verdict(args.id, args.verdict, args.score, args.rationale, args.pros, args.cons)
    elif args.command == "notify":
        notify_verified(args.top)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
