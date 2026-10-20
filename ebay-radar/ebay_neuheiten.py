#!/usr/bin/env python3
"""
HJTC Neuheiten-Radar
====================
Erkennt neue Sammelkarten-Sets, sobald die ersten Karten auf eBay auftauchen –
meist bei Händlern aus China/USA, Wochen bevor es in Deutschland Angebote gibt.

Kakawow & Co. drucken auf jede Karte einen Code wie „PTW-I-01“. Der erste Teil
(PTW = Phantom Twilight) steht für das Set. Taucht ein Präfix auf, das noch nie
gesehen wurde, ist ein neues Set (oder ein neues Insert) unterwegs.

Ablauf (per systemd-Timer, alle 6 Stunden):
  1. Neueste Angebote je Hersteller-Suchbegriff auf eBay USA, UK und DE holen.
  2. Code-Präfixe aus den Titeln ziehen, Set-Namen aus den häufigsten Titelwörtern ableiten.
  3. Neues Präfix (>= MIN_ANGEBOTE Angebote) -> Telegram-Meldung mit Ländern, Preisen, Beispielen.
  4. Montags: Wochenübersicht der Sets der letzten 90 Tage (wächst das Angebot? schon Konkurrenz in DE?).

Aufruf:
  python ebay_neuheiten.py              normaler Lauf
  python ebay_neuheiten.py --test       nur Ausgabe, nichts senden, nichts speichern
  python ebay_neuheiten.py --woche      Wochenübersicht sofort
"""
import os, sys, re, json, time, base64, logging, collections
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests

HERE = Path(__file__).resolve().parent
REGISTER = HERE / 'neuheiten_register.json'
BERLIN = ZoneInfo('Europe/Berlin')

# Hersteller mit Karten-Codes im Titel. Weitere einfach ergänzen.
SUCHEN = ['kakawow', 'card.fun', 'cardfun', 'kayou']
MARKTPLAETZE = ['EBAY_US', 'EBAY_GB', 'EBAY_DE']
SEITEN = 5                     # je 200 neueste Angebote
MIN_ANGEBOTE = 2               # ab so vielen Angeboten gilt ein Präfix als echt (Tippfehler ausfiltern)
BEOBACHTEN_TAGE = 90           # Sets so lange in der Wochenübersicht verfolgen

CODE = re.compile(r'\b([A-Z]{2,5})-([A-Z]{1,6})-?(\d{1,3})\b')
BOX = re.compile(r'\b(box|hobby|blaster|booster|pack|packs|case|display|sealed|ovp)\b', re.I)
STOP = set('kakawow card cards trading tcg the of and a an no nr new rare holo foil refractor base insert parallel /'.split())

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('neuheiten')


def token():
    creds = base64.b64encode(f"{os.environ['EBAY_CLIENT_ID']}:{os.environ['EBAY_CLIENT_SECRET']}".encode()).decode()
    r = requests.post('https://api.ebay.com/identity/v1/oauth2/token', timeout=20,
                      headers={'Content-Type': 'application/x-www-form-urlencoded', 'Authorization': f'Basic {creds}'},
                      data={'grant_type': 'client_credentials', 'scope': 'https://api.ebay.com/oauth/api_scope'})
    r.raise_for_status()
    return r.json()['access_token']


def hole_angebote(tok):
    items = {}
    for q in SUCHEN:
        for mp in MARKTPLAETZE:
            for s in range(SEITEN):
                r = requests.get('https://api.ebay.com/buy/browse/v1/item_summary/search', timeout=60,
                                 params={'q': q, 'limit': 200, 'offset': s * 200, 'sort': 'newlyListed'},
                                 headers={'Authorization': f'Bearer {tok}', 'X-EBAY-C-MARKETPLACE-ID': mp})
                if r.status_code != 200:
                    log.warning('%s %s: %s', q, mp, r.status_code)
                    break
                j = r.json()
                for it in j.get('itemSummaries', []):
                    items[it['itemId']] = {
                        'titel': it.get('title', ''), 'land': (it.get('itemLocation') or {}).get('country', '?'),
                        'preis': float(it['price']['value']), 'waehrung': it['price']['currency'],
                        'verkaeufer': (it.get('seller') or {}).get('username', ''), 'url': it.get('itemWebUrl', ''),
                        'neu': it.get('itemCreationDate', '')[:10], 'suche': q}
                if (s + 1) * 200 >= j.get('total', 0):
                    break
                time.sleep(0.2)
    return items


