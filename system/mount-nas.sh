#!/bin/bash
# /opt/jv/system/mount-nas.sh — monte un partage SMB du NAS.
# Lancé par le serveur via sudo (autorisé dans /etc/sudoers.d/audiobox).
# Propriétaire : root, droits 755 : l'utilisateur jv ne peut PAS le modifier.
#
# Usage : mount-nas.sh HOTE PARTAGE POINT_DE_MONTAGE [UTILISATEUR]
# Le mot de passe arrive par l'entrée standard (une ligne), jamais en argument :
# un argument est visible par tous les programmes de la box (« ps »).
set -euo pipefail

HOST="${1:-}"
SHARE="${2:-}"
MOUNT_POINT="${3:-}"
USERNAME="${4:-}"
PASSWORD=""
IFS= read -r PASSWORD || true

if [[ -z "$HOST" || -z "$SHARE" || -z "$MOUNT_POINT" ]]; then
    echo "Usage: mount-nas.sh HOTE PARTAGE POINT_DE_MONTAGE [UTILISATEUR]" >&2
    exit 1
fi

# Rien qui puisse ajouter des options de montage (virgule) ou changer de ligne.
if [[ ! "$HOST" =~ ^[A-Za-z0-9.-]+$ ]]; then
    echo "Adresse du NAS invalide: $HOST" >&2; exit 1
fi
if [[ "$SHARE" == *","* || "$USERNAME" == *","* || "$USERNAME" == *"="* ]]; then
    echo "Partage ou utilisateur invalide" >&2; exit 1
fi

# Le vrai chemin, sans « .. » ni lien : « /mnt/../etc » est refusé.
REEL="$(realpath -m -- "$MOUNT_POINT")"
if [[ "$REEL" != /opt/jv/nas/* && "$REEL" != /mnt/* ]]; then
    echo "Point de montage non autorisé: $MOUNT_POINT" >&2
    exit 1
fi
MOUNT_POINT="$REEL"

mkdir -p -- "$MOUNT_POINT"

if mountpoint -q -- "$MOUNT_POINT" 2>/dev/null; then
    umount -- "$MOUNT_POINT" || umount -l -- "$MOUNT_POINT"
    sleep 1
fi

BASE_OPTS="uid=$(id -u jv),gid=$(id -g jv),vers=3.0,iocharset=utf8,file_mode=0644,dir_mode=0755"

if [[ -n "$USERNAME" ]]; then
    # Identifiants dans un fichier lisible par root seul, effacé juste après.
    CRED="$(mktemp /root/.audiobox-cred.XXXXXX)"
    chmod 600 "$CRED"
    trap 'rm -f "$CRED"' EXIT
    printf 'username=%s\npassword=%s\n' "$USERNAME" "$PASSWORD" > "$CRED"
    mount -t cifs "//${HOST}/${SHARE}" "$MOUNT_POINT" -o "${BASE_OPTS},credentials=${CRED}"
else
    mount -t cifs "//${HOST}/${SHARE}" "$MOUNT_POINT" -o "${BASE_OPTS},guest" 2>/dev/null || \
    mount -t cifs "//${HOST}/${SHARE}" "$MOUNT_POINT" -o "${BASE_OPTS},username=guest,password="
fi

echo "OK: //${HOST}/${SHARE} monté sur ${MOUNT_POINT}"
