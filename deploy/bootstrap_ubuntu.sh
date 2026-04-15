#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   sudo bash deploy/bootstrap_ubuntu.sh /path/to/wechat-agent-lite

APP_SRC="${1:-}"
if [[ -z "${APP_SRC}" ]]; then
  echo "Usage: sudo bash deploy/bootstrap_ubuntu.sh /path/to/wechat-agent-lite"
  exit 1
fi

APP_USER="${APP_USER:-wechat-agent}"
APP_HOME="${APP_HOME:-/srv/wechat-agent-lite}"
SERVICE_FILE="/etc/systemd/system/wechat-agent-lite.service"
INSTALL_PLAYWRIGHT_CHROMIUM="${INSTALL_PLAYWRIGHT_CHROMIUM:-0}"

echo "[1/9] create user: ${APP_USER}"
if ! id "${APP_USER}" &>/dev/null; then
  useradd -m -s /bin/bash "${APP_USER}"
fi

echo "[2/9] install system packages"
apt-get update
apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  rsync \
  fontconfig \
  fonts-noto-cjk \
  fonts-wqy-zenhei \
  fonts-wqy-microhei
fc-cache -f >/dev/null 2>&1 || true

echo "[3/9] prepare dirs"
mkdir -p "${APP_HOME}" /var/log/wechat-agent-lite
chown -R "${APP_USER}:${APP_USER}" /var/log/wechat-agent-lite

echo "[4/9] sync project"
rsync -av --delete \
  --exclude ".git" \
  --exclude ".env" \
  --exclude ".venv" \
  --exclude "ms-playwright/" \
  --exclude "data/" \
  --exclude "output/" \
  --exclude "tmp/" \
  --exclude "__pycache__/" \
  "${APP_SRC}/" "${APP_HOME}/"
chown -R "${APP_USER}:${APP_USER}" "${APP_HOME}"

echo "[5/9] setup venv and deps"
sudo -u "${APP_USER}" bash -lc "
cd ${APP_HOME}
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
"

echo "[6/9] install playwright chromium (optional)"
if [[ "${INSTALL_PLAYWRIGHT_CHROMIUM}" == "1" ]]; then
  "${APP_HOME}/.venv/bin/python" -m playwright install-deps chromium
  sudo -u "${APP_USER}" bash -lc "
  cd ${APP_HOME}
  source .venv/bin/activate
  python -m playwright install chromium
  "
else
  echo "skip chromium install; set INSTALL_PLAYWRIGHT_CHROMIUM=1 to enable"
fi

echo "[7/9] create .env if missing"
if [[ ! -f "${APP_HOME}/.env" ]]; then
  cp "${APP_HOME}/.env.example" "${APP_HOME}/.env"
  chown "${APP_USER}:${APP_USER}" "${APP_HOME}/.env"
fi

echo "[8/9] install systemd service"
cp "${APP_HOME}/deploy/systemd/wechat-agent-lite.service" "${SERVICE_FILE}"
sed -i "s|User=wechat-agent|User=${APP_USER}|g" "${SERVICE_FILE}"
sed -i "s|/srv/wechat-agent-lite|${APP_HOME}|g" "${SERVICE_FILE}"
systemctl daemon-reload
systemctl enable wechat-agent-lite.service

echo "[9/9] start service"
systemctl restart wechat-agent-lite.service
systemctl status --no-pager wechat-agent-lite.service || true

echo "Done. Access the console through your chosen internal route or reverse proxy."
