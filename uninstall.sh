#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this uninstaller with sudo." >&2
    exit 1
fi

TARGET_USER="${SUDO_USER:-${PS5_FAN_USER:-}}"

systemctl disable --now ps5-fan-helper.service 2>/dev/null || true
rm -f /etc/systemd/system/ps5-fan-helper.service
systemctl daemon-reload

# Do not leave the fan at a manually-set PWM after removal.
for hwmon in /sys/class/hwmon/hwmon*; do
    if [ "$(cat "$hwmon/name" 2>/dev/null)" = "ps5_fan" ]; then
        echo 2 > "$hwmon/pwm1_enable" 2>/dev/null || true
    fi
done

rm -rf /usr/local/lib/ps5-fan-manager
rm -f /usr/local/bin/ps5-fan-manager
rm -f /usr/share/applications/ps5-fan-manager.desktop

if [ -n "$TARGET_USER" ] && id "$TARGET_USER" >/dev/null 2>&1; then
    TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
    rm -f "$TARGET_HOME/.config/autostart/ps5-fan-manager.desktop"
fi

echo "Removed PS5 Fan Manager. Saved settings were left in ~/.config/ps5-fan-manager."
