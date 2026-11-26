# 🎵 AudioBox

**Box audio maison pour Raspberry Pi** (écran tactile 7 pouces, 800×480).
Livres audio Audiobookshelf, web radios, podcasts, YouTube (audio seul) et musique du NAS,
avec une interface sombre aux couleurs au choix, pilotable aussi depuis Home Assistant
et depuis l'appli Android.

## ✨ Ce qu'elle fait

- 📚 **Livres audio** (Audiobookshelf) — livres en plusieurs fichiers, chapitres, vitesse,
  progression enregistrée dans Audiobookshelf
- 📻 **Web radios** — plus de 30 000 stations (Radio Browser), favorites
- 🎙️ **Podcasts** — flux RSS, téléchargés par la box
- ▶️ **YouTube** — audio seul, avec yt-dlp
- 🗄️ **Musique du NAS** — partage SMB, remonté à chaque démarrage
- 💤 **Minuterie de sommeil** — tenue par la box : le son baisse doucement puis s'arrête
- 🏠 **Home Assistant** — vrai lecteur multimédia (intégration `custom_components/audiobox`) :
  radios, volume, annonces vocales qui reprennent ensuite le livre
- 📱 **Appli Android** (`android/`) — télécommande sur le Wi-Fi de la maison

## 🛠️ Matériel

- Raspberry Pi 4 (2 Go ou plus)
- Écran tactile 7 pouces (800×480)
- Carte microSD (16 Go ou plus), alimentation USB-C 3 A

## 🚀 Installation (une seule fois)

Sur le Raspberry Pi (Raspberry Pi OS) :

```bash
curl -fL https://github.com/pi2018/AudioBox/archive/refs/heads/main.tar.gz | tar xz -C ~
cd ~/AudioBox-main
sudo bash install.sh
sudo reboot
```

Ensuite, tout se règle sur l'écran : **Paramètres › Sources** (Audiobookshelf, NAS, radios).
Les mises à jour se font aussi depuis l'écran : **Paramètres › Système › Mettre à jour AudioBox**
(la box vérifie la nouvelle version, affiche le résultat et redémarre toute seule).

## 🏠 Home Assistant

HACS (Marketplace) › Dépôts personnalisés › `https://github.com/pi2018/AudioBox`, type
**Intégration** › installer › redémarrer Home Assistant › Ajouter l'intégration « AudioBox ».
Le code admin (affiché sur l'écran de la box) n'est utile que pour les annonces.

## 📄 Licence

GNU GPL v3 — usage personnel libre, usage commercial interdit. Voir [LICENSE](LICENSE).
