#!/bin/bash
# ============================================================
# AudioBox — Script d'installation complet
# Cible : Raspberry Pi OS Lite 64-bit (Debian Bookworm/Trixie)
# Usage : sudo bash install.sh
# ============================================================
set -euo pipefail

BOLD='\033[1m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

log()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
err()   { echo -e "${RED}[✗]${NC} $*"; exit 1; }
title() { echo -e "\n${CYAN}${BOLD}── $* ──${NC}\n"; }

[[ "$EUID" -ne 0 ]] && err "Exécuter en tant que root: sudo bash install.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/jv"
USER="jv"

title "AudioBox — Installation"
echo "  Répertoire source : $SCRIPT_DIR"
echo "  Répertoire cible  : $INSTALL_DIR"
echo ""

# ── 1. Mise à jour ────────────────────────────────────────────────────────
title "Mise à jour système"
apt-get update -qq
apt-get upgrade -y -qq
log "Système à jour"

# ── 2. Dépendances ────────────────────────────────────────────────────────
title "Installation des dépendances"

DEBIAN_VERSION=$(lsb_release -cs 2>/dev/null || echo "unknown")
log "Debian détecté : $DEBIAN_VERSION"

# Paquets de base (toujours disponibles)
PKGS="python3 python3-pip python3-venv python3-dev \
    pipewire pipewire-pulse wireplumber \
    bluez bluez-tools \
    xorg openbox x11-xserver-utils \
    mpv ffmpeg \
    cifs-utils nfs-common \
    git curl wget net-tools lsof"

# ── Chromium : teste silencieusement chaque nom ──
CHROMIUM_BIN=""
for pkg in chromium chromium-browser; do
    if apt-cache show "$pkg" > /dev/null 2>&1; then
        PKGS="$PKGS $pkg"
        CHROMIUM_BIN="$pkg"
        log "Chromium trouvé : $pkg"
        break
    fi
done
if [[ -z "$CHROMIUM_BIN" ]]; then
    warn "Chromium non trouvé dans les dépôts"
    warn "Installez-le après : sudo apt-get install chromium"
    CHROMIUM_BIN="chromium"
fi

# ── polkit : teste silencieusement chaque nom ──
for pkg in polkitd policykit-1 polkit; do
    if apt-cache show "$pkg" > /dev/null 2>&1; then
        PKGS="$PKGS $pkg"
        log "polkit trouvé : $pkg"
        # pkexec peut être séparé
        apt-cache show pkexec > /dev/null 2>&1 && PKGS="$PKGS pkexec" || true
        break
    fi
done

# ── unclutter : optionnel ──
apt-cache show unclutter > /dev/null 2>&1 && PKGS="$PKGS unclutter" || true

apt-get install -y -qq $PKGS
log "Dépendances installées"

# Sauvegarder le nom de chromium pour openbox
echo "$CHROMIUM_BIN" > /tmp/audiobox_chromium_bin.txt

# ── 3. yt-dlp ─────────────────────────────────────────────────────────────
title "Installation de yt-dlp"
curl -sSL "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp" \
    -o /usr/local/bin/yt-dlp
chmod +x /usr/local/bin/yt-dlp
log "yt-dlp installé : $(yt-dlp --version 2>/dev/null || echo 'ok')"

# ── 4. Utilisateur jv ─────────────────────────────────────────────────────
title "Création de l'utilisateur $USER"
if ! id "$USER" &>/dev/null; then
    useradd -m -s /bin/bash "$USER"
    log "Utilisateur $USER créé"
else
    log "Utilisateur $USER existe déjà"
fi
for grp in audio bluetooth video render input; do
    getent group "$grp" &>/dev/null && usermod -aG "$grp" "$USER" || true
done
log "Groupes mis à jour"

# ── 5. Structure de répertoires ───────────────────────────────────────────
title "Création de la structure"
mkdir -p "$INSTALL_DIR/backend/routers"
mkdir -p "$INSTALL_DIR/backend/services"
mkdir -p "$INSTALL_DIR/frontend/assets"
mkdir -p "$INSTALL_DIR/config"
mkdir -p "$INSTALL_DIR/system"
mkdir -p "$INSTALL_DIR/nas"
mkdir -p "$INSTALL_DIR/logs"
chown -R "$USER:$USER" "$INSTALL_DIR"
log "Répertoires créés"

# ── 6. Déploiement des fichiers ───────────────────────────────────────────
title "Déploiement des fichiers"
cp -r "$SCRIPT_DIR/backend/." "$INSTALL_DIR/backend/"
cp -r "$SCRIPT_DIR/frontend/." "$INSTALL_DIR/frontend/"
cp "$SCRIPT_DIR/config/config.example.json" "$INSTALL_DIR/config/" 2>/dev/null || true

