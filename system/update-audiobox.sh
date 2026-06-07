#!/bin/bash
# Mise à jour automatique AudioBox depuis GitHub
set -euo pipefail

REPO="https://raw.githubusercontent.com/pi2018/AudioBox/main"
LOCAL_V=$(cat /opt/jv/version.json 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin)['version'])" 2>/dev/null || echo "0.0.0")
REMOTE_V=$(curl -sf $REPO/version.json | python3 -c "import sys,json;print(json.load(sys.stdin)['version'])")

echo "$(date) Version locale: $LOCAL_V — GitHub: $REMOTE_V"

if [ "$LOCAL_V" = "$REMOTE_V" ]; then
  echo "$(date) Déjà à jour."
  exit 0
fi

echo "$(date) Mise à jour $LOCAL_V → $REMOTE_V"
curl -sf $REPO/frontend/index.html -o /opt/jv/frontend/index.html
curl -sf $REPO/version.json -o /opt/jv/version.json
systemctl restart jv-backend
echo "$(date) Mise à jour terminée !"
