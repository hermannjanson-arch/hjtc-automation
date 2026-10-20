#!/usr/bin/env python3
"""Morgen-Zusammenfassung per Telegram (täglich 07:30 Berlin): Verkäufe von gestern, Neuigkeiten, To-dos, Systemstatus.
Ersetzt die vielen Einzelmeldungen von Neuheiten-Radar und Verkaufs-Sync (dringende Meldungen kommen weiter sofort)."""
import json, os, sys, base64, subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone
import requests

sys.path.insert(0, str(Path.home() / 'ebay-status'))
import ereignisse


def bestellungen_24h():
    creds = base64.b64encode(f"{os.environ['EBAY_CLIENT_ID']}:{os.environ['EBAY_CLIENT_SECRET']}".encode()).decode()
    tok = requests.post('https://api.ebay.com/identity/v1/oauth2/token', timeout=20,
                        headers={'Content-Type': 'application/x-www-form-urlencoded', 'Authorization': f'Basic {creds}'},
                        data={'grant_type': 'refresh_token', 'refresh_token': os.environ['EBAY_REFRESH_TOKEN'],
                              'scope': 'https://api.ebay.com/oauth/api_scope https://api.ebay.com/oauth/api_scope/sell.fulfillment'}).json()['access_token']
    von = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    r = requests.get('https://api.ebay.com/sell/fulfillment/v1/order', timeout=30, params={'filter': f'creationdate:[{von}..]', 'limit': 50},
                     headers={'Authorization': f'Bearer {tok}', 'X-EBAY-C-MARKETPLACE-ID': 'EBAY_DE'})
    r.raise_for_status()
    zeilen, summe = [], 0.0
    for o in r.json().get('orders', []):
        if o.get('orderPaymentStatus') != 'PAID':
            continue
        for li in o.get('lineItems', []):
            w = float(li['lineItemCost']['value']); summe += w
            zeilen.append(f"• {li.get('title', '')[:60]} · {eur(w)}")
    return zeilen, summe


def eur(x):
    return f'{x:,.2f} €'.replace(',', 'X').replace('.', ',').replace('X', '.')


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def main():
    test = '--test' in sys.argv
    teile = [f"☀️ <b>HJTC Morgenbericht {datetime.now():%d.%m.%Y}</b>"]
    try:
        z, s = bestellungen_24h()
        teile.append(f"\n<b>Verkäufe letzte 24 Std.:</b> {len(z)} · {eur(s)}" + ('\n' + '\n'.join(esc(x) for x in z) if z else ''))
    except Exception as e:
        teile.append(f"\nVerkäufe: konnten nicht geladen werden ({esc(str(e))[:100]})")
    ev, gesehen = [], set()
    for e in ereignisse.lesen(24):            # doppelte Texte nur einmal zeigen
        if (e['art'], e['text']) not in gesehen:
            gesehen.add((e['art'], e['text'])); ev.append(e)
    aktion = [e for e in ev if e['art'] == 'aktion']
    info = [e for e in ev if e['art'] == 'info']
    fehler = [e for e in ev if e['art'] == 'fehler']
    if aktion:
        teile.append('\n<b>📌 Zu tun:</b>\n' + '\n'.join(esc(e['text']) for e in aktion[:15]))
    if info:
        teile.append('\n<b>ℹ️ Neuigkeiten:</b>\n' + '\n'.join(esc(e['text']) for e in info[:20]))
    status = json.loads(subprocess.run([sys.executable, str(Path.home() / 'ebay-status' / 'status.py')], capture_output=True, text=True).stdout)
    kaputt = [d['name'] for d in status['dienste'] if not d['ok'] or d.get('fehler_24h')]
    teile.append('\n<b>Systeme:</b> ' + ('alle laufen ✅' if not kaputt else '⚠️ prüfen: ' + ', '.join(kaputt)) +
                 (f" · {len(fehler)} Fehlermeldungen" if fehler else ''))
    teile.append('\nDetails im Tresorraum auf dem Mac (Schreibtisch: „HJTC Tresorraum“).')
    text = '\n'.join(teile)
    if test:
        print(text)
        return
    requests.post(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage", timeout=30,
                  data={'chat_id': os.environ['TELEGRAM_CHAT_ID'], 'text': text[:4000], 'parse_mode': 'HTML', 'disable_web_page_preview': 'true'})
    ereignisse.aufraeumen()


if __name__ == '__main__':
    main()