# Nettoyer les .pyc
find "$INSTALL_DIR/backend" -name "*.pyc" -delete 2>/dev/null || true
find "$INSTALL_DIR/backend" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Scripts système (root, non modifiables par jv)
cp "$SCRIPT_DIR/system/mount-nas.sh"  "$INSTALL_DIR/system/"
cp "$SCRIPT_DIR/system/umount-nas.sh" "$INSTALL_DIR/system/"
chmod 700 "$INSTALL_DIR/system/"*.sh
chown root:root "$INSTALL_DIR/system/"*.sh

chown -R "$USER:$USER" "$INSTALL_DIR/backend"
chown -R "$USER:$USER" "$INSTALL_DIR/frontend"
log "Fichiers déployés"

# ── 7. Environnement Python ───────────────────────────────────────────────
title "Environnement Python virtuel"
sudo -u "$USER" python3 -m venv "$INSTALL_DIR/venv"
sudo -u "$USER" "$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip
sudo -u "$USER" "$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/backend/requirements.txt"
log "Venv Python prêt"

# ── 8. Config initiale ────────────────────────────────────────────────────
title "Configuration initiale"
if [[ ! -f "$INSTALL_DIR/config/config.json" ]]; then
    echo '{}' > "$INSTALL_DIR/config/config.json"
fi
chown -R "$USER:$USER" "$INSTALL_DIR/config"
chmod 700 "$INSTALL_DIR/config"
chmod 600 "$INSTALL_DIR/config/config.json"
log "Config initialisée"

# ── 9. PipeWire ───────────────────────────────────────────────────────────
title "Configuration PipeWire"
loginctl enable-linger "$USER" 2>/dev/null || warn "loginctl enable-linger échoué (non bloquant)"
log "PipeWire configuré"

# ── 10. Bluetooth ─────────────────────────────────────────────────────────
title "Configuration Bluetooth"
systemctl enable bluetooth 2>/dev/null || true
systemctl start bluetooth 2>/dev/null || warn "Bluetooth non démarré"

mkdir -p /etc/bluetooth
cat > /etc/bluetooth/main.conf << 'BTCONF'
[Policy]
AutoEnable=true

[General]
Enable=Source,Sink,Media,Socket
DiscoverableTimeout=0
BTCONF
log "Bluetooth configuré"

# ── 11. polkit ────────────────────────────────────────────────────────────
title "Règles polkit"
POLKIT_DIR=""
for d in /etc/polkit-1/rules.d /usr/share/polkit-1/rules.d; do
    if [[ -d "$d" ]]; then
        POLKIT_DIR="$d"
        break
    fi
done

if [[ -n "$POLKIT_DIR" ]]; then
    cp "$SCRIPT_DIR/system/99-jv-polkit.rules" "$POLKIT_DIR/"
    chmod 644 "$POLKIT_DIR/99-jv-polkit.rules"
    chown root:root "$POLKIT_DIR/99-jv-polkit.rules"
    log "Règles polkit installées dans $POLKIT_DIR"
else
    warn "Répertoire polkit introuvable — règles non installées"
fi

# ── 12. systemd services ──────────────────────────────────────────────────
title "Services systemd"
cp "$SCRIPT_DIR/system/jv-backend.service" /etc/systemd/system/
cp "$SCRIPT_DIR/system/jv-kiosk.service"   /etc/systemd/system/
systemctl daemon-reload
systemctl enable jv-backend
systemctl enable jv-kiosk
log "Services installés et activés"

# ── 13. Autologin tty1 ────────────────────────────────────────────────────
title "Autologin console"
mkdir -p /etc/systemd/system/getty@tty1.service.d/
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf << EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin ${USER} --noclear %I \$TERM
EOF
systemctl daemon-reload
log "Autologin configuré pour $USER sur tty1"

# ── 14. .bashrc — lancement X au boot ─────────────────────────────────────
title "Lancement X automatique"
if ! grep -q "AudioBox" /home/"$USER"/.bashrc 2>/dev/null; then
    cat >> /home/"$USER"/.bashrc << 'BASHRC'

# AudioBox — lancement X sur tty1
if [[ -z "${DISPLAY:-}" ]] && [[ "$(tty 2>/dev/null)" == "/dev/tty1" ]]; then
    exec startx -- -nocursor 2>/dev/null
fi
BASHRC
fi
chown "$USER:$USER" /home/"$USER"/.bashrc
log ".bashrc configuré"

# ── 15. Openbox autostart ─────────────────────────────────────────────────
title "Configuration Openbox"
CHROMIUM_BIN=$(cat /tmp/audiobox_chromium_bin.txt 2>/dev/null || echo "chromium")
mkdir -p /home/"$USER"/.config/openbox

cat > /home/"$USER"/.config/openbox/autostart << OBEOF
# Désactiver économiseur d'écran
xset s off
xset -dpms
xset s noblank

# Masquer le curseur (si disponible)
command -v unclutter &>/dev/null && unclutter -idle 3 -root &

