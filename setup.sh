#!/usr/bin/env bash
# One-command setup for the personal browser-agent site.
# Target: fresh Ubuntu 24.04 on an Oracle Cloud Always Free Ampere (ARM) VM.
# Run as root:  curl -fsSL <raw-setup.sh-url> -o /tmp/setup.sh && sudo bash /tmp/setup.sh
set -euo pipefail

REPO_URL="${REPO_URL:-}"
INSTALL_DIR="/opt/browser-agent"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run this script as root: sudo bash /tmp/setup.sh"
  exit 1
fi

echo "=== 1/5 Installing Docker (if needed) ==="
if ! command -v docker >/dev/null 2>&1; then
  apt-get update
  apt-get install -y ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  ARCH="$(dpkg --print-architecture)"
  CODENAME="$(. /etc/os-release && echo "$VERSION_CODENAME")"
  echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin git
  systemctl enable --now docker
else
  echo "Docker already installed: $(docker --version)"
  command -v git >/dev/null 2>&1 || apt-get install -y git
fi

echo "=== 2/5 Opening firewall ports 80/443 ==="
# Oracle's Ubuntu images block everything except SSH via iptables by default.
iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || iptables -I INPUT -p tcp --dport 80 -j ACCEPT
iptables -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null || iptables -I INPUT -p tcp --dport 443 -j ACCEPT
if ! dpkg -s iptables-persistent >/dev/null 2>&1; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent
fi
netfilter-persistent save >/dev/null 2>&1 || true
echo "Ports 80/443 open."

echo "=== 3/5 Getting the project code ==="
if [ -z "$REPO_URL" ]; then
  read -rp "GitHub repo URL for this project (https://github.com/YOU/REPO.git): " REPO_URL
fi
if [ -d "$INSTALL_DIR/.git" ]; then
  echo "Updating existing checkout..."
  git -C "$INSTALL_DIR" pull --ff-only || true
else
  rm -rf "$INSTALL_DIR"
  git clone "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

echo "=== 4/5 Creating .env ==="
if [ -f .env ]; then
  echo ".env already exists, keeping it."
else
  read -rp "Domain — your DuckDNS subdomain (e.g. adam-agent.duckdns.org): " DOMAIN
  while [ -z "${DOMAIN:-}" ]; do
    echo "Domain is required (Caddy needs it for HTTPS)."
    read -rp "Domain: " DOMAIN
  done
  read -rsp "Site password (used to log in to your website): " SITE_PASSWORD
  echo
  if [ -z "${SITE_PASSWORD:-}" ]; then
    SITE_PASSWORD="$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)"
    echo "No password entered — generated one: $SITE_PASSWORD"
    echo "SAVE THIS SOMEWHERE SAFE."
  fi
  read -rp "Gemini API key (free from https://aistudio.google.com): " LLM_API_KEY
  while [ -z "${LLM_API_KEY:-}" ]; do
    echo "The agent needs an API key to think. Get a free one at https://aistudio.google.com"
    read -rp "Gemini API key: " LLM_API_KEY
  done
  read -rp "Gemini model [gemini-2.5-flash]: " LLM_MODEL
  LLM_MODEL="${LLM_MODEL:-gemini-2.5-flash}"

  cat > .env <<EOF
DOMAIN=${DOMAIN}
SITE_PASSWORD=${SITE_PASSWORD}
LLM_API_KEY=${LLM_API_KEY}
LLM_MODEL=${LLM_MODEL}
TZ=America/Winnipeg
MAX_STEPS=40
EOF
  chmod 600 .env
  echo ".env written."
fi

echo "=== 5/5 Building and starting (first build takes a few minutes) ==="
docker compose up -d --build

DOMAIN_VAL="$(grep -E '^DOMAIN=' .env | cut -d= -f2-)"
echo
echo "Done! In a minute or two, open: https://${DOMAIN_VAL}"
echo "Log in with your site password, then use 'Take over' to log in to your"
echo "favorite sites inside the browser once — the agent will reuse those logins."
echo
echo "Useful commands:"
echo "  docker compose -f $INSTALL_DIR/docker-compose.yml logs -f   # watch logs"
echo "  docker compose -f $INSTALL_DIR/docker-compose.yml ps        # status"
