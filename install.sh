#!/bin/bash
set -e
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
log()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
title() { echo -e "\n${CYAN}${BOLD}-- $* --${NC}"; }
[[ "$EUID" -ne 0 ]] && { echo "Lancer avec : sudo bash install.sh"; exit 1; }
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/jv"
USER_NAME="${SUDO_USER:-jv}"
USER_HOME="/home/${USER_NAME}"
echo -e "${CYAN}${BOLD}=== AudioBox - Installation ===${NC}"
echo "  Utilisateur : ${USER_NAME}"

title "Installation des paquets"
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv python3-dev chromium chromium-sandbox openbox xserver-xorg xinit x11-xserver-utils mpv pipewire pipewire-alsa pipewire-audio pipewire-bin pipewire-pulse wireplumber libspa-0.2-bluetooth bluetooth bluez fbi xdotool unclutter curl git cifs-utils rfkill alsa-utils fonts-noto-color-emoji > /dev/null 2>&1
log "Paquets installes"

title "Installation yt-dlp"
pip3 install --break-system-packages -q --upgrade yt-dlp > /dev/null 2>&1 || true
log "yt-dlp installe"

title "Deploiement des fichiers"
mkdir -p "$INSTALL_DIR"
cp -r "$SCRIPT_DIR/backend" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/frontend" "$INSTALL_DIR/"
[ -d "$SCRIPT_DIR/system" ] && cp -r "$SCRIPT_DIR/system" "$INSTALL_DIR/"
mkdir -p "$INSTALL_DIR/config" "$INSTALL_DIR/logs" "$INSTALL_DIR/nas"
chown -R "$USER_NAME:$USER_NAME" "$INSTALL_DIR"
log "Fichiers deployes"

title "Environnement Python"
sudo -u "$USER_NAME" python3 -m venv "$INSTALL_DIR/venv"
sudo -u "$USER_NAME" "$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip > /dev/null 2>&1
sudo -u "$USER_NAME" "$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/backend/requirements.txt" > /dev/null 2>&1
log "Venv pret"

title "Service backend"
cat > /etc/systemd/system/jv-backend.service << EOF
[Unit]
Description=AudioBox Backend
After=network.target sound.target
Wants=network.target

[Service]
Type=simple
User=$USER_NAME
Group=$USER_NAME
WorkingDirectory=$INSTALL_DIR/backend
Environment=PYTHONUNBUFFERED=1
Environment=HOME=$USER_HOME
Environment=XDG_RUNTIME_DIR=/run/user/1000
Environment=PIPEWIRE_RUNTIME_DIR=/run/user/1000
ExecStartPre=-/usr/bin/amixer set PCM 100%
ExecStartPre=-/usr/bin/amixer set Master 100%
ExecStartPre=/bin/sleep 2
ExecStart=$INSTALL_DIR/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info --timeout-keep-alive 30
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=jv-backend

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable jv-backend > /dev/null 2>&1
log "Service backend installe"

title "Permissions sudoers"
cat > /etc/sudoers.d/audiobox << EOF
$USER_NAME ALL=(ALL) NOPASSWD: /usr/bin/systemctl start jv-backend
$USER_NAME ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop jv-backend
$USER_NAME ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart jv-backend
$USER_NAME ALL=(ALL) NOPASSWD: /usr/sbin/reboot
$USER_NAME ALL=(ALL) NOPASSWD: /usr/sbin/shutdown
EOF
chmod 0440 /etc/sudoers.d/audiobox
log "Sudoers configure"

echo "allowed_users=anybody" > /etc/X11/Xwrapper.config

title "Autologin tty1"
mkdir -p /etc/systemd/system/getty@tty1.service.d/
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf << EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $USER_NAME --noclear %I \$TERM
EOF
log "Autologin configure"

