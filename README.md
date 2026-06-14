# AudioBox 🎵

Lecteur audio personnalisé pour Raspberry Pi — Audiobookshelf, Radios web, YouTube, NAS.

## Prérequis

- Raspberry Pi 4 (ou 5) avec **Raspberry Pi OS Lite 64-bit** fraîchement installé
- Accès SSH ou clavier/écran pour l'installation initiale
- Connexion Internet active

## Installation rapide

```bash
# 1. Cloner ou copier le projet sur le Pi
scp -r jv/ pi@<IP_DU_PI>:~/

# 2. Se connecter et lancer l'installation
ssh pi@<IP_DU_PI>
cd ~/jv
sudo bash install.sh

# 3. Redémarrer
sudo reboot
```

## Récupérer le token dashboard

Après le redémarrage, notez votre token :

```bash
journalctl -u jv-backend | grep "Token"
```

## Accès au dashboard

| Interface | URL |
|-----------|-----|
| Depuis un PC/smartphone | `http://<IP_DU_PI>:8000` |
| Écran tactile (kiosk) | Automatique au démarrage |

## Structure du projet

```
jv/
├── backend/
│   ├── main.py                  # Point d'entrée FastAPI
│   ├── config.py                # Gestionnaire config chiffrée
│   ├── requirements.txt
│   ├── routers/
│   │   ├── abs.py               # Client Audiobookshelf
│   │   ├── player.py            # Moteur de lecture (mpv)
│   │   ├── youtube.py           # yt-dlp / recherche YouTube
│   │   ├── nas.py               # Navigation NAS monté
│   │   ├── bluetooth.py         # Gestion BT via bluetoothctl
│   │   └── settings.py          # API paramètres (protégée)
│   └── services/
│       ├── audio_manager.py     # Interface mpv via socket IPC
│       └── ws_manager.py        # WebSocket broadcast
├── frontend/
│   ├── index.html               # PWA dark mode (SPA)
│   ├── manifest.json            # Manifest PWA
│   ├── sw.js                    # Service Worker
│   └── assets/
│       └── icon-192.svg
├── config/
│   └── config.example.json      # Exemple de configuration
├── system/
│   ├── jv-backend.service # Service systemd backend
│   ├── jv-kiosk.service   # Service systemd kiosk
│   ├── 99-jv-polkit.rules # Règles polkit
│   ├── mount-nas.sh             # Script montage NAS (root)
│   └── umount-nas.sh            # Script démontage NAS (root)
└── install.sh                   # Script d'installation
```

## Sécurité

| Composant | Protection |
|-----------|------------|
| Config (clés API, mots de passe) | Chiffrement AES-128 (Fernet) sur disque |
| Endpoints `/api/settings/*` | Bearer token (32 octets aléatoires) |
| Actions système (mount, umount) | polkit rules — scripts root uniquement |
| Scripts système | `chmod 700`, `chown root:root` |
| Chromium kiosk | Sans barre d'adresse ni DevTools |

## Services systemd

```bash
# État
sudo systemctl status jv-backend
sudo systemctl status jv-kiosk

# Logs
journalctl -u jv-backend -f
journalctl -u jv-kiosk -f

# Redémarrer
sudo systemctl restart jv-backend
```

## Accès API (développement)

La documentation interactive est disponible sur :
`http://<IP_DU_PI>:8000/docs`

## Dépannage

### Le backend ne démarre pas
```bash
journalctl -u jv-backend --no-pager | tail -30
```

### Pas de son via Bluetooth
```bash
# Vérifier que PipeWire voit le device BT
sudo -u jv pw-dump | grep -i bluetooth
```

### NAS impossible à monter
```bash
# Tester manuellement
sudo mount -t cifs //ADRESSE/PARTAGE /mnt/test -o guest
```

## ⚠️ Utilisation commerciale

Ce projet est **strictement non commercial**.
Toute utilisation commerciale est interdite sans autorisation écrite.
Pour toute demande : ouvrir une issue sur GitHub.
