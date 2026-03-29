#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/opt/mac-nas-guardian"
CONF_ROOT="/etc/mac-nas-guardian"
SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[1/4] installing files to ${APP_ROOT}"
mkdir -p "${APP_ROOT}/app" "${CONF_ROOT}"
cp "${SRC_ROOT}/app/guardian_agent.py" "${APP_ROOT}/app/guardian_agent.py"
chmod +x "${APP_ROOT}/app/guardian_agent.py"

echo "[2/4] installing default config"
if [[ ! -f "${CONF_ROOT}/config.json" ]]; then
  cp "${SRC_ROOT}/config/guardian.example.json" "${CONF_ROOT}/config.json"
fi

echo "[3/4] installing systemd service"
cp "${SRC_ROOT}/systemd/mac-nas-guardian.service" /etc/systemd/system/mac-nas-guardian.service

echo "[4/4] enabling service"
systemctl daemon-reload
systemctl enable --now mac-nas-guardian.service

echo "install complete"
echo "web ui: http://$(hostname -I | awk '{print $1}'):18923/"
