#!/bin/bash
set -euo pipefail
curl -sSL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
    -o /usr/local/bin/yt-dlp
chmod +x /usr/local/bin/yt-dlp
echo "OK: $(yt-dlp --version)"
