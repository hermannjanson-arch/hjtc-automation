# -*- coding: utf-8 -*-
"""
regenerate_descriptions.py

Two ways to run this:

  1. python3 regenerate_descriptions.py --demo
     Runs on the 4 hand-written sample listings (no API calls, no
     credentials needed). Good for checking the template renders correctly.

  2. python3 regenerate_descriptions.py --live
     Runs against your REAL eBay account:
       - fetches all active listings (GetSellerList)
       - reads each one's current description (GetItem)
       - extracts the Condition block and rebuilds with the new template
       - DRY_RUN=True (default): writes preview/*.html + review.csv, touches
         nothing on eBay
       - DRY_RUN=False: after you've checked review.csv, actually calls
         ReviseItem for every listing marked "OK"

Setup for --live:
    1. pip install beautifulsoup4 requests --break-system-packages
    2. Open ebay_trading_api.py and paste your OAuth user token
       (same one ebay_feedback_bot.py already uses)
    3. Run with DRY_RUN = True first, check review.csv + preview/*.html
    4. Set DRY_RUN = False and run again to actually push changes
"""

import argparse
import csv
import os

from bs4 import BeautifulSoup

from description_template import build_description

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

DRY_RUN = True
PREVIEW_DIR = "preview"
REVIEW_CSV = "review.csv"

# Headings that mark the boundaries of the variable CONDITION block in the
# OLD descriptions. Everything between "Condition" and "Shipping - Domestic
# & International" is treated as condition text (grade + standard note +
# any flaw sentence) and carried over into the new template.
# Add variants here if you find listings with slightly different wording.
CONDITION_HEADINGS = {"condition"}
SHIPPING_HEADINGS = {
    "shipping - domestic & international",
    "shipping – domestic & international",
    "shipping - domestic and international",
}

# ---------------------------------------------------------------------------
# EXTRACTION
# ---------------------------------------------------------------------------


def _to_lines(raw_description):
    """Accepts either raw HTML or plain text and returns a clean list of
    non-empty lines in reading order."""
    if "<" in raw_description and ">" in raw_description:
        soup = BeautifulSoup(raw_description, "html.parser")
        text = soup.get_text("\n")
    else:
        text = raw_description
    lines = [l.strip() for l in text.split("\n")]
    return [l for l in lines if l]


def extract_variable_blocks(raw_description):
    """
    Returns {"condition": [...lines...]}

    condition -> everything between "Condition" and "Shipping - Domestic &
    International" (grade sentence, standard photo/lighting note, and any
    flaw sentence that was manually added for this listing).
    """
    lines = _to_lines(raw_description)

    condition_idx = None
    shipping_idx = None

    for i, line in enumerate(lines):
        norm = line.strip().lower().rstrip(":")
        if condition_idx is None and norm in CONDITION_HEADINGS:
            condition_idx = i
        elif condition_idx is not None and shipping_idx is None and norm in SHIPPING_HEADINGS:
            shipping_idx = i
            break

    if condition_idx is None or shipping_idx is None:
        raise ValueError(
            "Could not find 'Condition' / 'Shipping - Domestic & International' headings - "
            "this listing's description doesn't match the expected structure. "
            "Flag it for manual review instead of auto-processing."
        )

    condition_lines = lines[condition_idx + 1 : shipping_idx]

    return {"condition": condition_lines}


# ---------------------------------------------------------------------------
# REBUILD
# ---------------------------------------------------------------------------


def rebuild_description(item_title, raw_old_description):
    blocks = extract_variable_blocks(raw_old_description)
    new_html = build_description(
        item_title=item_title,
        condition_paragraphs=blocks["condition"],
    )
    return new_html, blocks


# ---------------------------------------------------------------------------
# LIVE ROLLOUT - real eBay account, all active listings
# ---------------------------------------------------------------------------


def run_live_rollout():
    from ebay_trading_api import (
        get_active_listings,
        get_item_description,
        revise_item_description,
    )

    os.makedirs(PREVIEW_DIR, exist_ok=True)
    review_rows = []

    print("Fetching active listings from eBay (GetSellerList)...")
    listings = list(get_active_listings())
    print(f"Found {len(listings)} active listings.\n")

    for i, listing in enumerate(listings, start=1):
        item_id = listing["item_id"]
        print(f"[{i}/{len(listings)}] {item_id} - {listing['title'][:60]}")

        try:
            title, old_description = get_item_description(item_id)
        except Exception as e:
            review_rows.append(
                {
                    "item_id": item_id,
                    "title": listing["title"],
                    "status": "FETCH FAILED",
                    "reason": str(e),
                    "condition": "",
                }
            )
            continue

        try:
            new_html, blocks = rebuild_description(title, old_description)
        except ValueError as e:
            review_rows.append(
                {
                    "item_id": item_id,
                    "title": title,
                    "status": "NEEDS MANUAL REVIEW",
                    "reason": str(e),
                    "condition": "",
                }
            )
            continue

        preview_path = os.path.join(PREVIEW_DIR, f"{item_id}.html")
        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(new_html)

        row = {
            "item_id": item_id,
            "title": title,
            "status": "OK",
            "reason": "",
            "condition": " | ".join(blocks["condition"]),
        }

        if DRY_RUN:
            row["status"] = "DRY RUN - not sent"
            review_rows.append(row)
        else:
            try:
                revise_item_description(item_id, new_html)
                row["status"] = "REVISED"
                review_rows.append(row)
            except Exception as e:
                row["status"] = "REVISE FAILED"
                row["reason"] = str(e)
                review_rows.append(row)

    with open(REVIEW_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["item_id", "title", "status", "reason", "condition"]
        )
        writer.writeheader()
        writer.writerows(review_rows)

    ok_count = sum(1 for r in review_rows if r["status"] in ("OK", "DRY RUN - not sent", "REVISED"))
    print(f"\nDone. {len(review_rows)} listings processed, {ok_count} OK.")
    print(f"Preview HTML files -> ./{PREVIEW_DIR}/")
    print(f"Review sheet        -> ./{REVIEW_CSV}")
    if DRY_RUN:
        print("\nThis was a DRY RUN - nothing was changed on eBay.")
        print("Check review.csv and preview/*.html, then set DRY_RUN = False to go live.")


