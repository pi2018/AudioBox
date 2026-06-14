#!/bin/bash
# /opt/audiobox/system/umount-nas.sh
set -euo pipefail

MOUNT_POINT="${1:-}"

if [[ -z "$MOUNT_POINT" ]]; then
    echo "Usage: umount-nas.sh MOUNT_POINT" >&2
    exit 1
fi

if [[ "$MOUNT_POINT" != /opt/audiobox/nas/* && "$MOUNT_POINT" != /mnt/* ]]; then
    echo "Point de montage non autorisé: $MOUNT_POINT" >&2
    exit 1
fi

if mountpoint -q "$MOUNT_POINT" 2>/dev/null; then
    umount "$MOUNT_POINT" || umount -l "$MOUNT_POINT"
    echo "OK: ${MOUNT_POINT} démonté"
else
    echo "Déjà démonté: ${MOUNT_POINT}"
fi
