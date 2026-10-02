#!/usr/bin/env python3
"""
eBay Automatisches Feedback
=============================
Prüft laufend deine Bestellungen. Sobald eine Bestellung als BEZAHLT markiert
ist und noch kein Feedback dafür vergeben wurde, wird automatisch eine
positive Bewertung abgegeben - auf Deutsch für Käufer aus DE/AT/CH, sonst
auf Englisch. Der Text wird zufällig aus mehreren Varianten gewählt.

SICHERHEIT: Startet im DRY_RUN-Modus (siehe Konfiguration unten). Im
Dry-Run wird NICHTS an eBay gesendet, du bekommst nur eine Telegram-Nachricht,
was das Skript tun WÜRDE. Erst wenn du das eine Weile beobachtet und für
korrekt befunden hast, DRY_RUN auf False stellen.

Voraussetzung: ebay_oauth_setup.py wurde einmalig ausgeführt und
EBAY_REFRESH_TOKEN steht in der .env-Datei.

HINWEIS ZUR TRADING API: Die eigentliche Feedback-Vergabe läuft über eBays
älteres XML-basiertes "Trading API" (LeaveFeedback-Call), da es dafür keine
moderne REST-Alternative gibt. Diese Schnittstelle ist seit Jahren stabil,
aber falls sich an den genauen Feldnamen etwas geändert haben sollte, meldet
das Skript einen klaren Fehler statt stillschweigend zu scheitern - schau in
diesem Fall in die Logs (journalctl) und wir passen es gemeinsam an.
"""

import os
import time
import json
import base64
import random
import logging
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# KONFIGURATION
# ---------------------------------------------------------------------------

# SICHERHEITSSCHALTER: Solange True, wird NICHTS wirklich an eBay gesendet,
# nur eine Telegram-Vorschau. Gesteuert über DRY_RUN in der .env
# (true/false). Fehlt die Variable, gilt False (= LIVE).
DRY_RUN = os.environ.get("DRY_RUN", "false").strip().strip("\"'").lower() in ("1", "true", "yes", "on")

POLL_INTERVAL_SECONDS = 3600  # stündlich reicht völlig, Bestellungen sind nicht zeitkritisch

PROCESSED_ORDERS_FILE = Path(__file__).parent / "feedback_given.json"
PROCESSED_ORDERS_MAX_AGE_DAYS = 120

# Länder, für die auf Deutsch bewertet wird - alle anderen bekommen Englisch.
# Enthält sowohl ISO-Ländercodes (falls doch mal eine Adresse mitkommt) als
# auch eBays 'Site'-Bezeichnungen (der übliche Fall, siehe get_buyer_registration_country).
GERMAN_SPEAKING_COUNTRIES = {"DE", "AT", "CH", "GERMANY", "AUSTRIA", "SWITZERLAND"}

FEEDBACK_TEXTS_DE = [
    "Vielen Dank für die unkomplizierte, angenehme Transaktion. Ausgezeichneter Käufer. 1+",
    "Tolle Kommunikation, eine Freude, mit Ihnen Geschäfte zu machen.",
    "Guter Käufer, prompte Zahlung, geschätzter Kunde, sehr zu empfehlen.",
    "Schnelle Reaktion, schnelle Zahlung. Perfekt! Danke!",
    "Hoffe auf weitere Geschäfte mit Ihnen. Vielen Dank!",
]

FEEDBACK_TEXTS_EN = [
    "Thank you for an easy, pleasant transaction. Excellent buyer. A+",
    "Great communication, a pleasure to do business with.",
    "Good buyer, prompt payment, valued customer, highly recommended.",
    "Quick response and fast payment. Perfect! Thanks!",
    "Hope to deal with you again. Thank you!",
]

# ---------------------------------------------------------------------------
# Ende Konfiguration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("ebay-feedback")

