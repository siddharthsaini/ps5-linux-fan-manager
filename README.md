# PS5 Fan Manager

A small GNOME/Ubuntu top-bar app for the PS5 fan hwmon driver.

Requires Python 3, GTK 3, and the Ayatana AppIndicator bindings. On Ubuntu:

```sh
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1
```

It has two modes:

- **Auto** -> closed-loop temperature control using one target (default 70°C), configurable from 40–90°C.
- **Manual** -> direct PWM control with no temperature-based automation.

The default control sensor is **MainSoC**. A checkbox switches to the hottest of
the PS5 sensors (MainSoC, Local1, Local2, Local3).

## Install

```sh
sudo ./install.sh
```

Then start it now, or log out and back in:

```sh
ps5-fan-manager --show
```

The installer also creates an XDG autostart entry and a systemd helper service.

## Safety

- Fan PWM never goes below **26**, including in manual mode.
- Auto mode uses the configured fan range (default 26–255).
- A critical temperature of **90°C** forces PWM 255 in Auto mode.
- Manual mode never changes PWM because of temperature. Instead, the top-bar
  icon is coloured:
  - green: below 70°C
  - yellow: 70°C to below 85°C
  - red: 85°C and above
- If the GUI quits or disconnects, the helper restores the driver's automatic
  mode by default. This can be disabled in Settings.
- The helper also returns the fan to automatic mode whenever it starts, so a
  crashed/restarted helper cannot leave a stale manual PWM behind.

## Files

| Path | Purpose |
|---|---|
| `/usr/local/bin/ps5-fan-manager` | GUI launcher |
| `/usr/local/lib/ps5-fan-manager/` | installed Python files |
| `/etc/systemd/system/ps5-fan-helper.service` | privileged helper |
| `~/.config/ps5-fan-manager/config.json` | settings |
| `~/.config/autostart/ps5-fan-manager.desktop` | login autostart |

The helper communicates over `/run/ps5-fan-manager/control.sock`. The socket is
owned by root and the installing user's primary group, and the helper verifies
the peer UID before accepting commands.

## Logs

```sh
journalctl -u ps5-fan-helper -f
```

## Remove

```sh
sudo ./uninstall.sh
```

The uninstaller restores `pwm1_enable=2` before removing the helper.

## Development

The helper accepts a fake hwmon tree and an alternate socket, so it can be
tested without root or hardware:

```sh
./ps5-fan-helper --fake-root /path/to/fake-hwmon --socket /tmp/ps5fan.sock
PS5_FAN_SOCKET=/tmp/ps5fan.sock ./ps5-fan-manager --show
```

The fake hwmon directory must contain a `hwmon0` directory with:

```text
name            -> ps5_fan
temp1_input     -> 56000
temp1_label     -> MainSoC
pwm1            -> 120
pwm1_enable     -> 1
```

The real driver exposes no fan tachometer, so the app can only confirm the
commanded PWM, not the measured RPM.
