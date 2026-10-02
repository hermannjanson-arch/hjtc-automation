#!/usr/bin/env python3
"""
eBay Sammelkarten-Watcher
==========================
Durchsucht eBay laufend nach neuen Angeboten (mehrere Suchprofile gleichzeitig)
und schickt Treffer sofort per Telegram.

Läuft in einer Endlosschleife (kein Cronjob) -> für echten 24/7-Betrieb per
systemd-Service starten (siehe README.md).

Konfiguration: alles Wichtige steht unten im Abschnitt "KONFIGURATION".
Zugangsdaten (App-ID, Secret, Telegram-Token) kommen aus Umgebungsvariablen,
NICHT im Code eintragen (siehe README.md / .env.example).
"""

import os
import time
import json
import base64
import logging
import requests
from pathlib import Path
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# KONFIGURATION
# ---------------------------------------------------------------------------

# Wie oft neu geprüft wird (Sekunden).
# Bei 3 Suchen und 90s Intervall: ca. 2.880 Calls/Tag (58% von 5.000/Tag) ->
# lässt bewusst Spielraum, um später weitere Suchen hinzuzufügen.
POLL_INTERVAL_SECONDS = 90

# Datei, in der bereits gesehene Artikel gespeichert werden, damit nach einem
# Neustart keine doppelten Benachrichtigungen kommen.
SEEN_ITEMS_FILE = Path(__file__).parent / "seen_items.json"
# Einträge älter als X Tage werden aus der Seen-Liste entfernt, damit die
# Datei nicht unbegrenzt wächst.
SEEN_ITEMS_MAX_AGE_DAYS = 14

# Deine Suchprofile. Für jedes Profil: eigene Keywords, optionale Preisgrenze.
# Die Zustellung erfolgt NICHT pro Kategorie, sondern automatisch getrennt nach
# Angebotstyp: Sofortkauf-Funde gehen an TELEGRAM_CHAT_ID_FIXED, Auktionen an
# TELEGRAM_CHAT_ID_AUCTION (beide in der .env-Datei festgelegt).
SEARCHES = [
    {
        "name": "Emma Watson Costume Card",
        "query": "emma watson costume card",
        "marketplace": "EBAY_US",
        "max_price": None,
        "buying_options": ["FIXED_PRICE", "AUCTION"],
        "exclude_keywords": ["proxy", "custom", "fake", "reprint"],
    },
    {
        "name": "Artbox Harry Potter Prop Card",
        "query": "artbox harry potter prop card",
        "marketplace": "EBAY_US",
        "max_price": None,
        "buying_options": ["FIXED_PRICE", "AUCTION"],
        "exclude_keywords": ["proxy", "custom", "fake", "reprint"],
    },
    {
        "name": "Artbox Harry Potter Costume Card",
        "query": "artbox harry potter costume card",
        "marketplace": "EBAY_US",
        "max_price": None,
        "buying_options": ["FIXED_PRICE", "AUCTION"],
        "exclude_keywords": ["proxy", "custom", "fake", "reprint"],
    },
]

# ---------------------------------------------------------------------------
# Ende Konfiguration - ab hier normalerweise nichts anfassen
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("ebay-watcher")

