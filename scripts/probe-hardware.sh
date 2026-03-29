#!/usr/bin/env bash
set -euo pipefail

echo "== Mac NAS Guardian hardware probe =="
echo

echo "[1] model"
if [[ -r /sys/devices/virtual/dmi/id/product_name ]]; then
  cat /sys/devices/virtual/dmi/id/product_name
else
  echo "unknown"
fi
echo

echo "[2] applesmc module"
if [[ -d /sys/devices/platform/applesmc.768 ]]; then
  echo "applesmc platform path found: /sys/devices/platform/applesmc.768"
else
  found="$(find /sys/devices/platform -maxdepth 1 -type d -name 'applesmc.*' 2>/dev/null | head -n 1 || true)"
  if [[ -n "${found}" ]]; then
    echo "applesmc platform path found: ${found}"
  else
    echo "applesmc platform path not found"
  fi
fi
echo

echo "[3] fan paths"
find /sys/devices/platform -maxdepth 2 -type f \( -name 'fan*_input' -o -name 'fan*_min' -o -name 'fan*_max' -o -name 'fan*_target' \) 2>/dev/null || true
echo

echo "[4] hwmon temps"
for name_file in /sys/class/hwmon/*/name; do
  [[ -e "${name_file}" ]] || continue
  hwmon_dir="$(dirname "${name_file}")"
  hwmon_name="$(cat "${name_file}" 2>/dev/null || true)"
  echo "hwmon: ${hwmon_dir} (${hwmon_name})"
  find "${hwmon_dir}" -maxdepth 1 -type f -name 'temp*_input' 2>/dev/null || true
done
echo

echo "[5] keyboard backlight"
if [[ -e /sys/class/leds/smc::kbd_backlight/brightness ]]; then
  echo "supported"
  echo "brightness: $(cat /sys/class/leds/smc::kbd_backlight/brightness)"
  echo "max: $(cat /sys/class/leds/smc::kbd_backlight/max_brightness)"
else
  echo "not found"
fi
echo

echo "[6] display backlight"
find /sys/class/backlight -maxdepth 2 -type f \( -name brightness -o -name max_brightness -o -name actual_brightness \) 2>/dev/null || true
echo

echo "[7] led devices"
find /sys/class/leds -maxdepth 2 -type f -name brightness 2>/dev/null || true
