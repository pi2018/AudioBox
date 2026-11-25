#!/bin/bash
# /opt/jv/system/umount-nas.sh — démonte un partage du NAS (root, 755).
set -euo pipefail

MOUNT_POINT="${1:-}"
if [[ -z "$MOUNT_POINT" ]]; then
    echo "Usage: umount-nas.sh POINT_DE_MONTAGE" >&2
    exit 1
fi

REEL="$(realpath -m -- "$MOUNT_POINT")"
if [[ "$REEL" != /opt/jv/nas/* && "$REEL" != /mnt/* ]]; then
    echo "Point de montage non autorisé: $MOUNT_POINT" >&2
    exit 1
fi

if mountpoint -q -- "$REEL" 2>/dev/null; then
    umount -- "$REEL" || umount -l -- "$REEL"
    echo "OK: ${REEL} démonté"
else
    echo "Déjà démonté: ${REEL}"
fi
