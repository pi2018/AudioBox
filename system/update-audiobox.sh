#!/bin/bash
# /opt/jv/system/update-audiobox.sh — met toute l'AudioBox à jour depuis GitHub.
# Lancé par le bouton « Mettre à jour » (via sudo, autorisé dans sudoers).
# Propriétaire root, droits 755 : l'utilisateur jv ne peut pas le modifier.
#
# 1. Appelé par le serveur, il se recopie et se relance À PART (systemd-run), puis rend
#    la main tout de suite. Avant (1.5), il travaillait « à l'intérieur » du service du
#    serveur : quand l'installation redémarrait le serveur, systemd arrêtait aussi la
#    mise à jour, en plein travail.
# 2. À part : il télécharge la dernière version (branche main), lance son install.sh,
#    vérifie que le serveur tourne bien la NOUVELLE version, note le résultat (affiché
#    dans Paramètres › Système) et redémarre la box. En cas d'échec, rien ne redémarre
#    et l'écran affiche ce qui n'a pas marché.
#
# Codes de sortie : 0 lancé, 1 échec, 2 déjà en cours.
set -uo pipefail

DEPOT="pi2018/AudioBox"
BRANCHE="main"
LOGS="/opt/jv/logs"
JOURNAL="$LOGS/mise-a-jour.log"
ETAT="$LOGS/mise-a-jour.etat"
UNITE="audiobox-mise-a-jour"
COPIE="/run/audiobox-mise-a-jour.sh"
UTILISATEUR="${AUDIOBOX_USER:-jv}"

noter() { mkdir -p "$LOGS"; echo "$*" > "$ETAT"; }

version_de() {  # version_de FICHIER.json
    python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["version"])' "$1" 2>/dev/null || echo "?"
}

version_qui_tourne() {
    curl -fsS --max-time 5 http://127.0.0.1:8000/api/system/version 2>/dev/null \
        | python3 -c 'import json, sys; print(json.load(sys.stdin).get("en_cours", ""))' 2>/dev/null
}

lancer_a_part() {
    if systemctl is-active --quiet "$UNITE"; then
        echo "Une mise à jour est déjà en cours"
        return 2
    fi
    systemctl reset-failed "$UNITE" >/dev/null 2>&1 || true
    # Une copie : l'installation remplace ce fichier pendant qu'il travaille.
    install -m 700 "$0" "$COPIE"
    noter "en_cours"
    if ! systemd-run --unit="$UNITE" --collect --quiet \
            --setenv=AUDIOBOX_USER="$UTILISATEUR" /bin/bash "$COPIE" --maintenant; then
        noter "echec : lancement impossible"
        echo "Lancement de la mise à jour impossible"
        return 1
    fi
    echo "OK: mise à jour lancée"
}

mettre_a_jour() {
    mkdir -p "$LOGS"
    exec >"$JOURNAL" 2>&1
    echo "$(date) Mise à jour AudioBox depuis $DEPOT ($BRANCHE)"
    TMP="$(mktemp -d)"
    trap 'rm -rf "$TMP"' EXIT

    if ! curl -fsSL --retry 3 --max-time 300 \
            "https://codeload.github.com/${DEPOT}/tar.gz/refs/heads/${BRANCHE}" -o "$TMP/audiobox.tar.gz"; then
        noter "echec : téléchargement impossible (internet ?)"
        return 1
    fi
    if ! tar -xzf "$TMP/audiobox.tar.gz" -C "$TMP"; then
        noter "echec : archive illisible"
        return 1
    fi
    SRC="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -1)"
    if [[ ! -f "$SRC/install.sh" || ! -d "$SRC/backend" ]]; then
        noter "echec : archive inattendue"
        return 1
    fi

    LOCAL_V="$(version_de /opt/jv/version.json)"
    NOUVELLE_V="$(version_de "$SRC/version.json")"
    echo "$(date) Version installée : $LOCAL_V — nouvelle : $NOUVELLE_V"

    cd "$SRC" || return 1
    if ! SUDO_USER="$UTILISATEUR" bash ./install.sh; then
        noter "echec : l'installation s'est arrêtée (voir le journal de mise à jour)"
        systemctl restart jv-backend || true
        return 1
    fi

    # Le serveur doit répondre avec la NOUVELLE version (2 minutes au plus).
    for _ in $(seq 1 60); do
        [[ "$(version_qui_tourne)" == "$NOUVELLE_V" ]] && break
        sleep 2
    done
    if [[ "$(version_qui_tourne)" != "$NOUVELLE_V" ]]; then
        noter "echec : le serveur ne tourne pas la version $NOUVELLE_V"
        return 1
    fi

    noter "ok $NOUVELLE_V"
    echo "$(date) Mise à jour terminée ($NOUVELLE_V) — la box redémarre"
    # Redémarrage complet : l'écran repart lui aussi sur la nouvelle version.
    sleep 3
    systemctl reboot
}

if [[ "${1:-}" == "--maintenant" ]]; then
    mettre_a_jour; exit $?
else
    lancer_a_part; exit $?
fi
