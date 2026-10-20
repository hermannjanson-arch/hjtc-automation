#!/usr/bin/env python3
"""Status aller HJTC-Server-Dienste als JSON (für das Cockpit auf dem Mac, per SSH abgefragt)."""
import json, subprocess, sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path.home() / 'ebay-status'))
sys.path.insert(0, str(Path.home() / 'ebay-radar'))
import ereignisse

DIENSTE = {  # Unit: Beschreibung
    'ebay-feedback.service': 'Feedback-Bot', 'ebay-watcher.service': 'Watcher (Costume/Prop-Karten)',
    'ebay-neuheiten.timer': 'Neuheiten-Radar', 'ebay-verkaufs-sync.timer': 'Verkaufs-Sync',
    'ebay-watchdog.timer': 'Watchdog', 'ebay-morgenbericht.timer': 'Morgenbericht'}


def show(unit, props):
    out = subprocess.run(['systemctl', 'show', unit, '-p', ','.join(props)], capture_output=True, text=True).stdout
    return dict(z.split('=', 1) for z in out.splitlines() if '=' in z)


def fehler_24h(unit):
    out = subprocess.run(['journalctl', '-u', unit.replace('.timer', '.service'), '--since', '-24h', '--no-pager', '-o', 'cat'],
                         capture_output=True, text=True).stdout
    return sum(1 for z in out.splitlines() if '[ERROR]' in z or 'Traceback' in z)


def main():
    d = {'zeit': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'dienste': [], 'sets': [], 'ereignisse': ereignisse.lesen(24 * 7)}
    for unit, name in DIENSTE.items():
        if unit.endswith('.timer'):
            t = show(unit, ['ActiveState', 'LastTriggerUSec', 'NextElapseUSecRealtime'])
            s = show(unit.replace('.timer', '.service'), ['Result', 'ExecMainStatus'])
            ok = t.get('ActiveState') == 'active' and s.get('Result') in ('success', '')
            d['dienste'].append({'name': name, 'ok': ok, 'zustand': t.get('ActiveState'), 'zuletzt': t.get('LastTriggerUSec'),
                                 'naechster': t.get('NextElapseUSecRealtime'), 'ergebnis': s.get('Result'), 'fehler_24h': fehler_24h(unit)})
        else:
            s = show(unit, ['ActiveState', 'NRestarts', 'ActiveEnterTimestamp'])
            d['dienste'].append({'name': name, 'ok': s.get('ActiveState') == 'active', 'zustand': s.get('ActiveState'),
                                 'seit': s.get('ActiveEnterTimestamp'), 'neustarts': s.get('NRestarts'), 'fehler_24h': fehler_24h(unit)})
    try:
        import ebay_neuheiten as N
        reg = json.loads((Path.home() / 'ebay-radar' / 'neuheiten_register.json').read_text())
        heute = datetime.now().date()
        for p, e in reg.items():
            alter = (heute - datetime.strptime(e['erstmals'], '%Y-%m-%d').date()).days
            if alter > N.BEOBACHTEN_TAGE or not e['verlauf']:
                continue
            v = e['verlauf'][max(e['verlauf'])]
            d['sets'].append({'praefix': p, 'name': e['name'], 'jahr': e.get('jahr', ''), 'erstmals': e['erstmals'],
                              'angebote': v['angebote'], 'de': v['de'], 'chance': N.prognose(e['name'], v['de'])})
    except Exception as ex:
        d['sets_fehler'] = str(ex)
    try:
        st = json.loads((Path.home() / 'ebay-sync' / 'sync_state.json').read_text())
        d['sync_eintraege'] = len(st.get('erledigt', {}))
    except FileNotFoundError:
        d['sync_eintraege'] = 0
    print(json.dumps(d, ensure_ascii=False))


if __name__ == '__main__':
    main()