def set_name(titel_liste):
    """Set-Name = Wörter, die in mindestens 60 % der Titel vorkommen, in typischer Reihenfolge."""
    zaehler, pos = collections.Counter(), collections.defaultdict(list)
    for t in titel_liste:
        w = [x for x in re.findall(r"[A-Za-z0-9][A-Za-z0-9.'&]*", t) if not CODE.match(x)]
        gesehen = set()
        for i, x in enumerate(w):
            k = x.lower()
            if k in STOP or k in gesehen or re.fullmatch(r'\d{1,3}', k):
                continue
            gesehen.add(k); zaehler[k] += 1; pos[k].append(i / max(len(w), 1))
    n = len(titel_liste)
    haeufig = [k for k, c in zaehler.items() if c >= max(2, 0.6 * n)]
    haeufig.sort(key=lambda k: sum(pos[k]) / len(pos[k]))
    return ' '.join(k.capitalize() if not k.isdigit() else k for k in haeufig[:7]) or '(unklar)'


def auswerten(items):
    """Je Präfix: Anzahl, Länder, Preise (Einzelkarten in EUR/USD/GBP getrennt), Beispiele, Set-Name."""
    pre = {}
    for iid, it in items.items():
        for p in {m.group(1) for m in CODE.finditer(it['titel'])}:
            o = pre.setdefault(p, {'ids': [], 'titel': [], 'laender': collections.Counter(), 'verkaeufer': set(),
                                   'preise': collections.defaultdict(list), 'erst': '9999', 'jahre': collections.Counter()})
            o['ids'].append(iid); o['titel'].append(it['titel']); o['laender'][it['land']] += 1
            o['verkaeufer'].add(it['verkaeufer']); o['erst'] = min(o['erst'], it['neu'] or '9999')
            for y in re.findall(r'\b(20[12]\d)\b', it['titel']):
                o['jahre'][y] += 1
            if not BOX.search(it['titel']):
                o['preise'][it['waehrung']].append(it['preis'])
    for p, o in pre.items():
        o['name'] = set_name(o['titel'])
        o['jahr'] = o['jahre'].most_common(1)[0][0] if o['jahre'] else ''
    return pre


def preis_text(o):
    teile = []
    for w, v in o['preise'].items():
        v = sorted(v)
        teile.append(f"{w} {v[0]:.2f}–{v[-1]:.2f} (Median {v[len(v) // 2]:.2f})")
    return ', '.join(teile) or '–'


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def telegram(text, test):
    if test:
        print('\n--- TELEGRAM ---\n' + text)
        return
    r = requests.post(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage", timeout=30,
                      data={'chat_id': os.environ['TELEGRAM_CHAT_ID'], 'text': text[:4000], 'parse_mode': 'HTML',
                            'disable_web_page_preview': 'true'})
    if not r.ok:
        log.error('Telegram: %s %s', r.status_code, r.text[:200])


def lade_register():
    try:
        return json.loads(REGISTER.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def speichere_register(reg):
    tmp = REGISTER.with_suffix('.tmp')
    tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=1))
    tmp.replace(REGISTER)


