#!/bin/bash
# /opt/jv/system/update-audiobox.sh — met toute l'AudioBox à jour depuis GitHub.
# Lancé par le bouton « Mettre à jour » (via sudo, autorisé dans sudoers).
# Propriétaire root, droits 755 : l'utilisateur jv ne peut pas le modifier.
#
# Il télécharge la dernière version de la branche main, puis relance install.sh
# de cette version : serveur, interface, scripts, droits et services ensemble.
# Le travail se fait en arrière-plan : le serveur qui l'a demandé va redémarrer.
set -euo pipefail

DEPOT="pi2018/AudioBox"
BRANCHE="main"
JOURNAL="/opt/jv/logs/mise-a-jour.log"
UTILISATEUR="${AUDIOBOX_USER:-jv}"

if [[ "${1:-}" != "--maintenant" ]]; then
    # Détaché du serveur : il peut redémarrer sans couper la mise à jour.
    mkdir -p "$(dirname "$JOURNAL")"
    setsid nohup "$0" --maintenant > "$JOURNAL" 2>&1 < /dev/null &
    echo "OK: mise à jour lancée"
    exit 0
fi

echo "$(date) Mise à jour AudioBox depuis $DEPOT ($BRANCHE)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

curl -fsSL "https://codeload.github.com/${DEPOT}/tar.gz/refs/heads/${BRANCHE}" -o "$TMP/audiobox.tar.gz"
tar -xzf "$TMP/audiobox.tar.gz" -C "$TMP"
SRC="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -1)"

if [[ ! -f "$SRC/install.sh" || ! -d "$SRC/backend" ]]; then
    echo "Archive inattendue : mise à jour annulée"
    exit 1
fi

LOCAL_V="$(python3 -c "import json;print(json.load(open('/opt/jv/version.json'))['version'])" 2>/dev/null || echo "?")"
NOUVELLE_V="$(python3 -c "import json;print(json.load(open('$SRC/version.json'))['version'])" 2>/dev/null || echo "?")"
echo "$(date) Version installée : $LOCAL_V — nouvelle : $NOUVELLE_V"

cd "$SRC"
SUDO_USER="$UTILISATEUR" bash ./install.sh
echo "$(date) Mise à jour terminée ($NOUVELLE_V)"
# Redémarrage complet : le serveur ET l'écran repartent sur la nouvelle version.
# (Relancer seulement le serveur laissait l'ancienne page affichée sur l'écran.)
sleep 3
systemctl reboot
