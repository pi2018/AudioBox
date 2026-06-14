#!/bin/bash
# Installation de librespot pour Spotify Connect sur AudioBox
set -euo pipefail

echo "Installation de librespot (Spotify Connect)..."

# Installer les dépendances
apt-get install -y -qq libasound2-dev pkg-config

# Installer Rust si pas présent
if ! command -v cargo &>/dev/null; then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
fi

# Compiler librespot
cargo install librespot

# Créer le service systemd
cat > /etc/systemd/system/audiobox-spotify.service << 'SERVICE'
[Unit]
Description=AudioBox Spotify Connect (librespot)
After=network.target sound.target pipewire.service
Wants=pipewire.service

[Service]
Type=simple
User=jv
Group=jv
Environment=HOME=/home/jv
Environment=XDG_RUNTIME_DIR=/run/user/1000
ExecStart=/home/${USER}/.cargo/bin/librespot \
    --name "AudioBox" \
    --bitrate 320 \
    --backend pipe \
    --device-type speaker \
    --initial-volume 80
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable audiobox-spotify
systemctl start audiobox-spotify

echo "✓ Spotify Connect installé !"
echo "  Ouvre Spotify sur ton téléphone et cherche 'AudioBox' comme enceinte"
