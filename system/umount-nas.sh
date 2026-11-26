#!/bin/bash
# /opt/jv/system/umount-nas.sh — démonte un partage du NAS et l'oublie (il n'est plus
# remonté au démarrage, et son mot de passe est effacé). Propriétaire root, droits 755.
set -euo pipefail

MOUNT_POINT="${1:-}"
REGLAGES="/etc/audiobox/nas"
if [[ -z "$MOUNT_POINT" ]]; then
    echo "Usage: umount-nas.sh POINT_DE_MONTAGE" >&2
    exit 1
fi

REEL="$(realpath -m -- "$MOUNT_POINT")"
if [[ "$REEL" != /opt/jv/nas/* && "$REEL" != /mnt/* ]]; then
    echo "Point de montage non autorisé: $MOUNT_POINT" >&2
    exit 1
fi

CLE="$(printf '%s' "$REEL" | tr -c 'A-Za-z0-9._-' '_')"
rm -f -- "$REGLAGES/$CLE.conf" "$REGLAGES/$CLE.cred"

if mountpoint -q -- "$REEL" 2>/dev/null; then
    umount -- "$REEL" || umount -l -- "$REEL"
    echo "OK: ${REEL} démonté"
else
    echo "Déjà démonté: ${REEL}"
fi
