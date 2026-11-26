#!/bin/bash
# =============================================================================
#  Wahlen 2027 – alles starten (Doppelklick im Finder)
#
#  Startet: Grist (falls nötig), Daten-API, Grist-Abgleich, Grafik-Server
#  und öffnet das Menü im Browser. Stürzt ein Teil ab, startet er von selbst neu.
#  Beenden: in diesem Fenster Ctrl+C drücken oder das Fenster schliessen.
#
#  Wahljahr: Abfrage beim Start (2023 = Probe/Präsentation, 2027 = Wahltag),
#  oder fest als Parameter:   "./Wahlen 2027 starten.command" 2027
# =============================================================================

# ---- Einstellungen ----------------------------------------------------------
SEITEN_SCHWEIZ="3,3,2,3"     # Parteien je Seite Hochrechnung Schweiz (leer = je 3)
GRIST_INTERVALL=10           # Sekunden zwischen Grist-Abgleichen
PORT_API=8790
PORT_GRAFIK=8795
# -----------------------------------------------------------------------------

cd "$(dirname "$0")" || exit 1
PROJEKT="$(pwd)"
DB_ORDNER="$PROJEKT/Daten/Datenbank"
SERVER_ORDNER="$PROJEKT/Komponenten/_server"
LOGS="$HOME/Library/Logs/Wahlen2027"
mkdir -p "$LOGS"

ROT=$'\033[31m'; GRUEN=$'\033[32m'; GELB=$'\033[33m'; FETT=$'\033[1m'; NORMAL=$'\033[0m'
ok()     { echo "  ${GRUEN}✔${NORMAL} $*"; }
warn()   { echo "  ${GELB}!${NORMAL} $*"; }
fehler() { echo "  ${ROT}✘ $*${NORMAL}"; }
abbruch() { fehler "$*"; echo; read -r -p "Enter drücken zum Schliessen … " _; exit 1; }

printf '\033]0;Wahlen 2027 – Grafik-Anlage\007'   # Fenstertitel
clear
echo "${FETT}Wahlen 2027 – Grafik-Anlage starten${NORMAL}"
echo

# ---- Wahljahr ---------------------------------------------------------------
JAHR="$1"
if [ -z "$JAHR" ]; then
  ANTWORT=$(osascript -e 'try
    set r to display dialog "Welches Wahljahr?" & return & return & "2023 = Probe / Präsentation" & return & "2027 = Wahltag" buttons {"2027 (Wahltag)", "2023 (Probe)"} default button "2023 (Probe)" with title "Wahlen 2027" giving up after 20
    return button returned of r
  on error
    return "abbrechen"
  end try' 2>/dev/null)
  case "$ANTWORT" in
    2027*) JAHR=2027 ;;
    abbrechen) echo "Abgebrochen."; exit 0 ;;
    *) JAHR=2023 ;;
  esac
fi
ok "Wahljahr $JAHR"

# ---- Prüfungen --------------------------------------------------------------
command -v python3 >/dev/null 2>&1 || abbruch "Python 3 fehlt. Im Terminal «xcode-select --install» ausführen."
ok "$(python3 --version 2>&1)"

[ -f "$DB_ORDNER/wahlen_api.py" ] || abbruch "Daten/Datenbank nicht gefunden – liegt das Skript im Ordner «Wahlen 2027»?"
[ -f "$SERVER_ORDNER/grafik_server.py" ] || abbruch "Komponenten/_server nicht gefunden."

if [ ! -f "$DB_ORDNER/wahlen.sqlite" ]; then
  warn "Datenbank noch nicht entpackt – entpacke wahlen.sqlite.zip …"
  ( cd "$DB_ORDNER" && unzip -q -o wahlen.sqlite.zip && python3 wahlen_db.py views wahlen.sqlite >/dev/null ) \
    || abbruch "Entpacken fehlgeschlagen."
fi
( cd "$DB_ORDNER" && python3 wahlen_db.py views wahlen.sqlite >/dev/null 2>&1 )   # Ansichten aktuell halten
ok "Datenbank bereit"

# Schriften und Wappen aus Komponenten/_gemeinsam in alle Grafiken verteilen (nur Geändertes)
if python3 "$PROJEKT/Komponenten/_gemeinsam/verteilen.py" --still; then ok "Schriften und Wappen aktuell"
else warn "Schriften/Wappen konnten nicht verteilt werden (Komponenten/_gemeinsam)"; fi

# Laufen schon Teile (z. B. von einem früheren Start)?
ALT=$(pgrep -f "wahlen_api.py|grist_sync.py loop|grafik_server.py" | tr '\n' ' ')
if [ -n "$ALT" ]; then
  warn "Es laufen noch Teile eines früheren Starts – werden beendet."
  pkill -f "wahlen_api.py|grist_sync.py loop|grafik_server.py"
  sleep 1
fi
for p in $PORT_API $PORT_GRAFIK; do
  if lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1; then
    abbruch "Port $p ist von einem anderen Programm belegt: $(lsof -nP -iTCP:$p -sTCP:LISTEN | tail -1 | awk '{print $1, "PID", $2}')"
  fi
done