def lauf(test):
    items = hole_angebote(token())
    pre = auswerten(items)
    reg = lade_register()
    erster_lauf = not reg
    heute = datetime.now(BERLIN).strftime('%Y-%m-%d')
    neu = []
    for p, o in pre.items():
        e = reg.get(p)
        if e is None:
            if len(o['ids']) < MIN_ANGEBOTE:
                continue
            e = reg[p] = {'name': o['name'], 'jahr': o['jahr'], 'erstmals': heute, 'verlauf': {}}
            if not erster_lauf:
                neu.append((p, o))
        e['name'] = o['name'] if len(o['ids']) >= 3 else e['name']
        e['jahr'] = o['jahr'] or e.get('jahr', '')
        e['verlauf'][heute] = {'angebote': len(o['ids']), 'de': o['laender'].get('DE', 0),
                               'verkaeufer_de': len({items[i]['verkaeufer'] for i in o['ids'] if items[i]['land'] == 'DE'}),
                               'laender': dict(o['laender'])}
    log.info('%s Angebote, %s Präfixe, %s neu%s', len(items), len(pre), len(neu), ' (Erstlauf: nur registriert)' if erster_lauf else '')
    for p, o in sorted(neu, key=lambda x: -len(x[1]['ids'])):
        bsp = [i for i in o['ids'] if not BOX.search(items[i]['titel'])][:3] or o['ids'][:3]
        laender = ', '.join(f'{k} {v}' for k, v in o['laender'].most_common())
        de = o['laender'].get('DE', 0)
        telegram(f"🆕 <b>Neues Set entdeckt: {esc(p)}</b>\n<b>{esc(o['name'])}</b>{' (' + o['jahr'] + ')' if o['jahr'] else ''}\n"
                 f"{len(o['ids'])} Angebote · {laender} · {len(o['verkaeufer'])} Verkäufer\n"
                 f"Einzelkarten: {preis_text(o)}\n"
                 f"{'🟢 Noch kein Angebot in DE – Frühstarter-Chance' if de == 0 else f'🟡 Schon {de} Angebote in DE'}\n"
                 + '\n'.join(f"• {esc(items[i]['titel'][:80])}\n  {items[i]['url']}" for i in bsp), test)
    # Verlauf kurz halten
    grenze = (datetime.now(BERLIN) - timedelta(days=BEOBACHTEN_TAGE + 30)).strftime('%Y-%m-%d')
    for e in reg.values():
        e['verlauf'] = {d: v for d, v in e['verlauf'].items() if d >= grenze}
    if not test:
        speichere_register(reg)
    return reg


def wochenuebersicht(reg, test):
    """Sets der letzten 90 Tage: Angebot gesamt vs. DE, Trend zur Vorwoche."""
    heute = datetime.now(BERLIN).date()
    zeilen = []
    for p, e in reg.items():
        if not e['erstmals'] or (heute - datetime.strptime(e['erstmals'], '%Y-%m-%d').date()).days > BEOBACHTEN_TAGE:
            continue
        tage = sorted(e['verlauf'])
        if not tage:
            continue
        jetzt = e['verlauf'][tage[-1]]
        vor = next((e['verlauf'][d] for d in reversed(tage) if d <= (heute - timedelta(days=7)).isoformat()), None)
        trend = f"{jetzt['angebote'] - vor['angebote']:+d}" if vor else 'neu'
        zeilen.append((jetzt['angebote'], f"<b>{esc(p)}</b> {esc(e['name'][:45])} · seit {e['erstmals'][8:10]}.{e['erstmals'][5:7]}. · "
                                         f"{jetzt['angebote']} Angebote ({trend} z. Vorwoche) · DE {jetzt['de']} von {jetzt['verkaeufer_de']} Verkäufern"))
    if not zeilen:
        return
    zeilen.sort(key=lambda z: -z[0])
    telegram('📈 <b>Neue Sets – Wochenübersicht</b> (letzte 90 Tage)\nViel Angebot weltweit, wenig in DE = Fenster offen.\n\n'
             + '\n'.join(z for _, z in zeilen[:25]), test)


def main():
    test = '--test' in sys.argv
    reg = lauf(test) if '--woche' not in sys.argv else lade_register()
    jetzt = datetime.now(BERLIN)
    if '--woche' in sys.argv or (jetzt.weekday() == 0 and 6 <= jetzt.hour < 12):
        wochenuebersicht(reg, test)


if __name__ == '__main__':
    main()