# ---------------------------------------------------------------------------
# LOCAL DEMO - 4 example listings, no API calls, no credentials needed
# ---------------------------------------------------------------------------

SAMPLE_LISTINGS = [
    {
        "item_id": "SAMPLE-dune-flaw",
        "item_title": "Dune 2024 Topps Chrome - Trading Card",
        "old_description": """For sale is this rare and well-preserved Dune trading card from the 2024 Topps Chrome Dune series.
A great collectors item for any fan of the Dune universe!

Condition
Please see the photos for details - what you see is exactly what you will receive. Note: Due to professional studio LED lighting, the reflections and holo-effects on the photos may slightly differ from how they look under natural daylight.
Please note that there is a small, faint scratch on the card that is difficult to see (photo 3).
If there are further questions, feel free to contact us.

Shipping - Domestic & International
We ship from Germany to most countries worldwide...
""",
    },
    {
        "item_id": "SAMPLE-dune-clean",
        "item_title": "Dune 2024 Topps Chrome - Trading Card",
        "old_description": """For sale is this rare and well-preserved Dune trading card from the 2024 Topps Chrome Dune series.
A great collectors item for any fan of the Dune universe!

Condition
Please see the photos for details - what you see is exactly what you will receive. Note: Due to professional studio LED lighting, the reflections and holo-effects on the photos may slightly differ from how they look under natural daylight.
If there are further questions, feel free to contact us.

Shipping - Domestic & International
We ship from Germany to most countries worldwide...
""",
    },
    {
        "item_id": "SAMPLE-harrypotter",
        "item_title": "Harry Potter Kakawow Trading Card",
        "old_description": """Harry Potter Kakawow Trading Card
For sale is this rare and well-preserved Harry Potter trading card from the Kakawow series. A great collector's item for any fan of the Wizarding World!

Condition
This card is in Near-Mint condition, with minimal to no signs of wear.
Please see the photos for details - what you see is exactly what you will receive. Note: Due to professional studio LED lighting, the reflections and holo-effects on the photos may slightly differ from how they look under natural daylight.

Shipping - Domestic & International
We ship from Germany to most countries worldwide...
""",
    },
    {
        "item_id": "SAMPLE-tennis",
        "item_title": "Topps Chrome 2025 - Tennis Trading Card",
        "old_description": """For sale is this rare and well-preserved tennis trading card from the Topps Chrome 2025 series. A great collector's item for any fan!

Condition
This card is in excellent condition, with minimal to no signs of wear.
Please see the photos for details - what you see is exactly what you will receive. Note: Due to professional studio LED lighting, the reflections and holo-effects on the photos may slightly differ from how they look under natural daylight.

Shipping - Domestic & International
We ship from Germany to most countries worldwide...
""",
    },
]


def run_local_preview():
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    review_rows = []

    for listing in SAMPLE_LISTINGS:
        try:
            new_html, blocks = rebuild_description(
                listing["item_title"], listing["old_description"]
            )
        except ValueError as e:
            review_rows.append(
                {
                    "item_id": listing["item_id"],
                    "status": "NEEDS MANUAL REVIEW",
                    "reason": str(e),
                    "condition": "",
                }
            )
            continue

        out_path = os.path.join(PREVIEW_DIR, f"{listing['item_id']}.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(new_html)

        review_rows.append(
            {
                "item_id": listing["item_id"],
                "status": "OK",
                "reason": "",
                "condition": " | ".join(blocks["condition"]),
            }
        )

        print(f"[DEMO] {listing['item_id']} -> preview written to {out_path}")

    with open(REVIEW_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["item_id", "status", "reason", "condition"])
        writer.writeheader()
        writer.writerows(review_rows)

    print(f"\nDone. {len(review_rows)} listings processed.")
    print(f"Preview HTML files -> ./{PREVIEW_DIR}/")
    print(f"Review sheet        -> ./{REVIEW_CSV}")


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Regenerate eBay listing descriptions.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run against your real eBay account (needs ebay_trading_api.py configured).",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run on the 4 built-in sample listings only, no API calls needed.",
    )
    args = parser.parse_args()

    if args.live:
        run_live_rollout()
    else:
        run_local_preview()

