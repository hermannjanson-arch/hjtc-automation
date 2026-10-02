#!/usr/bin/env bash
# eBay-Watchdog
# =============
# Prüft (per systemd-Timer alle 5 Min.), ob ebay-watcher und ebay-feedback
# laufen, und meldet per Telegram:
#   - wenn ein Dienst nicht mehr "active" ist (einmalig, kein Spam)
#   - wenn er wieder läuft
#   - wenn systemd ihn seit der letzten Prüfung automatisch neu gestartet hat
#     (= Absturz, wegen Restart=always sonst unsichtbar)
# TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID kommen per EnvironmentFile aus
# ~/ebay-feedback/.env (siehe /etc/systemd/system/ebay-watchdog.service).

set -u

SERVICES="${WATCHDOG_SERVICES:-ebay-watcher ebay-feedback}"
STATE_DIR="${WATCHDOG_STATE_DIR:-$HOME/ebay-watchdog/state}"
PREFIX="${WATCHDOG_PREFIX:-}"

mkdir -p "$STATE_DIR"

send_telegram() {
    local code
    code=$(curl -sS -m 15 -o /dev/null -w "%{http_code}" \
        --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=${PREFIX}$1" \
        "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage")
    if [ "$code" != "200" ]; then
        echo "Telegram-Versand fehlgeschlagen (HTTP $code)" >&2
        return 1
    fi
}

last_log_lines() {
    journalctl -u "$1" -n 5 --no-pager -o cat 2>/dev/null | cut -c1-200
}

for svc in $SERVICES; do
    state=$(systemctl is-active "$svc")
    restarts=$(systemctl show -p NRestarts --value "$svc")
    restarts=${restarts:-0}

    state_file="$STATE_DIR/$svc.state"
    restarts_file="$STATE_DIR/$svc.restarts"
    prev_state=$(cat "$state_file" 2>/dev/null || echo active)
    prev_restarts=$(cat "$restarts_file" 2>/dev/null || echo "$restarts")

    if [ "$state" != "active" ] && [ "$prev_state" = "active" ]; then
        msg="🚨 Dienst $svc läuft NICHT (Status: $state) auf $(hostname)

Letzte Log-Zeilen:
$(last_log_lines "$svc")"
        # State nur speichern, wenn die Nachricht rausging -> sonst neuer Versuch beim nächsten Lauf
        send_telegram "$msg" && echo "$state" > "$state_file"
        echo "$svc: $state (Alarm)"
    elif [ "$state" = "active" ] && [ "$prev_state" != "active" ]; then
        send_telegram "✅ Dienst $svc läuft wieder." && echo "$state" > "$state_file"
        echo "$svc: wieder active"
    else
        echo "$state" > "$state_file"
        echo "$svc: $state"
    fi

    # NRestarts zählt nur automatische Neustarts; ein manueller restart setzt ihn auf 0 zurück.
    if [ "$state" = "active" ] && [ "$restarts" -gt "$prev_restarts" ]; then
        msg="⚠️ Dienst $svc ist abgestürzt und wurde automatisch neu gestartet ($((restarts - prev_restarts))x seit letzter Prüfung).

Letzte Log-Zeilen:
$(last_log_lines "$svc")"
        send_telegram "$msg" && echo "$restarts" > "$restarts_file"
        echo "$svc: Neustart erkannt ($prev_restarts -> $restarts)"
    else
        echo "$restarts" > "$restarts_file"
    fi
done
