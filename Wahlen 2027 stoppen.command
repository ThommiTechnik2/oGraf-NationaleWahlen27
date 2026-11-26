#!/bin/bash
# Wahlen 2027 – alles beenden (falls das Start-Fenster schon zu ist)
echo "Beende Daten-API, Grist-Abgleich und Grafik-Server …"
pkill -f "Wahlen 2027 starten.command" 2>/dev/null
pkill -f "wahlen_api.py|grist_sync.py loop|grafik_server.py" 2>/dev/null
sleep 1
if pgrep -f "wahlen_api.py|grist_sync.py loop|grafik_server.py" >/dev/null; then
  pkill -9 -f "wahlen_api.py|grist_sync.py loop|grafik_server.py"
fi
echo "Beendet. Grist (OrbStack) und OBS laufen weiter."
sleep 2
