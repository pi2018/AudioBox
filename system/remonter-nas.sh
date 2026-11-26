#!/bin/bash
# /opt/jv/system/remonter-nas.sh — au démarrage, remonte les partages du NAS retenus par
# mount-nas.sh (réglages dans /etc/audiobox/nas, lisibles par root seulement).
# Lancé par le service audiobox-nas. Propriétaire root, droits 755.
set -uo pipefail

REGLAGES="${AUDIOBOX_NAS_REGLAGES:-/etc/audiobox/nas}"
COMPTE_BOX="jv"
ESSAIS="${AUDIOBOX_NAS_ESSAIS:-6}"     # le réseau arrive parfois après le démarrage
PAUSE="${AUDIOBOX_NAS_PAUSE:-10}"
shopt -s nullglob

OPTS="uid=$(id -u "$COMPTE_BOX"),gid=$(id -g "$COMPTE_BOX"),vers=3.0,iocharset=utf8,file_mode=0644,dir_mode=0755"
statut=0

for CONF in "$REGLAGES"/*.conf; do
    HOST=""; SHARE=""; MOUNT_POINT=""
    while IFS='=' read -r cle valeur; do
        case "$cle" in
            HOST) HOST="$valeur" ;;
            SHARE) SHARE="$valeur" ;;
            MOUNT_POINT) MOUNT_POINT="$valeur" ;;
        esac
    done < "$CONF"

    if [[ ! "$HOST" =~ ^[A-Za-z0-9.-]+$ || -z "$SHARE" || "$SHARE" == *","* || -z "$MOUNT_POINT" ]]; then
        echo "Réglage ignoré : $CONF"
        continue
    fi
    REEL="$(realpath -m -- "$MOUNT_POINT")"
    if [[ "$REEL" != /opt/jv/nas/* && "$REEL" != /mnt/* ]]; then
        echo "Point de montage refusé : $MOUNT_POINT"
        continue
    fi
    if mountpoint -q -- "$REEL" 2>/dev/null; then
        continue
    fi
    mkdir -p -- "$REEL"

    CRED="${CONF%.conf}.cred"
    if [[ -f "$CRED" ]]; then
        options="$OPTS,credentials=$CRED"
    else
        options="$OPTS,guest"
    fi

    monte=""
    for ((essai = 1; essai <= ESSAIS; essai++)); do
        if mount -t cifs "//$HOST/$SHARE" "$REEL" -o "$options"; then
            monte=1
            break
        fi
        sleep "$PAUSE"
    done
    if [[ -n "$monte" ]]; then
        echo "OK: //$HOST/$SHARE monté sur $REEL"
    else
        echo "Échec : //$HOST/$SHARE n'a pas pu être monté"
        statut=1
    fi
done
exit $statut
