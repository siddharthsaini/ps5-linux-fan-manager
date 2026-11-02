#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer with sudo." >&2
    exit 1
fi

TARGET_USER="${SUDO_USER:-${PS5_FAN_USER:-}}"
if [ -z "$TARGET_USER" ] || ! id "$TARGET_USER" >/dev/null 2>&1; then
    echo "Could not determine the desktop user. Run with sudo from that user's session." >&2
    exit 1
fi

TARGET_UID="$(id -u "$TARGET_USER")"
TARGET_GID="$(id -g "$TARGET_USER")"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
SOURCE="$(cd "$(dirname "$0")" && pwd)"
DEST="/usr/local/lib/ps5-fan-manager"
UNIT="/etc/systemd/system/ps5-fan-helper.service"

install -d -m 0755 "$DEST"
install -m 0644 "$SOURCE/core.py" "$DEST/core.py"
install -m 0755 "$SOURCE/ps5-fan-helper" "$DEST/ps5-fan-helper"
install -m 0755 "$SOURCE/ps5-fan-manager" "$DEST/ps5-fan-manager"

cat > /usr/local/bin/ps5-fan-manager <<EOF
#!/bin/sh
exec /usr/bin/python3 "$DEST/ps5-fan-manager" "\$@"
EOF
chmod 0755 /usr/local/bin/ps5-fan-manager

sed "s/@UID@/$TARGET_UID/g" "$SOURCE/ps5-fan-helper.service" > "$UNIT"
systemctl daemon-reload
systemctl enable ps5-fan-helper.service >/dev/null
systemctl restart ps5-fan-helper.service

install -d -m 0755 /usr/share/applications
install -m 0644 "$SOURCE/ps5-fan-manager.desktop" \
    /usr/share/applications/ps5-fan-manager.desktop

install -d -m 0755 -o "$TARGET_USER" -g "$TARGET_GID" "$TARGET_HOME/.config"
install -d -m 0755 -o "$TARGET_USER" -g "$TARGET_GID" "$TARGET_HOME/.config/autostart"
sed 's/ --show//' "$SOURCE/ps5-fan-manager.desktop" > \
    "$TARGET_HOME/.config/autostart/ps5-fan-manager.desktop"
chown "$TARGET_USER:$TARGET_GID" "$TARGET_HOME/.config/autostart/ps5-fan-manager.desktop"
chmod 0644 "$TARGET_HOME/.config/autostart/ps5-fan-manager.desktop"

echo "Installed PS5 Fan Manager."
echo "Top-bar app: /usr/local/bin/ps5-fan-manager"
echo "Helper logs: journalctl -u ps5-fan-helper -f"
echo "The app will start at your next login; run 'ps5-fan-manager --show' now to open it."
