#!/bin/bash
set -e

echo "=== HSLU KI-Agent Server Setup ==="

# 1. Systempakete aktualisieren und ffmpeg / python installieren
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv ffmpeg git

# 2. Virtualenv anlegen & Abhängigkeiten installieren
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3. Playwright Browser & Systembibliotheken für Headless Linux installieren
playwright install
playwright install-deps

# 4. Systemd Service einrichten (optional)
if [ -f "deploy/hslu-agent.service" ]; then
    echo "Richte Systemd Service ein..."
    sudo cp deploy/hslu-agent.service /etc/systemd/system/
    sudo systemctl daemon-reload
    # sudo systemctl enable --now hslu-agent.service
fi

echo "=== Setup abgeschlossen! ==="