# ---- Grist ------------------------------------------------------------------
GRIST_URL=$(cd "$DB_ORDNER" && python3 -c "
import json, urllib.parse
u = urllib.parse.urlsplit(json.load(open('grist_config.json'))['api_url'])
print(f'{u.scheme}://{u.netloc}')" 2>/dev/null)
GRIST_URL=${GRIST_URL:-http://localhost:8484}
grist_da() { curl -s -o /dev/null -m 2 "$GRIST_URL" ; }

if grist_da; then
  ok "Grist läuft ($GRIST_URL)"
else
  warn "Grist antwortet nicht – starte OrbStack und den Grist-Container …"
  open -g -a OrbStack 2>/dev/null
  DOCKER=$(command -v docker || echo "$HOME/.orbstack/bin/docker")
  CONTAINER=""
  if [ -x "$DOCKER" ] || command -v docker >/dev/null 2>&1; then
    printf "    warte auf Docker "
    for _ in $(seq 1 30); do "$DOCKER" info >/dev/null 2>&1 && break; printf "."; sleep 2; done; echo
    CONTAINER=$("$DOCKER" ps -a --format '{{.Names}} {{.Image}}' 2>/dev/null | grep -i grist | head -1 | awk '{print $1}')
  fi
  if [ -n "$CONTAINER" ]; then
    "$DOCKER" start "$CONTAINER" >/dev/null 2>&1
    printf "    warte auf Grist "
    for _ in $(seq 1 30); do grist_da && break; printf "."; sleep 2; done; echo
  fi
  if grist_da; then ok "Grist läuft (Container $CONTAINER)"
  else warn "Grist nicht erreichbar – Grafiken laufen trotzdem, aber ohne neue Daten aus Grist. OrbStack prüfen."; fi
fi

if [ -f "$HOME/.grist_api_key" ] || [ -n "$GRIST_API_KEY" ]; then
  ok "Grist-API-Schlüssel vorhanden"
  MIT_GRIST=1
else
  warn "Kein Grist-API-Schlüssel (~/.grist_api_key) – Grist-Abgleich wird NICHT gestartet. Siehe README, Schritt A4."
  MIT_GRIST=0
fi

# ---- Starten (mit automatischem Neustart) -----------------------------------
PIDS=""
dienst() {   # dienst <Name> <Ordner> <Befehl …>
  local name="$1" ordner="$2"; shift 2
  local log="$LOGS/$name.log"
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') Start =====" >> "$log"
  (
    trap 'kill $KIND 2>/dev/null; exit 0' TERM INT HUP
    while true; do
      ( cd "$ordner" && exec python3 -u "$@" ) >> "$log" 2>&1 &
      KIND=$!
      wait $KIND
      CODE=$?
      echo "===== $(date '+%H:%M:%S') beendet (Code $CODE) – Neustart in 3 s =====" >> "$log"
      sleep 3
    done
  ) &
  PIDS="$PIDS $!"
}

aufraeumen() {
  echo
  echo "${FETT}Beende alles …${NORMAL}"
  [ -n "$TAIL_PID" ] && kill "$TAIL_PID" 2>/dev/null
  for p in $PIDS; do kill "$p" 2>/dev/null; done
  sleep 1
  pkill -f "wahlen_api.py|grist_sync.py loop|grafik_server.py" 2>/dev/null
  ok "Beendet. Das Fenster kann geschlossen werden."
  exit 0
}
trap aufraeumen INT TERM HUP

echo
echo "${FETT}Starte …${NORMAL}"
dienst daten-api    "$DB_ORDNER"     wahlen_api.py --jahr "$JAHR" --port $PORT_API
[ "$MIT_GRIST" = 1 ] && \
dienst grist-sync   "$DB_ORDNER"     grist_sync.py loop --intervall $GRIST_INTERVALL --jahr "$JAHR"
dienst grafik       "$SERVER_ORDNER" grafik_server.py --jahr "$JAHR" --port $PORT_GRAFIK \
                                     --wahlen-api "http://127.0.0.1:$PORT_API/api" --seiten-schweiz "$SEITEN_SCHWEIZ"

warte_auf() {   # warte_auf <URL> <Name>
  for _ in $(seq 1 40); do curl -s -o /dev/null -m 1 "$1" && { ok "$2"; return 0; }; sleep 0.25; done
  fehler "$2 startet nicht – Protokoll: $LOGS"; return 1
}
warte_auf "http://127.0.0.1:$PORT_API/api" "Daten-API    http://127.0.0.1:$PORT_API/api"
warte_auf "http://127.0.0.1:$PORT_GRAFIK/" "Grafik-Server http://127.0.0.1:$PORT_GRAFIK/"
[ "$MIT_GRIST" = 1 ] && ok "Grist-Abgleich alle $GRIST_INTERVALL s"

open "http://127.0.0.1:$PORT_GRAFIK/"

echo
echo "${FETT}Bereit.${NORMAL}  Menü: ${FETT}http://127.0.0.1:$PORT_GRAFIK/${NORMAL}"
echo "  OBS-Browserquelle: http://127.0.0.1:$PORT_GRAFIK/renderer  (1920×1080) – in OBS einmal «Aktualisieren»"
echo "  Videowand:         http://127.0.0.1:$PORT_GRAFIK/renderer/wand  (Vollbild, eigener Ausgang)"
echo "  Protokolle:        $LOGS"
echo
echo "${GELB}Dieses Fenster offen lassen. Beenden mit Ctrl+C (oder Fenster schliessen).${NORMAL}"
echo "-------------------------------------------------------------------------------"
touch "$LOGS/daten-api.log" "$LOGS/grist-sync.log" "$LOGS/grafik.log"
tail -n 0 -F "$LOGS/daten-api.log" "$LOGS/grist-sync.log" "$LOGS/grafik.log" &
TAIL_PID=$!
wait $TAIL_PID
