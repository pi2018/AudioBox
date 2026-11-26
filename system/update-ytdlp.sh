#!/bin/bash
# /opt/jv/system/update-ytdlp.sh — met yt-dlp à jour (root, 755, autorisé dans sudoers).
set -euo pipefail
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
curl -fsSL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o "$TMP"
# On ne remplace l'ancien que si le nouveau fonctionne.
chmod 755 "$TMP"
"$TMP" --version >/dev/null
install -m 755 "$TMP" /usr/local/bin/yt-dlp
echo "OK: $(/usr/local/bin/yt-dlp --version)"
