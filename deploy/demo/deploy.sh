#!/bin/sh
# Sets up and updates the public demo on a fresh Ubuntu server; safe to run again.
# The Demo workflow copies this folder and a ready .env to /opt/rhinvoice-demo and
# runs this script there as root. By hand:
#   scp compose.yml Caddyfile init-databases.sh deploy.sh .env root@SERVER:/opt/rhinvoice-demo/
#   ssh root@SERVER sh /opt/rhinvoice-demo/deploy.sh
set -eu

DIR=/opt/rhinvoice-demo
cd "$DIR"

# Docker, once.
if ! command -v docker >/dev/null 2>&1; then
  echo "installing docker"
  curl -fsSL https://get.docker.com | sh
fi

# Firewall: SSH, HTTP (certificates) and HTTPS only. Docker publishes 80 and 443
# itself; nothing else of the stack has a port on the host.
if command -v ufw >/dev/null 2>&1; then
  ufw default deny incoming >/dev/null
  ufw default allow outgoing >/dev/null
  ufw allow 22/tcp >/dev/null
  ufw allow 80/tcp >/dev/null
  ufw allow 443/tcp >/dev/null
  ufw allow 443/udp >/dev/null
  ufw --force enable >/dev/null
fi

# Security updates install themselves.
if ! dpkg -s unattended-upgrades >/dev/null 2>&1; then
  apt-get update -q && DEBIAN_FRONTEND=noninteractive apt-get install -y -q unattended-upgrades
fi

chmod 600 .env
chmod 755 init-databases.sh

docker compose pull --quiet
docker compose up -d --remove-orphans
# Old images of earlier releases are not needed any more.
docker image prune --force >/dev/null

docker compose ps --format "{{.Service}}: {{.Status}}"
