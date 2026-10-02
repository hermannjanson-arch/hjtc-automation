#!/usr/bin/env bash
# Erinnerung: eBay-Refresh-Token (ebay-feedback) läuft bald ab.
# Wird einmalig vom systemd-Timer ebay-token-reminder.timer ausgelöst.
# Nach einer Token-Erneuerung das Datum in
# /etc/systemd/system/ebay-token-reminder.timer anpassen (neuer Ablauf - 1 Monat).

set -u
PREFIX="${WATCHDOG_PREFIX:-}"

msg="${PREFIX}⏰ eBay-Refresh-Token läuft bald ab!

Der Token für ebay-feedback läuft ca. am 01.01.2028 ab (18 Monate nach Erstellung am 02.07.2026). Danach kann der Bot kein Feedback mehr geben.

Erneuern:
1. sudo systemd-run --pty --uid=ubuntu -p EnvironmentFile=/home/ubuntu/ebay-feedback/.env /home/ubuntu/ebay-feedback/venv/bin/python3 /home/ubuntu/ebay-feedback/ebay_oauth_setup.py
2. Mit dem eBay-VERKAUFSKONTO einloggen
3. Neuen EBAY_REFRESH_TOKEN in ~/ebay-feedback/.env eintragen (OHNE Anführungszeichen, wie bisher)
4. sudo systemctl restart ebay-feedback
5. Datum in /etc/systemd/system/ebay-token-reminder.timer auf neuen Ablauf minus 1 Monat setzen"

code=$(curl -sS -m 15 -o /dev/null -w "%{http_code}" \
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
    --data-urlencode "text=${msg}" \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage")
if [ "$code" != "200" ]; then
    echo "Telegram-Versand fehlgeschlagen (HTTP $code)" >&2
    exit 1
fi
echo "Erinnerung gesendet"
