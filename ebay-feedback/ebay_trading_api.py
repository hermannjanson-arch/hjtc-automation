# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
"""
ebay_trading_api.py

Thin wrapper around the eBay Trading API (XML) for the description rollout:
  - get_active_listings()      -> GetSellerList, paginated, all active items
  - get_item_description(id)   -> GetItem, returns (title, description_html)
  - revise_item_description()  -> ReviseItem, writes the new description back

Auth: reuses the exact same auto-refreshing OAuth access token pattern as
ebay_feedback_bot.py - reads EBAY_CLIENT_ID / EBAY_CLIENT_SECRET /
EBAY_REFRESH_TOKEN from the .env file in this same folder, and requests a
fresh 2h access token automatically whenever needed (cached in memory,
refreshed automatically once it's about to expire).

Requires this file to live in the SAME FOLDER as your existing .env file
(the one ebay_feedback_bot.py already uses).
"""

import base64
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

load_dotenv()  # reads the .env file in the current folder

EBAY_CLIENT_ID = os.environ.get("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.environ.get("EBAY_CLIENT_SECRET")
EBAY_REFRESH_TOKEN = os.environ.get("EBAY_REFRESH_TOKEN")

EBAY_SITE_ID = "77"  # 77 = Germany (eBay.de)
TRADING_API_ENDPOINT = "https://api.ebay.com/ws/api.dll"
COMPATIBILITY_LEVEL = "1193"

# Be polite to eBay's rate limits - small delay between calls
REQUEST_DELAY_SECONDS = 0.4

NS = {"e": "urn:ebay:apis:eBLBaseComponents"}

# In-memory token cache, same pattern as ebay_feedback_bot.py
_token_cache = {"token": None, "expires_at": datetime.utcnow()}


def get_access_token() -> str:
    """Holt (und cached) ein User-Access-Token via Refresh-Token.
    Identisch zur Funktion in ebay_feedback_bot.py."""
    if _token_cache["token"] and datetime.utcnow() < _token_cache["expires_at"]:
        return _token_cache["token"]

    if not (EBAY_CLIENT_ID and EBAY_CLIENT_SECRET and EBAY_REFRESH_TOKEN):
        raise RuntimeError(
            "EBAY_CLIENT_ID / EBAY_CLIENT_SECRET / EBAY_REFRESH_TOKEN fehlen. "
            "Stelle sicher, dass diese Datei im selben Ordner wie deine .env liegt."
        )

    creds = base64.b64encode(f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}".encode()).decode()
    resp = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {creds}",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": EBAY_REFRESH_TOKEN,
            "scope": "https://api.ebay.com/oauth/api_scope https://api.ebay.com/oauth/api_scope/sell.fulfillment",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = datetime.utcnow() + timedelta(seconds=data["expires_in"] - 120)
    return _token_cache["token"]


# ---------------------------------------------------------------------------
# INTERNAL HELPERS
# ---------------------------------------------------------------------------


def _headers(call_name):
    return {
        "X-EBAY-API-SITEID": EBAY_SITE_ID,
        "X-EBAY-API-COMPATIBILITY-LEVEL": COMPATIBILITY_LEVEL,
        "X-EBAY-API-CALL-NAME": call_name,
        "Content-Type": "text/xml",
    }


def _post(call_name, xml_body):
    resp = requests.post(
        TRADING_API_ENDPOINT,
        headers=_headers(call_name),
        data=xml_body.encode("utf-8"),
        timeout=30,
    )
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY_SECONDS)
    return ET.fromstring(resp.content)


def _check_ack(root, call_name, item_id=""):
    ack = root.findtext("e:Ack", namespaces=NS)
    if ack not in ("Success", "Warning"):
        errors = []
        for err in root.findall("e:Errors", NS):
            short_msg = err.findtext("e:ShortMessage", namespaces=NS)
            long_msg = err.findtext("e:LongMessage", namespaces=NS)
            errors.append(f"{short_msg}: {long_msg}")
        raise RuntimeError(
            f"{call_name} failed for item {item_id}: " + " | ".join(errors)
        )


# ---------------------------------------------------------------------------
# GetSellerList - enumerate all active listings
# ---------------------------------------------------------------------------


def get_active_listings(page_size=100):
    """
    Yields dicts: {"item_id": ..., "title": ...} for every currently active
    listing in the account, handling pagination automatically.
    """
    page_number = 1
    while True:
        token = get_access_token()
        xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<GetSellerListRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{token}</eBayAuthToken>
  </RequesterCredentials>
  <ErrorLanguage>en_US</ErrorLanguage>
  <WarningLevel>High</WarningLevel>
  <GranularityLevel>Coarse</GranularityLevel>
  <StartTimeFrom>2026-06-01T00:00:00.000Z</StartTimeFrom>
  <StartTimeTo>2026-09-01T00:00:00.000Z</StartTimeTo>
  <IncludeWatchCount>false</IncludeWatchCount>
  <Pagination>
    <EntriesPerPage>{page_size}</EntriesPerPage>
    <PageNumber>{page_number}</PageNumber>
  </Pagination>
</GetSellerListRequest>"""

        root = _post("GetSellerList", xml_body)
        _check_ack(root, "GetSellerList")

        items = root.findall(".//e:ItemArray/e:Item", NS)
        if not items:
            break

        for item in items:
            item_id = item.findtext("e:ItemID", namespaces=NS)
            title = item.findtext("e:Title", namespaces=NS)
            selling_status = item.findtext(
                "e:SellingStatus/e:ListingStatus", namespaces=NS
            )
            if selling_status == "Active" or selling_status is None:
                yield {"item_id": item_id, "title": title}

        total_pages_str = root.findtext(
            ".//e:PaginationResult/e:TotalNumberOfPages", namespaces=NS
        )
        total_pages = int(total_pages_str) if total_pages_str else 1
        if page_number >= total_pages:
            break
        page_number += 1


# ---------------------------------------------------------------------------
# GetItem - read the current description for one listing
# ---------------------------------------------------------------------------


def get_item_description(item_id):
    """Returns (title, description_html) for a single item."""
    token = get_access_token()
    xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<GetItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{token}</eBayAuthToken>
  </RequesterCredentials>
  <ItemID>{item_id}</ItemID>
  <DetailLevel>ReturnAll</DetailLevel>
</GetItemRequest>"""

    root = _post("GetItem", xml_body)
    _check_ack(root, "GetItem", item_id)

    title = root.findtext(".//e:Item/e:Title", namespaces=NS)
    description = root.findtext(".//e:Item/e:Description", namespaces=NS) or ""
    return title, description


# ---------------------------------------------------------------------------
# ReviseItem - write the new description back
# ---------------------------------------------------------------------------


def revise_item_description(item_id, new_description_html):
    """Revises ONLY the Description field of an active listing.
    Safe for active listings with bids/watchers - revising the description
    alone (no price/quantity change) does not restart the listing."""
    token = get_access_token()

    xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<ReviseItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{token}</eBayAuthToken>
  </RequesterCredentials>
  <Item>
    <ItemID>{item_id}</ItemID>
    <Description><![CDATA[{new_description_html}]]></Description>
  </Item>
</ReviseItemRequest>"""

    root = _post("ReviseItem", xml_body)
    _check_ack(root, "ReviseItem", item_id)
    return True