# PipeWire
sleep 1
systemctl --user start pipewire pipewire-pulse wireplumber 2>/dev/null || true

# Backend AudioBox
sleep 2
systemctl start jv-backend 2>/dev/null || true

# Attendre que le backend réponde puis lancer Chromium
sleep 6
${CHROMIUM_BIN} \\
    --kiosk \\
    --noerrdialogs \\
    --disable-infobars \\
    --disable-session-crashed-bubble \\
    --disable-restore-session-state \\
    --touch-events=enabled \\
    --no-first-run \\
    --disable-translate \\
    --check-for-update-interval=31536000 \\
    --app=http://localhost:8000 &
OBEOF

chown -R "$USER:$USER" /home/"$USER"/.config
log "Openbox configuré avec : $CHROMIUM_BIN"

# ── 16. Résumé final ──────────────────────────────────────────────────────
IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "IP_DU_PI")
echo ""
echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║        AudioBox — Installation terminée          ║${NC}"
echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════════╝${NC}"
echo ""
log "Redémarrez : ${BOLD}sudo reboot${NC}"
echo ""
warn "Après le redémarrage :"
echo "  1. Token dashboard : ${BOLD}journalctl -u jv-backend | grep 'Token'${NC}"
echo "  2. Dashboard       : ${BOLD}http://${IP}:8000${NC}"
echo ""
warn "Conservez le token en lieu sûr."

# ════════════════════════════════════════════════════════════
# AJOUTS v1.3.0 — volume, sudoers, splash, script démarrage
# ════════════════════════════════════════════════════════════

# ── Volume ALSA bloqué à 100% dans le service ──────────────
title "Configuration volume ALSA"
if ! grep -q "amixer set Master" /etc/systemd/system/jv-backend.service; then
  sed -i '/\[Service\]/a ExecStartPre=/usr/bin/amixer set Master 100%' /etc/systemd/system/jv-backend.service
  systemctl daemon-reload
  log "Volume ALSA configuré à 100%"
fi

# ── Sudoers NOPASSWD ───────────────────────────────────────
title "Configuration sudoers"
cat > /etc/sudoers.d/audiobox << EOF
${USER} ALL=(ALL) NOPASSWD: /usr/bin/systemctl start jv-backend
${USER} ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop jv-backend
${USER} ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart jv-backend
${USER} ALL=(ALL) NOPASSWD: /usr/sbin/reboot
${USER} ALL=(ALL) NOPASSWD: /usr/sbin/shutdown
EOF
chmod 0440 /etc/sudoers.d/audiobox
log "Sudoers configuré (NOPASSWD pour backend + reboot/shutdown)"

# ── Permissions X ──────────────────────────────────────────
echo "allowed_users=anybody" > /etc/X11/Xwrapper.config

# ── Script de démarrage X ──────────────────────────────────
title "Script de démarrage"
cat > /home/${USER}/start-audiobox-x.sh << 'EOF'
#!/bin/bash
openbox &
sleep 1
xset s off
xset -dpms
systemctl --user start pipewire pipewire-pulse wireplumber 2>/dev/null || true
sudo systemctl start jv-backend 2>/dev/null || true
DISPLAY=:0 exec chromium \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-restore-session-state \
  --touch-events=enabled \
  --no-first-run \
  --check-for-update-interval=31536000 \
  --app=file:///opt/jv/frontend/splash.html
EOF
chmod +x /home/${USER}/start-audiobox-x.sh
chown ${USER}:${USER} /home/${USER}/start-audiobox-x.sh

# .bashrc lance startx sur tty1
if ! grep -q "start-audiobox-x.sh" /home/${USER}/.bashrc; then
  cat >> /home/${USER}/.bashrc << EOF

# AudioBox - lancement X sur tty1
if [[ -z "\${DISPLAY:-}" ]] && [[ "\$(tty 2>/dev/null)" == "/dev/tty1" ]]; then
    exec startx /home/${USER}/start-audiobox-x.sh -- -nocursor 2>/dev/null
fi
EOF
fi
log "Script de démarrage configuré"

# ── Splash screen boot ─────────────────────────────────────
title "Splash screen"
if [ -f "$SCRIPT_DIR/system/splash.png" ]; then
  cp "$SCRIPT_DIR/system/splash.png" /boot/splash.png
  cat > /etc/systemd/system/audiobox-splash.service << EOF
[Unit]
Description=AudioBox Splash Logo
DefaultDependencies=no
After=local-fs.target
Before=getty@tty1.service

[Service]
Type=forking
ExecStart=/usr/bin/fbi -d /dev/fb0 -T 1 --noverbose -a --timeout 0 /boot/splash.png
ExecStop=/usr/bin/killall fbi

[Install]
WantedBy=sysinit.target
EOF
  systemctl enable audiobox-splash 2>/dev/null || true
  log "Splash screen configuré"
else
  warn "splash.png absent - splash boot non configuré"
fi

log "Installation v1.3.0 complète !"
