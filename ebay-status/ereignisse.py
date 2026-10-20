"""Gemeinsames Ereignis-Protokoll aller HJTC-Dienste (~/ebay-status/ereignisse.jsonl).

art: 'info' (nur Morgenbericht/Cockpit), 'aktion' (du musst etwas tun), 'fehler'.
Eingebunden per sys.path in ebay-radar und ebay-sync.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

DATEI = Path.home() / 'ebay-status' / 'ereignisse.jsonl'


def melden(quelle, art, text, **extra):
    DATEI.parent.mkdir(exist_ok=True)
    with DATEI.open('a') as f:
        f.write(json.dumps({'zeit': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'quelle': quelle,
                            'art': art, 'text': text, **extra}, ensure_ascii=False) + '\n')


def lesen(stunden=24 * 7):
    if not DATEI.exists():
        return []
    grenze = datetime.now(timezone.utc).timestamp() - stunden * 3600
    out = []
    for z in DATEI.read_text().splitlines():
        try:
            e = json.loads(z)
            if datetime.fromisoformat(e['zeit']).timestamp() >= grenze:
                out.append(e)
        except (ValueError, KeyError):
            continue
    return out


def aufraeumen(tage=60):
    """Alte Einträge entfernen, damit die Datei klein bleibt."""
    behalten = lesen(stunden=24 * tage)
    if DATEI.exists():
        DATEI.write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in behalten))
