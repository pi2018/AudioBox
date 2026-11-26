#!/bin/bash
# /opt/jv/system/mount-nas.sh — monte un partage SMB du NAS et le retient : il est
# remonté à chaque démarrage (service audiobox-nas, script remonter-nas.sh). Avant
# (1.5), un partage monté disparaissait au premier redémarrage de la box.
# Lancé par le serveur via sudo (autorisé dans /etc/sudoers.d/audiobox).
# Propriétaire : root, droits 755 : l'utilisateur jv ne peut PAS le modifier.
#
# Usage : mount-nas.sh HOTE PARTAGE POINT_DE_MONTAGE [UTILISATEUR]
# Le mot de passe arrive par l'entrée standard (une ligne), jamais en argument :
# un argument est visible par tous les programmes de la box (« ps »). Il est gardé
# dans /etc/audiobox/nas, lisible par root seulement (comme pour /etc/fstab), et
# effacé par umount-nas.sh.
set -euo pipefail

HOST="${1:-}"
SHARE="${2:-}"
MOUNT_POINT="${3:-}"
USERNAME="${4:-}"
PASSWORD=""
IFS= read -r PASSWORD || true
REGLAGES="/etc/audiobox/nas"
COMPTE_BOX="jv"

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
if [[ "$SHARE$MOUNT_POINT$USERNAME$PASSWORD" == *[[:cntrl:]]* ]]; then
    echo "Caractère invalide dans les réglages du NAS" >&2; exit 1
fi

# Le vrai chemin, sans « .. » ni lien : « /mnt/../etc » est refusé.
REEL="$(realpath -m -- "$MOUNT_POINT")"
if [[ "$REEL" != /opt/jv/nas/* && "$REEL" != /mnt/* ]]; then
    echo "Point de montage non autorisé: $MOUNT_POINT" >&2
    exit 1
fi
MOUNT_POINT="$REEL"
CLE="$(printf '%s' "$MOUNT_POINT" | tr -c 'A-Za-z0-9._-' '_')"
CONF="$REGLAGES/$CLE.conf"
CRED="$REGLAGES/$CLE.cred"

mkdir -p -- "$MOUNT_POINT"
install -d -m 700 "$REGLAGES"

if mountpoint -q -- "$MOUNT_POINT" 2>/dev/null; then
    umount -- "$MOUNT_POINT" || umount -l -- "$MOUNT_POINT"
    sleep 1
fi

BASE_OPTS="uid=$(id -u "$COMPTE_BOX"),gid=$(id -g "$COMPTE_BOX"),vers=3.0,iocharset=utf8,file_mode=0644,dir_mode=0755"
oublier() { rm -f -- "$CONF" "$CRED"; }

if [[ -n "$USERNAME" ]]; then
    ( umask 077; printf 'username=%s\npassword=%s\n' "$USERNAME" "$PASSWORD" > "$CRED" )
    if ! mount -t cifs "//${HOST}/${SHARE}" "$MOUNT_POINT" -o "${BASE_OPTS},credentials=${CRED}"; then
        oublier
        echo "Le NAS refuse : vérifie l'adresse, le partage, le nom et le mot de passe" >&2
        exit 1
    fi
else
    rm -f -- "$CRED"
    if ! mount -t cifs "//${HOST}/${SHARE}" "$MOUNT_POINT" -o "${BASE_OPTS},guest" 2>/dev/null \
        && ! mount -t cifs "//${HOST}/${SHARE}" "$MOUNT_POINT" -o "${BASE_OPTS},username=guest,password="; then
        oublier
        echo "Le NAS refuse l'accès sans mot de passe" >&2
        exit 1
    fi
fi

# Retenu pour le prochain démarrage.
( umask 077; printf 'HOST=%s\nSHARE=%s\nMOUNT_POINT=%s\n' "$HOST" "$SHARE" "$MOUNT_POINT" > "$CONF" )
echo "OK: //${HOST}/${SHARE} monté sur ${MOUNT_POINT}"
