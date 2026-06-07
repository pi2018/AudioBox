#!/bin/bash
# /opt/jv/system/mount-nas.sh
# Propriétaire: root, chmod 700
set -euo pipefail

HOST="${1:-}"
SHARE="${2:-}"
MOUNT_POINT="${3:-}"
USERNAME="${4:-}"
PASSWORD="${5:-}"

# Validation
if [[ -z "$HOST" || -z "$SHARE" || -z "$MOUNT_POINT" ]]; then
    echo "Usage: mount-nas.sh HOST SHARE MOUNT_POINT [USER] [PASS]" >&2
    exit 1
fi

# Restreindre les points de montage autorisés
if [[ "$MOUNT_POINT" != /opt/jv/nas/* && "$MOUNT_POINT" != /mnt/* ]]; then
    echo "Point de montage non autorisé: $MOUNT_POINT" >&2
    exit 1
fi

# Créer le répertoire de montage
mkdir -p "$MOUNT_POINT"

# Démonter si déjà monté
if mountpoint -q "$MOUNT_POINT" 2>/dev/null; then
    umount "$MOUNT_POINT" || umount -l "$MOUNT_POINT"
    sleep 1
fi

# Options de base
BASE_OPTS="uid=$(id -u jv),gid=$(id -g jv),vers=3.0,iocharset=utf8,file_mode=0644,dir_mode=0755"

# Montage avec ou sans credentials
if [[ -n "$USERNAME" && -n "$PASSWORD" ]]; then
    mount -t cifs "//${HOST}/${SHARE}" "$MOUNT_POINT" \
        -o "${BASE_OPTS},username=${USERNAME},password=${PASSWORD}"
elif [[ -n "$USERNAME" ]]; then
    mount -t cifs "//${HOST}/${SHARE}" "$MOUNT_POINT" \
        -o "${BASE_OPTS},username=${USERNAME}"
else
    mount -t cifs "//${HOST}/${SHARE}" "$MOUNT_POINT" \
        -o "${BASE_OPTS},guest" 2>/dev/null || \
    mount -t cifs "//${HOST}/${SHARE}" "$MOUNT_POINT" \
        -o "${BASE_OPTS},username=guest,password="
fi

echo "OK: //${HOST}/${SHARE} monté sur ${MOUNT_POINT}"
