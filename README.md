# 🎵 AudioBox

**Home Audio System for Raspberry Pi**

A self-contained kiosk audio player built on Raspberry Pi 4 with a 7-inch touchscreen. Combines Audiobookshelf, web radio, YouTube audio, NAS music, and Home Assistant integration in a beautiful Volumio-style dark interface.

## ✨ Features

- 📚 **Audiobooks** — Audiobookshelf integration with chapter navigation, sync, speed control
- 📻 **Web Radio** — 30,000+ stations via Radio Browser API
- ▶️ **YouTube** — Audio-only playback via yt-dlp
- 🗄️ **NAS Music** — Browse and play from network storage
- 🏠 **Home Assistant** — Full integration with webhooks and public API
- 💤 **Sleep Timer** — Auto-stop after 15/30/45/60 minutes
- 🌙 **Standby Mode** — Clock + weather display after 3 minutes
- 📱 **Mobile Optimized** — Responsive design for smartphones
- 🎨 **Dynamic Background** — Album art as blurred background
- 🔵 **Bluetooth** — Bluetooth speaker support

## 🛠️ Hardware

- Raspberry Pi 4 (2GB+ RAM)
- 7-inch DSI touchscreen (800×480)
- MicroSD card (16GB+)
- USB-C power supply (3A)

## 🚀 Installation

```bash
git clone https://github.com/pi2018/AudioBox.git
cd AudioBox
chmod +x install.sh
./install.sh
```

## ⚙️ Configuration

Edit `config/config.json` with your settings:
- Audiobookshelf server URL and API key
- NAS path and credentials
- Home Assistant webhook URLs

## 📄 License

GNU GPL v3 — Free for personal use. Commercial use prohibited.
See [LICENSE](LICENSE) for details.
