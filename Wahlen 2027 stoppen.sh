#!/bin/bash
# Wahlen 2027 – alles beenden (Linux), falls das Start-Fenster schon zu ist
MUSTER="wahlen_api.py|grist_sync.py loop|grafik_server.py|casparcg-server"
echo "Beende Daten-API, Grist-Abgleich und Grafik-Server …"
pkill -f "Wahlen 2027 starten.sh" 2>/dev/null
pkill -f "$MUSTER" 2>/dev/null
sleep 1
pgrep -f "$MUSTER" >/dev/null && pkill -9 -f "$MUSTER"
echo "Beendet (inkl. CasparCG). Grist (Docker) läuft weiter."
sleep 2
