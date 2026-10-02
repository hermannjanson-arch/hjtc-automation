#!/usr/bin/env python3
"""
Einmaliges OAuth-Setup für das eBay-Verkaufskonto
===================================================
Dieses Skript muss NUR EINMAL ausgeführt werden. Es autorisiert die App,
in deinem Namen (ebay.de-Verkaufskonto) auf Bestellungen zuzugreifen und
Feedback zu vergeben. Danach läuft alles automatisch über den gespeicherten
Refresh-Token weiter (der ist ca. 18 Monate gültig, muss danach einmalig
erneuert werden).

WICHTIG: Auch wenn du den Developer-Account mit einer anderen E-Mail
(deinem Einkaufskonto) erstellt hast, ist das kein Problem. Bei Schritt 2
unten loggst du dich bewusst mit deinem ebay.de-VERKAUFSKONTO ein -
DAS Konto wird autorisiert, unabhängig vom Developer-Account.

Voraussetzung: In der eBay Developer Console (developer.ebay.com -> My
Account -> User Tokens) muss eine "RuName" (Redirect-Name) eingerichtet
sein. Siehe README.md für die genauen Schritte.
"""

import os
import base64
import webbrowser
import urllib.parse
import requests

EBAY_CLIENT_ID = os.environ.get("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.environ.get("EBAY_CLIENT_SECRET")
EBAY_RUNAME = os.environ.get("EBAY_RUNAME")  # aus der Developer Console

# Benötigte Berechtigungen (Scopes). sell.fulfillment für Bestelldaten,
# die Basis-Scope wird von der (älteren) Trading API für LeaveFeedback
# benötigt. Falls beim Autorisieren eine "invalid_scope"-Fehlermeldung
# kommt: in der Developer Console unter "User Tokens" -> "OAuth Scopes"
# prüfen, welche Scopes für deine App freigeschaltet sind, und diese
# Liste entsprechend anpassen.
SCOPES = [
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
]

if not all([EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, EBAY_RUNAME]):
    raise SystemExit(
        "Fehlende Umgebungsvariablen. Benötigt: EBAY_CLIENT_ID, "
        "EBAY_CLIENT_SECRET, EBAY_RUNAME.\n"
        "Vor dem Ausführen: set -a; source .env; set +a"
    )


def step_1_build_consent_url() -> str:
    params = {
        "client_id": EBAY_CLIENT_ID,
        "redirect_uri": EBAY_RUNAME,
        "response_type": "code",
        "scope": " ".join(SCOPES),
    }
    return "https://auth.ebay.com/oauth2/authorize?" + urllib.parse.urlencode(params)


def step_2_exchange_code(auth_code: str) -> dict:
    creds = base64.b64encode(f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}".encode()).decode()
    resp = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {creds}",
        },
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": EBAY_RUNAME,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    print("=" * 70)
    print("SCHRITT 1: Autorisierungs-Link öffnen")
    print("=" * 70)
    url = step_1_build_consent_url()
    print(f"\nÖffne diesen Link in deinem Browser:\n\n{url}\n")
    print(
        "Logg dich dort mit deinem ebay.de-VERKAUFSKONTO ein (nicht dem "
        "Einkaufskonto!) und bestätige den Zugriff.\n"
    )
    print(
        "Du wirst danach zu einer Seite weitergeleitet, deren Adresse mit "
        "'?code=...' endet (die Seite selbst kann eine Fehlermeldung/404 "
        "zeigen, das ist egal - wichtig ist nur die Adresszeile).\n"
    )

    try:
        webbrowser.open(url)
    except Exception:
        pass

    print("=" * 70)
    print("SCHRITT 2: Code aus der Adresszeile einfügen")
    print("=" * 70)
    raw = input(
        "\nFüge die komplette URL aus der Adresszeile ein (oder nur den "
        "Wert hinter 'code='):\n> "
    ).strip()

    if "code=" in raw:
        code = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)["code"][0]
    else:
        code = raw
    code = urllib.parse.unquote(code)

    print("\nTausche Code gegen Tokens...")
    tokens = step_2_exchange_code(code)

    print("\n" + "=" * 70)
    print("ERFOLG! Trag diese Zeile in deine .env-Datei ein:")
    print("=" * 70)
    print(f"\nEBAY_REFRESH_TOKEN={tokens['refresh_token']}\n")
    print(
        "Dieser Refresh-Token ist ca. 18 Monate gültig. Das Feedback-Skript "
        "holt sich damit automatisch bei Bedarf neue Access-Tokens - dieser "
        "Setup-Schritt muss danach nicht mehr wiederholt werden."
    )


if __name__ == "__main__":
    main()
