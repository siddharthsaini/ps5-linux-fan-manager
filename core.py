#!/usr/bin/env python3
"""Shared configuration, sensor, and fan-control logic."""

from __future__ import annotations

import glob
import json
import os
import tempfile
import time

HWMON_ROOT = "/sys/class/hwmon"
SOCKET_PATH = os.environ.get(
    "PS5_FAN_SOCKET", "/run/ps5-fan-manager/control.sock"
)
CONFIG_PATH = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "ps5-fan-manager",
    "config.json",
)

MIN_PWM = 26
MAX_PWM = 255
GREEN_BELOW = 70.0
YELLOW_BELOW = 85.0
CRITICAL_TEMP = 90.0
POLL_SECONDS = 1.0

DEFAULTS = {
    "mode": "auto",
    "target": 70.0,
    "manual_pwm": 120,
    "min_pwm": MIN_PWM,
    "max_pwm": MAX_PWM,
    "use_hottest": False,
    "restore_on_exit": True,
    "show_temp": True,
}


def _clamp(value, low, high):
    return max(low, min(high, value))


def _read(path, default=None):
    try:
        with open(path, "r", encoding="ascii") as handle:
            return handle.read().strip()
    except (OSError, UnicodeError):
        return default


def _read_int(path, default=None):
    value = _read(path)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def find_hwmon(root=HWMON_ROOT):
    """Return the hwmon directory whose name is ps5_fan."""
    for directory in sorted(glob.glob(os.path.join(root, "hwmon*"))):
        if _read(os.path.join(directory, "name")) == "ps5_fan":
            return directory
    return None


def read_temps(hwmon):
    temps = []
    for path in sorted(glob.glob(os.path.join(hwmon, "temp*_input"))):
        base = os.path.basename(path)[: -len("_input")]
        label = _read(os.path.join(hwmon, base + "_label")) or base
        value = _read_int(path)
        if value is not None:
            temps.append({"label": label, "celsius": value / 1000.0})
    return temps


def read_pwm(hwmon):
    return _read_int(os.path.join(hwmon, "pwm1"), 0)


def write_value(path, value):
    with open(path, "w", encoding="ascii") as handle:
        handle.write(str(value) + "\n")


def select_temp(temps, use_hottest):
    """Return (label, celsius) for the configured control sensor."""
    if not temps:
        return None, None
    if use_hottest:
        sensor = max(temps, key=lambda item: item["celsius"])
        return sensor["label"], sensor["celsius"]
    for sensor in temps:
        if sensor["label"].casefold() == "mainsoc":
            return sensor["label"], sensor["celsius"]
    return temps[0]["label"], temps[0]["celsius"]


def temp_color(celsius):
    if celsius is None:
        return "grey"
    if celsius < GREEN_BELOW:
        return "green"
    if celsius < YELLOW_BELOW:
        return "yellow"
    return "red"


def pwm_percent(pwm):
    return int(round(pwm * 100.0 / MAX_PWM))


def normalize_config(raw):
    config = dict(DEFAULTS)
    if isinstance(raw, dict):
        config.update(raw)
        # Migrate configs from the older separate Auto/Fixed targets.
        if "target" not in raw:
            source = "fixed_target" if raw.get("mode") == "fixed" else "auto_target"
            if source in raw:
                config["target"] = raw[source]
    for key in ("auto_target", "fixed_target"):
        config.pop(key, None)

    mode = str(config.get("mode", "auto")).lower()
    if mode == "fixed":
        mode = "auto"
    config["mode"] = mode if mode in ("auto", "manual") else "auto"

    try:
        config["target"] = _clamp(float(config.get("target", 70)), 40.0, 90.0)
    except (TypeError, ValueError):
        config["target"] = 70.0

    for key in ("manual_pwm", "min_pwm", "max_pwm"):
        try:
            config[key] = _clamp(int(config.get(key, MIN_PWM)), MIN_PWM, MAX_PWM)
        except (TypeError, ValueError):
            config[key] = MIN_PWM

    config["manual_pwm"] = _clamp(config["manual_pwm"], MIN_PWM, MAX_PWM)
    config["min_pwm"] = _clamp(config["min_pwm"], MIN_PWM, MAX_PWM)
    config["max_pwm"] = _clamp(config["max_pwm"], config["min_pwm"], MAX_PWM)

    for key in ("use_hottest", "restore_on_exit", "show_temp"):
        config[key] = bool(config.get(key, DEFAULTS[key]))

    return config


def load_config(path=CONFIG_PATH):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return normalize_config(json.load(handle))
    except (OSError, ValueError, TypeError):
        return normalize_config({})


def save_config(config, path=CONFIG_PATH):
    config = normalize_config(config)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=directory, prefix=".config-", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


PROFILE = {
    "kp": 0.040,
    "ki": 0.005,
    "deadband": 1.5,
    "up": 0.08,
    "down": 0.03,
}


class FanController:
    """Small PI controller whose output is mapped onto the configured PWM range."""

    def __init__(self):
        self.integral = 0.0
        self.last_output = None
        self.last_time = None

    def reset(self, fraction):
        self.integral = _clamp(fraction, 0.0, 1.0)
        self.last_output = self.integral
        self.last_time = None

    def force_max(self):
        self.integral = 1.0
        self.last_output = 1.0

    def update(self, celsius, target, min_pwm, max_pwm, now=None):
        profile = PROFILE
        now = time.monotonic() if now is None else now
        dt = 1.0 if self.last_time is None else _clamp(now - self.last_time, 0.2, 5.0)
        self.last_time = now

        error = celsius - target
        if abs(error) <= profile["deadband"]:
            error = 0.0

        integral = _clamp(
            self.integral + profile["ki"] * error * dt, 0.0, 1.0
        )
        output = integral + profile["kp"] * error
        if output > 1.0 and error > 0:
            integral = self.integral
        elif output < 0.0 and error < 0:
            integral = self.integral
        self.integral = integral
        output = _clamp(output, 0.0, 1.0)

        if self.last_output is not None:
            output = _clamp(
                output,
                self.last_output - profile["down"] * dt,
                self.last_output + profile["up"] * dt,
            )
        self.last_output = output

        span = max(0, max_pwm - min_pwm)
        return int(round(min_pwm + output * span))