EBAY_CLIENT_ID = os.environ.get("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.environ.get("EBAY_CLIENT_SECRET")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID_DEFAULT = os.environ.get("TELEGRAM_CHAT_ID")

if not all([EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID_DEFAULT]):
    raise SystemExit(
        "Fehlende Umgebungsvariablen. Benötigt werden mindestens:\n"
        "  EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID\n"
        "Siehe README.md."
    )

_token_cache = {"token": None, "expires_at": datetime.min}


def get_ebay_token() -> str:
    """Holt (und cached) ein OAuth Application Token für die Browse API."""
    if _token_cache["token"] and datetime.utcnow() < _token_cache["expires_at"]:
        return _token_cache["token"]

    creds = base64.b64encode(f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}".encode()).decode()
    resp = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {creds}",
        },
        data={
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["token"] = data["access_token"]
    # etwas Puffer abziehen, damit wir nicht mit einem gerade abgelaufenen Token arbeiten
    _token_cache["expires_at"] = datetime.utcnow() + timedelta(seconds=data["expires_in"] - 120)
    log.info("Neues eBay-Token geholt (gültig %s Sek.)", data["expires_in"])
    return _token_cache["token"]


def search_ebay(search: dict) -> list[dict]:
    """Fragt die eBay Browse API für ein Suchprofil ab, sortiert nach 'neueste zuerst'."""
    token = get_ebay_token()
    params = {
        "q": search["query"],
        "sort": "newlyListed",
        "limit": "50",
    }
    filters = []
    if search.get("buying_options"):
        filters.append(f"buyingOptions:{{{'|'.join(search['buying_options'])}}}")
    if search.get("max_price"):
        filters.append(f"price:[..{search['max_price']}]")
        filters.append("priceCurrency:EUR")
    if filters:
        params["filter"] = ",".join(filters)

    resp = requests.get(
        "https://api.ebay.com/buy/browse/v1/item_summary/search",
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": search.get("marketplace", "EBAY_US"),
        },
        params=params,
        timeout=15,
    )
    if resp.status_code == 401:
        # Token abgelaufen -> einmal neu holen und retryen
        _token_cache["token"] = None
        token = get_ebay_token()
        resp = requests.get(
            "https://api.ebay.com/buy/browse/v1/item_summary/search",
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": search.get("marketplace", "EBAY_US"),
            },
            params=params,
            timeout=15,
        )
    resp.raise_for_status()
    return resp.json().get("itemSummaries", [])


def load_seen_ids() -> dict:
    if SEEN_ITEMS_FILE.exists():
        try:
            return json.loads(SEEN_ITEMS_FILE.read_text())
        except json.JSONDecodeError:
            log.warning("seen_items.json beschädigt, starte mit leerer Liste.")
    return {}


def save_seen_ids(seen: dict) -> None:
    cutoff = datetime.utcnow() - timedelta(days=SEEN_ITEMS_MAX_AGE_DAYS)
    cleaned = {
        item_id: ts for item_id, ts in seen.items()
        if datetime.fromisoformat(ts) > cutoff
    }
    SEEN_ITEMS_FILE.write_text(json.dumps(cleaned))


def matches_excludes(item: dict, exclude_keywords: list[str]) -> bool:
    title = (item.get("title") or "").lower()
    return any(kw.lower() in title for kw in exclude_keywords)


def send_telegram(text: str, chat_id: str) -> None:
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=15,
    )
    if not resp.ok:
        log.error("Telegram-Fehler: %s %s", resp.status_code, resp.text)


def format_message(item: dict, category: str) -> str:
    title = item.get("title", "Ohne Titel")
    price = item.get("price", {})
    price_str = f"{price.get('value', '?')} {price.get('currency', '')}"
    condition = item.get("condition", "unbekannt")
    listing_type = "Auktion" if "AUCTION" in item.get("buyingOptions", []) else "Sofortkauf"
    link = item.get("itemWebUrl", "")
    return (
        f"🔔 <b>{category}</b>\n"
        f"{title}\n"
        f"💶 {price_str} · {listing_type} · {condition}\n"
        f"{link}"
    )


def run_once(seen: dict) -> None:
    for search in SEARCHES:
        try:
            items = search_ebay(search)
        except requests.RequestException as e:
            log.error("Fehler bei Suche '%s': %s", search["name"], e)
            continue

        for item in items:
            item_id = item.get("itemId")
            if not item_id or item_id in seen:
                continue
            if matches_excludes(item, search.get("exclude_keywords", [])):
                seen[item_id] = datetime.utcnow().isoformat()
                continue

            is_auction = "AUCTION" in item.get("buyingOptions", [])
            chat_env = "TELEGRAM_CHAT_ID_AUCTION" if is_auction else "TELEGRAM_CHAT_ID_FIXED"
            chat_id = os.environ.get(chat_env, TELEGRAM_CHAT_ID_DEFAULT)

            message = format_message(item, search["name"])
            send_telegram(message, chat_id)
            log.info("Gesendet [%s]: %s", search["name"], item.get("title"))
            seen[item_id] = datetime.utcnow().isoformat()


def main() -> None:
    log.info("eBay-Watcher gestartet. Prüfe alle %s Sekunden.", POLL_INTERVAL_SECONDS)
    seen = load_seen_ids()
    while True:
        run_once(seen)
        save_seen_ids(seen)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
