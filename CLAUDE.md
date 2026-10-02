# HJTC eBay-Automation (Oracle Cloud Server)

Der Code liegt NICHT lokal, sondern auf dem Server. Alle Änderungen erfolgen per SSH.

- Host: `ubuntu@130.162.235.0` (Ubuntu 22.04, Python 3.10, 1 GB RAM, Zeitzone UTC)
- SSH-Key (lokal): `/Users/hermannjanson/Documents/03_HJTC_eBay_Business/Code/Ebay_scouting/ssh-key-2026-07-02-2.key`
- Verbinden: `ssh -i "<key>" ubuntu@130.162.235.0 '<befehl>'`
- GitHub (privat): `hermannjanson-arch/hjtc-automation`, Branch `main`

## Arbeitsweise

- Änderungen schrittweise, nach jedem Schritt auf OK warten.
- Vor jeder Änderung Backup: `cp datei.py datei.py.bak-$(date +%F-%H%M)` (`*.bak*` ist gitignored).
- Vor einem Neustart Syntax prüfen: `~/<projekt>/venv/bin/python3 -m py_compile <datei>.py` bzw. `bash -n <datei>.sh`.
- Nach jeder Änderung: `systemctl status ebay-watcher ebay-feedback` prüfen und zeigen.
- `.env`-Dateien nie ausgeben, nur Schlüsselnamen (`cut -d= -f1 .env`). Nur ändern, wenn ausdrücklich verlangt.
- Vor jedem Commit/Push: Diff bzw. Dateiliste zeigen und auf OK warten.

## Server-Struktur

```
/home/ubuntu/                  <- git-Repo (Whitelist-.gitignore: nur die Ordner unten)
├── .gitignore
├── CLAUDE.md                  <- diese Datei
├── ebay-watcher/              Dienst ebay-watcher
│   ├── ebay_watcher.py
│   ├── requirements.txt
│   ├── .env                   (Secrets, ignoriert)
│   ├── seen_items.json        (State, ignoriert)
│   └── venv/                  (ignoriert)
├── ebay-feedback/             Dienst ebay-feedback
│   ├── ebay_feedback_bot.py
│   ├── ebay_oauth_setup.py    einmaliges OAuth-Setup -> EBAY_REFRESH_TOKEN
│   ├── ebay_trading_api.py    \
│   ├── description_template.py > Beschreibungs-Neuaufbau (kein Dienst, manuell)
│   ├── regenerate_descriptions.py /  (--demo / --live, eigenes DRY_RUN=True im Code)
│   ├── .env, .env.save        (Secrets, ignoriert)
│   ├── feedback_given.json    (State, ignoriert)
│   ├── preview/, review.csv   (Ausgaben von regenerate_descriptions, ignoriert)
│   └── venv/                  (ignoriert)
├── ebay-watchdog/
│   ├── watchdog.sh            Telegram-Alarm bei Dienstausfall/Absturz
│   ├── token_reminder.sh      Erinnerung vor Ablauf des Refresh-Tokens
│   └── state/                 (ignoriert)
├── systemd/                   Kopien der Units aus /etc/systemd/system (+ README)
├── ebay-watcher.bak/          Komplett-Backup vom 02.10.2026 (ignoriert)
└── ebay-feedback.bak/         Komplett-Backup vom 02.10.2026 (ignoriert)
```

Units liegen aktiv in `/etc/systemd/system/`. Nach Änderung an einer Unit: `sudo systemctl daemon-reload` und Kopie nach `~/systemd/` aktualisieren.

## Dienste und Timer

| Unit | Zweck | Intervall |
|---|---|---|
| `ebay-watcher.service` | Sucht neue Sammelkarten-Angebote (Browse API, EBAY_US), meldet per Telegram | Endlosschleife, alle 90 s |
| `ebay-feedback.service` | Gibt positives Feedback für bezahlte Bestellungen | Endlosschleife, stündlich |
| `ebay-watchdog.timer` | Alarm, wenn ein Dienst nicht `active` ist, wieder läuft oder abgestürzt/auto-neugestartet wurde (NRestarts) | alle 5 min |
| `ebay-token-reminder.timer` | Erinnerung zur Token-Erneuerung | einmalig 01.12.2027 09:00 Europe/Berlin |

Beide Dienste: `Restart=always`, `RestartSec=10`, Secrets per `EnvironmentFile=<projekt>/.env`.
Watchdog und Reminder nutzen `EnvironmentFile=/home/ubuntu/ebay-feedback/.env` (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID).