EBAY_CLIENT_ID = os.environ.get("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.environ.get("EBAY_CLIENT_SECRET")
EBAY_REFRESH_TOKEN = os.environ.get("EBAY_REFRESH_TOKEN")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID_DEFAULT = os.environ.get("TELEGRAM_CHAT_ID")
TELEGRAM_CHAT_ID_FEEDBACK = os.environ.get("TELEGRAM_CHAT_ID_FEEDBACK", TELEGRAM_CHAT_ID_DEFAULT)

if not all([EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, EBAY_REFRESH_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID_DEFAULT]):
    raise SystemExit(
        "Fehlende Umgebungsvariablen. Benötigt: EBAY_CLIENT_ID, "
        "EBAY_CLIENT_SECRET, EBAY_REFRESH_TOKEN, TELEGRAM_BOT_TOKEN, "
        "TELEGRAM_CHAT_ID.\nEBAY_REFRESH_TOKEN kommt aus ebay_oauth_setup.py."
    )

_token_cache = {"token": None, "expires_at": datetime.min}


def get_access_token() -> str:
    """Holt (und cached) ein User-Access-Token via Refresh-Token."""
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


def fetch_paid_orders() -> list[dict]:
    """Holt aktuelle Bestellungen über die Sell Fulfillment API (ungefiltert;
    der Bezahlstatus wird anschließend in run_once() geprüft)."""
    token = get_access_token()
    resp = requests.get(
        "https://api.ebay.com/sell/fulfillment/v1/order",
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_DE",
        },
        params={
            "limit": "50",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("orders", [])


def get_buyer_registration_country(buyer_username: str) -> str:
    """Holt das tatsächliche Registrierungsland des Käufer-Kontos über die
    Trading API (GetUser). Robuster als die Lieferadresse, die durch
    Versand-Konsolidierer wie SpeedPAK ein falsches Land zeigen kann
    (Paket geht dann z.B. erst an ein Sammellager in einem anderen Land)."""
    try:
        token = get_access_token()
        xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<GetUserRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <UserID>{buyer_username}</UserID>
</GetUserRequest>"""
        headers = {
            "X-EBAY-API-SITEID": "77",
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1193",
            "X-EBAY-API-CALL-NAME": "GetUser",
            "X-EBAY-API-IAF-TOKEN": token,
            "Content-Type": "text/xml",
        }
        resp = requests.post(
            "https://api.ebay.com/ws/api.dll",
            headers=headers,
            data=xml_body.encode("utf-8"),
            timeout=15,
        )
        resp.raise_for_status()
        ns = {"e": "urn:ebay:apis:eBLBaseComponents"}
        root = ET.fromstring(resp.text)
        if root.findtext("e:Ack", default="", namespaces=ns) not in ("Success", "Warning"):
            long_msg = root.findtext(".//e:LongMessage", default="unbekannter Fehler", namespaces=ns)
            log.warning("GetUser für '%s' fehlgeschlagen: %s", buyer_username, long_msg)
            return ""
        country = root.findtext(".//e:User/e:RegistrationAddress/e:Country", default="", namespaces=ns)
        if country:
            return country.upper()
        # Fallback: eBay liefert RegistrationAddress nicht immer mit, aber das
        # 'Site'-Feld (registriertes eBay-Länderportal) ist stets vorhanden.
        site = root.findtext(".//e:User/e:Site", default="", namespaces=ns)
        return site.upper()
    except (requests.RequestException, RuntimeError) as e:
        log.warning("Registrierungsland für '%s' konnte nicht ermittelt werden: %s", buyer_username, e)
        return ""


def pick_feedback_text(country: str) -> str:
    if country in GERMAN_SPEAKING_COUNTRIES:
        return random.choice(FEEDBACK_TEXTS_DE)
    return random.choice(FEEDBACK_TEXTS_EN)


def get_transaction_id(order_id: str, item_id: str) -> str | None:
    """Holt die TransactionID über die Trading API (GetOrders) - zuverlässiger
    als das REST-Feld 'legacyTransactionId', das eBay nicht immer mitliefert."""
    token = get_access_token()
    xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<GetOrdersRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <OrderIDArray><OrderID>{order_id}</OrderID></OrderIDArray>
  <OrderRole>Seller</OrderRole>
</GetOrdersRequest>"""
    headers = {
        "X-EBAY-API-SITEID": "77",
        "X-EBAY-API-COMPATIBILITY-LEVEL": "1193",
        "X-EBAY-API-CALL-NAME": "GetOrders",
        "X-EBAY-API-IAF-TOKEN": token,
        "Content-Type": "text/xml",
    }
    resp = requests.post(
        "https://api.ebay.com/ws/api.dll",
        headers=headers,
        data=xml_body.encode("utf-8"),
        timeout=15,
    )
    resp.raise_for_status()
    ns = {"e": "urn:ebay:apis:eBLBaseComponents"}
    root = ET.fromstring(resp.text)

    if root.findtext("e:Ack", default="", namespaces=ns) not in ("Success", "Warning"):
        long_msg = root.findtext(".//e:LongMessage", default="unbekannter Fehler", namespaces=ns)
        raise RuntimeError(f"GetOrder fehlgeschlagen: {long_msg}")

    for txn in root.findall(".//e:TransactionArray/e:Transaction", ns):
        txn_item_id = txn.findtext("e:Item/e:ItemID", default="", namespaces=ns)
        if txn_item_id == item_id:
            return txn.findtext("e:TransactionID", default=None, namespaces=ns)

    # Fallback: falls kein exakter Item-Match, erste gefundene TransactionID nehmen
    first = root.find(".//e:TransactionArray/e:Transaction/e:TransactionID", ns)
    return first.text if first is not None else None


def leave_feedback(item_id: str, transaction_id: str, buyer_username: str, comment: str) -> None:
    """Vergibt Feedback über die (XML-basierte) Trading API."""
    token = get_access_token()
    xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<LeaveFeedbackRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <ItemID>{item_id}</ItemID>
  <TransactionID>{transaction_id}</TransactionID>
  <TargetUser>{buyer_username}</TargetUser>
  <CommentType>Positive</CommentType>
  <CommentText>{comment}</CommentText>
  <Role>Seller</Role>
</LeaveFeedbackRequest>"""

    headers = {
        "X-EBAY-API-SITEID": "77",  # 77 = eBay.de
        "X-EBAY-API-COMPATIBILITY-LEVEL": "1193",
        "X-EBAY-API-CALL-NAME": "LeaveFeedback",
        "X-EBAY-API-IAF-TOKEN": token,
        "Content-Type": "text/xml",
    }
    resp = requests.post(
        "https://api.ebay.com/ws/api.dll",
        headers=headers,
        data=xml_body.encode("utf-8"),
        timeout=15,
    )
    resp.raise_for_status()
    if "<Ack>Success</Ack>" not in resp.text and "<Ack>Warning</Ack>" not in resp.text:
        raise RuntimeError(f"eBay meldete keinen Erfolg: {resp.text[:500]}")


def send_telegram(text: str) -> None:
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data={
            "chat_id": TELEGRAM_CHAT_ID_FEEDBACK,
            "text": text,
            "parse_mode": "HTML",
        },
        timeout=15,
    )
    if not resp.ok:
        log.error("Telegram-Fehler: %s %s", resp.status_code, resp.text)


def load_processed() -> dict:
    if PROCESSED_ORDERS_FILE.exists():
        try:
            return json.loads(PROCESSED_ORDERS_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_processed(processed: dict) -> None:
    cutoff = datetime.utcnow() - timedelta(days=PROCESSED_ORDERS_MAX_AGE_DAYS)
    cleaned = {k: v for k, v in processed.items() if datetime.fromisoformat(v) > cutoff}
    PROCESSED_ORDERS_FILE.write_text(json.dumps(cleaned))


def run_once(processed: dict) -> None:
    try:
        orders = fetch_paid_orders()
    except requests.RequestException as e:
        log.error("Fehler beim Abrufen der Bestellungen: %s", e)
        return

    for order in orders:
        order_id = order.get("orderId")
        if not order_id or order_id in processed:
            continue
        if order.get("orderPaymentStatus") != "PAID":
            continue

        buyer_username = order.get("buyer", {}).get("username", "unbekannt")
        country = get_buyer_registration_country(buyer_username)
        comment = pick_feedback_text(country)

        line_items = order.get("lineItems", [])
        if not line_items:
            continue
        item_id = line_items[0].get("legacyItemId")

        if DRY_RUN:
            send_telegram(
                f"🧪 <b>DRY RUN – würde Feedback senden</b>\n"
                f"Käufer: {buyer_username} ({country or 'Land unbekannt'})\n"
                f"Bestellung: {order_id}\n"
                f"Text: {comment}"
            )
            log.info("[DRY RUN] Würde Feedback senden für Order %s", order_id)
        else:
            if not item_id:
                log.warning("Order %s: fehlende Item-ID, überspringe.", order_id)
                continue
            try:
                transaction_id = get_transaction_id(order_id, item_id)
            except (requests.RequestException, RuntimeError) as e:
                log.error("Order %s: TransactionID konnte nicht ermittelt werden: %s", order_id, e)
                send_telegram(f"⚠️ Feedback fehlgeschlagen (TransactionID) für Order {order_id}: {e}")
                continue
            if not transaction_id:
                log.warning("Order %s: keine TransactionID gefunden, überspringe.", order_id)
                continue
            try:
                leave_feedback(item_id, transaction_id, buyer_username, comment)
                send_telegram(
                    f"✅ <b>Feedback gesendet</b>\n"
                    f"Käufer: {buyer_username} ({country or 'Land unbekannt'})\n"
                    f"Text: {comment}"
                )
                log.info("Feedback gesendet für Order %s", order_id)
            except (requests.RequestException, RuntimeError) as e:
                log.error("Feedback für Order %s fehlgeschlagen: %s", order_id, e)
                send_telegram(f"⚠️ Feedback fehlgeschlagen für Order {order_id}: {e}")
                continue

        processed[order_id] = datetime.utcnow().isoformat()


def main() -> None:
    mode = "DRY RUN (Test, sendet nichts)" if DRY_RUN else "LIVE (sendet echtes Feedback!)"
    log.info("eBay-Feedback-Bot gestartet im Modus: %s", mode)
    processed = load_processed()
    while True:
        run_once(processed)
        save_processed(processed)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