title "Script kiosk"
cat > "$USER_HOME/start-audiobox-x.sh" << 'KIOSKEOF'
#!/bin/bash
openbox &
sleep 1
xset s off
xset -dpms
xset s noblank
systemctl --user start pipewire pipewire-pulse wireplumber 2>/dev/null || true
sudo systemctl start jv-backend 2>/dev/null || true
DISPLAY=:0 exec chromium --kiosk --noerrdialogs --disable-infobars --disable-session-crashed-bubble --disable-restore-session-state --touch-events=enabled --no-first-run --check-for-update-interval=31536000 --app=file:///opt/jv/frontend/splash.html
KIOSKEOF
chmod +x "$USER_HOME/start-audiobox-x.sh"
chown "$USER_NAME:$USER_NAME" "$USER_HOME/start-audiobox-x.sh"

cat > "$USER_HOME/.xinitrc" << XINITEOF
#!/bin/bash
exec $USER_HOME/start-audiobox-x.sh
XINITEOF
chmod +x "$USER_HOME/.xinitrc"
chown "$USER_NAME:$USER_NAME" "$USER_HOME/.xinitrc"

cat > "$USER_HOME/.bash_profile" << 'PROFILEEOF'
[[ -f ~/.bashrc ]] && source ~/.bashrc
if [[ -z "${DISPLAY:-}" ]] && [[ "$(tty 2>/dev/null)" == "/dev/tty1" ]]; then
    sleep 3
    exec startx -- -nocursor 2>/dev/null
fi
PROFILEEOF
chown "$USER_NAME:$USER_NAME" "$USER_HOME/.bash_profile"

sed -i '/exec startx/d' "$USER_HOME/.bashrc" 2>/dev/null || true

mkdir -p "$USER_HOME/.config/openbox"
cat > "$USER_HOME/.config/openbox/autostart" << 'OBEOF'
xset s off
xset -dpms
xset s noblank
command -v unclutter &>/dev/null && unclutter -idle 3 -root &
OBEOF
chown -R "$USER_NAME:$USER_NAME" "$USER_HOME/.config"
log "Kiosk configure"

title "Splash boot"
if [ -f "$SCRIPT_DIR/system/splash.png" ]; then
  cp "$SCRIPT_DIR/system/splash.png" /boot/splash.png
  cat > /etc/systemd/system/audiobox-splash.service << 'SPLASHEOF'
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
SPLASHEOF
  systemctl enable audiobox-splash > /dev/null 2>&1 || true
  log "Splash configure"
else
  warn "splash.png absent"
fi

title "Bluetooth auto"
cat > /etc/systemd/system/audiobox-bluetooth.service << 'BTEOF'
[Unit]
Description=AudioBox Bluetooth unblock
After=bluetooth.service
Wants=bluetooth.service

[Service]
Type=oneshot
ExecStart=/usr/sbin/rfkill unblock bluetooth
ExecStartPost=/bin/sh -c 'sleep 3; bluetoothctl power on || true'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
BTEOF
systemctl enable audiobox-bluetooth > /dev/null 2>&1 || true
log "Bluetooth configure"

title "Demarrage backend"
systemctl start jv-backend 2>/dev/null || true
sleep 6
TOKEN=$(journalctl -u jv-backend --no-pager 2>/dev/null | grep -oP 'Dashboard Token: \K[A-Za-z0-9_-]+' | tail -1)
IP=$(hostname -I | awk '{print $1}')
echo "$TOKEN" > "$USER_HOME/audiobox-token.txt"
chown "$USER_NAME:$USER_NAME" "$USER_HOME/audiobox-token.txt" 2>/dev/null || true
echo ""
echo -e "${CYAN}========================================================${NC}"
echo -e "   ${BOLD}AudioBox installe avec succes !${NC}"
echo -e "${CYAN}========================================================${NC}"
echo -e "   Interface : ${GREEN}http://${IP}:8000${NC}"
echo -e "   Token     : ${YELLOW}${TOKEN}${NC}"
echo -e "   (sauvegarde dans ~/audiobox-token.txt)"
echo -e "${CYAN}========================================================${NC}"
echo -e "   Redemarrez : ${BOLD}sudo reboot${NC}"
echo ""