### ebay-watcher
- Suchprofile: Liste `SEARCHES` im Skript (Emma Watson Costume Card, Artbox HP Prop Card, Artbox HP Costume Card).
- Sofortkauf → `TELEGRAM_CHAT_ID_FIXED`, Auktionen → `TELEGRAM_CHAT_ID_AUCTION`.
- API-Limit 5.000 Calls/Tag; 3 Suchen × 90 s ≈ 2.880/Tag. Bei neuen Suchen das Intervall prüfen.
- `seen_items.json`: 14 Tage Aufbewahrung. Nicht aus Backup zurückspielen (sonst Doppel-Meldungen).

### ebay-feedback
- **LIVE.** `DRY_RUN` kommt aus der `.env` (`DRY_RUN=false`); fehlt die Variable, gilt False = LIVE. Bei Logikänderungen erst mit `DRY_RUN=true` testen.
- Deutsch für Käufer aus DE/AT/CH, sonst Englisch; Text zufällig aus `FEEDBACK_TEXTS_DE/EN`.
- `feedback_given.json`: 120 Tage Aufbewahrung. Nicht aus Backup zurückspielen (sonst doppeltes Feedback).

## eBay-API-Eigenheiten (hart erarbeitet – nicht "vereinfachen")

1. **Fulfillment-API: Filter bewusst entfernt.** Erst wurde der Feldname in gemischter Schreibweise (`orderFulfillmentStatus`) abgelehnt, mit kleingeschriebenem Namen dann der Wert `{NOT_STARTED|IN_PROGRESS|FULFILLED}` (errorId 30800). Deshalb holt `fetch_paid_orders()` **ungefiltert** (`limit=50`) und prüft `orderPaymentStatus == "PAID"` in Python. Filter nur wieder einbauen, wenn die Syntax vorher getestet ist.
2. **`legacyTransactionId` fehlt oft** in der REST-Antwort der Fulfillment API. Deshalb holt `get_transaction_id()` die TransactionID über die Trading API **`GetOrders`** (XML, SiteID 77, Compat-Level 1193). Die wird für `LeaveFeedback` gebraucht.
3. **Käuferland über `GetUser` / `Site`, nicht über die Lieferadresse.** Bei SpeedPAK und anderen Versand-Konsolidierern zeigt die Lieferadresse das Land des Sammellagers, nicht des Käufers. `get_buyer_registration_country()` nutzt deshalb Trading API `GetUser`. `GERMAN_SPEAKING_COUNTRIES` enthält sowohl ISO-Codes als auch Site-Namen (`GERMANY`, `AUSTRIA`, `SWITZERLAND`).
4. **Refresh-Token steht ohne Anführungszeichen in der `.env`** und funktioniert so mit systemd `EnvironmentFile`. Nicht ändern.

Weitere:
- Feedback-Vergabe nur über Trading API `LeaveFeedback` (keine REST-Alternative).
- Watcher: Application Token (`client_credentials`). Feedback: User Token via Refresh-Token mit Scope `sell.fulfillment`. Access Tokens gelten 2 h und werden automatisch erneuert.
- Refresh-Token gilt 18 Monate (47.304.000 s). Aktueller Token erstellt 02.07.2026 → **Ablauf ca. 01.01.2028**. Erneuern mit `ebay_oauth_setup.py` (Login mit dem eBay-**Verkaufs**konto), danach Datum in `ebay-token-reminder.timer` anpassen.

## System

- `unattended-upgrades` installiert täglich Sicherheitsupdates. **Kein automatischer Server-Reboot** (`/etc/apt/apt.conf.d/52unattended-upgrades-local`). Reboot macht der Nutzer selbst, wenn `/var/run/reboot-required` existiert.
- `needrestart` darf Dienste nach Bibliotheks-Updates neu starten (bewusst so gelassen).
- Git: Push per Deploy-Key `~/.ssh/github_hjtc_deploy` (SSH-Alias `github-hjtc` in `~/.ssh/config`), Identität nur repo-lokal gesetzt.

## Nützliche Befehle

```
sudo systemctl restart <dienst>
systemctl status ebay-watcher ebay-feedback --no-pager
journalctl -u <dienst> -n 50 --no-pager
systemctl list-timers 'ebay-*'
cd ~ && git status && git diff
```
