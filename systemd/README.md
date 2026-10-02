# systemd-Units (Kopien)

Die aktiven Dateien liegen in `/etc/systemd/system/`. Dieser Ordner ist nur eine
versionierte Kopie. Nach einer Änderung an einer Unit hierher zurückkopieren:

    cp /etc/systemd/system/ebay-*.service /etc/systemd/system/ebay-*.timer ~/systemd/

Wiederherstellen auf einem neuen Server:

    sudo cp ~/systemd/*.service ~/systemd/*.timer /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now ebay-watcher ebay-feedback ebay-watchdog.timer ebay-token-reminder.timer

Secrets stehen NICHT in den Units, sondern in den .env-Dateien (EnvironmentFile=).
