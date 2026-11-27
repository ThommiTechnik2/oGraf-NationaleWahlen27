#!/bin/bash
# =============================================================================
#  Wahlen 2027 – alles starten (Linux Mint / Ubuntu)
#
#  Startet: Grist (Docker, falls nötig), Daten-API, Grist-Abgleich, Grafik-Server
#  und öffnet das Menü im Browser. Stürzt ein Teil ab, startet er von selbst neu.
#  Beenden: in diesem Fenster Ctrl+C drücken oder das Fenster schliessen.
#
#  Doppelklick im Dateimanager (Nemo) → «Ausführen» – das Skript öffnet sich selbst
#  in einem Terminalfenster. Oder im Terminal:   ./"Wahlen 2027 starten.sh" [2023|2027]
#  Einmalig ausführbar machen:                    chmod +x "Wahlen 2027 starten.sh"
# =============================================================================

# ---- Einstellungen ----------------------------------------------------------
SEITEN_SCHWEIZ="3,3,2,3"     # Parteien je Seite Hochrechnung Schweiz (leer = je 3)
GRIST_INTERVALL=10           # Sekunden zwischen Grist-Abgleichen
PORT_API=8790
PORT_GRAFIK=8795
# Bedienung vom Laptop aus (Browser, Stream Deck): 0.0.0.0 = im Netz erreichbar, 127.0.0.1 = nur dieser Rechner
GRAFIK_HOST="0.0.0.0"
# CasparCG (SDI-Ausgabe über DeckLink): auto = starten, wenn installiert · aus = nie
CASPARCG="auto"
CASPAR_PORT=5250
# -----------------------------------------------------------------------------

# Per Doppelklick gestartet (kein Terminal)? Dann in einem Terminalfenster neu öffnen.
if [ ! -t 1 ] && [ -n "$DISPLAY$WAYLAND_DISPLAY" ] && [ -z "$WAHLEN_IM_TERMINAL" ]; then
  export WAHLEN_IM_TERMINAL=1
  for t in x-terminal-emulator gnome-terminal xfce4-terminal mate-terminal konsole xterm; do
    if command -v "$t" >/dev/null 2>&1; then
      case "$t" in
        gnome-terminal) exec gnome-terminal -- bash "$0" "$@" ;;
        *)              exec "$t" -e bash "$0" "$@" ;;
      esac
    fi
  done
fi

cd "$(dirname "$(readlink -f "$0")")" || exit 1
PROJEKT="$(pwd)"
DB_ORDNER="$PROJEKT/Daten/Datenbank"
SERVER_ORDNER="$PROJEKT/Komponenten/_server"
LOGS="${XDG_STATE_HOME:-$HOME/.local/state}/Wahlen2027"
mkdir -p "$LOGS"

ROT=$'\033[31m'; GRUEN=$'\033[32m'; GELB=$'\033[33m'; FETT=$'\033[1m'; NORMAL=$'\033[0m'
ok()     { echo "  ${GRUEN}✔${NORMAL} $*"; }
warn()   { echo "  ${GELB}!${NORMAL} $*"; }
fehler() { echo "  ${ROT}✘ $*${NORMAL}"; }
abbruch() { fehler "$*"; echo; read -r -p "Enter drücken zum Schliessen … " _; exit 1; }

# Ohne curl/lsof auskommen: Prüfungen mit Python
erreichbar() { python3 - "$1" <<'PY' >/dev/null 2>&1
import sys, urllib.request, urllib.error
try:
    urllib.request.urlopen(sys.argv[1], timeout=1.5)
except urllib.error.HTTPError:
    pass                      # Server antwortet (auch 401/404 heisst: läuft)
PY
}
port_belegt() { python3 - "$1" <<'PY' >/dev/null 2>&1
import socket, sys
s = socket.socket(); s.settimeout(0.5)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PY
}

printf '\033]0;Wahlen 2027 – Grafik-Anlage\007'   # Fenstertitel
clear
echo "${FETT}Wahlen 2027 – Grafik-Anlage starten${NORMAL}"
echo

# ---- Wahljahr ---------------------------------------------------------------
JAHR="$1"
if [ -z "$JAHR" ]; then
  if command -v zenity >/dev/null 2>&1 && [ -n "$DISPLAY$WAYLAND_DISPLAY" ]; then
    ANTWORT=$(zenity --question --title="Wahlen 2027" --timeout=20 \
              --text="Welches Wahljahr?\n\n2023 = Probe / Präsentation\n2027 = Wahltag" \
              --ok-label="2023 (Probe)" --cancel-label="2027 (Wahltag)" 2>/dev/null; echo $?)
    case "$ANTWORT" in
      1) JAHR=2027 ;;
      *) JAHR=2023 ;;      # 0 = 2023, 5 = Zeit abgelaufen → 2023
    esac
  else
    read -r -t 20 -p "Welches Wahljahr? [2023 = Probe / 2027 = Wahltag] (Enter = 2023): " JAHR
    echo
  fi
  JAHR=${JAHR:-2023}
fi
case "$JAHR" in 2023|2027) ;; *) abbruch "Unbekanntes Wahljahr: $JAHR (2023 oder 2027)";; esac
ok "Wahljahr $JAHR"

# ---- Prüfungen --------------------------------------------------------------
command -v python3 >/dev/null 2>&1 || abbruch "Python 3 fehlt: sudo apt install python3"
ok "$(python3 --version 2>&1)"

[ -f "$DB_ORDNER/wahlen_api.py" ] || abbruch "Daten/Datenbank nicht gefunden – liegt das Skript im Ordner «Wahlen 2027»?"
[ -f "$SERVER_ORDNER/grafik_server.py" ] || abbruch "Komponenten/_server nicht gefunden."

if [ ! -f "$DB_ORDNER/wahlen.sqlite" ]; then
  warn "Datenbank noch nicht entpackt – entpacke wahlen.sqlite.zip …"
  ( cd "$DB_ORDNER" && python3 -c "import zipfile; zipfile.ZipFile('wahlen.sqlite.zip').extractall('.')" \
      && python3 wahlen_db.py views wahlen.sqlite >/dev/null ) || abbruch "Entpacken fehlgeschlagen."
fi
( cd "$DB_ORDNER" && python3 wahlen_db.py views wahlen.sqlite >/dev/null 2>&1 )   # Ansichten aktuell halten
ok "Datenbank bereit"

# Schriften und Wappen aus Komponenten/_gemeinsam in alle Grafiken verteilen (nur Geändertes)
if python3 "$PROJEKT/Komponenten/_gemeinsam/verteilen.py" --still; then ok "Schriften und Wappen aktuell"
else warn "Schriften/Wappen konnten nicht verteilt werden (Komponenten/_gemeinsam)"; fi

# Laufen schon Teile (z. B. von einem früheren Start)?
MUSTER="wahlen_api.py|grist_sync.py loop|grafik_server.py|casparcg-server"
if pgrep -f "$MUSTER" >/dev/null; then
  warn "Es laufen noch Teile eines früheren Starts – werden beendet."
  pkill -f "$MUSTER"; sleep 1
fi
# ---- CasparCG ---------------------------------------------------------------
CASPAR_BIN=""
if [ "$CASPARCG" != "aus" ]; then
  for b in casparcg-server-2.6 casparcg-server-2.5 casparcg-server-2.4 casparcg-server casparcg; do
    command -v "$b" >/dev/null 2>&1 && { CASPAR_BIN=$(command -v "$b"); break; }
  done
  if [ -n "$CASPAR_BIN" ]; then
    CASPAR_ORDNER="$LOGS/casparcg"
    mkdir -p "$CASPAR_ORDNER"/{media,log,data,template}
    cp "$SERVER_ORDNER/casparcg/casparcg.config" "$CASPAR_ORDNER/casparcg.config" \
      || abbruch "casparcg.config fehlt in Komponenten/_server/casparcg"
    ok "CasparCG gefunden ($CASPAR_BIN)"
  else
    warn "CasparCG nicht installiert – keine SDI-Ausgabe (Grafiken laufen trotzdem, z. B. in OBS)."
  fi
fi

for p in $PORT_API $PORT_GRAFIK $([ -n "$CASPAR_BIN" ] && echo $CASPAR_PORT); do
  port_belegt $p && abbruch "Port $p ist von einem anderen Programm belegt (anzeigen mit: ss -ltnp | grep $p)"
done

# ---- Grist (Docker) ---------------------------------------------------------
GRIST_URL=$(cd "$DB_ORDNER" && python3 -c "
import json, urllib.parse
u = urllib.parse.urlsplit(json.load(open('grist_config.json'))['api_url'])
print(f'{u.scheme}://{u.netloc}')" 2>/dev/null)
GRIST_URL=${GRIST_URL:-http://localhost:8484}

if erreichbar "$GRIST_URL"; then
  ok "Grist läuft ($GRIST_URL)"
elif command -v docker >/dev/null 2>&1; then
  warn "Grist antwortet nicht – starte den Grist-Container …"
  if ! docker info >/dev/null 2>&1; then
    warn "Docker antwortet nicht. Läuft der Dienst (sudo systemctl start docker)? Ist der Benutzer in der Gruppe «docker»?"
  fi
  CONTAINER=$(docker ps -a --format '{{.Names}} {{.Image}}' 2>/dev/null | grep -i grist | head -1 | awk '{print $1}')
  if [ -n "$CONTAINER" ]; then
    docker start "$CONTAINER" >/dev/null 2>&1
    printf "    warte auf Grist "
    for _ in $(seq 1 30); do erreichbar "$GRIST_URL" && break; printf "."; sleep 2; done; echo
  fi
  if erreichbar "$GRIST_URL"; then ok "Grist läuft (Container $CONTAINER)"
  else warn "Grist nicht erreichbar – Grafiken laufen trotzdem, aber ohne neue Daten aus Grist."; fi
else
  warn "Grist nicht erreichbar und Docker nicht installiert – Grafiken laufen ohne neue Daten aus Grist."
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
      if [ "$1" = "--programm" ]; then shift_prog=("${@:2}"); ( cd "$ordner" && exec "${shift_prog[@]}" ) >> "$log" 2>&1 &
      else ( cd "$ordner" && exec python3 -u "$@" ) >> "$log" 2>&1 &
      fi
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
  pkill -f "$MUSTER" 2>/dev/null
  ok "Beendet. Das Fenster kann geschlossen werden."
  exit 0
}
trap aufraeumen INT TERM HUP

echo
echo "${FETT}Starte …${NORMAL}"
dienst daten-api    "$DB_ORDNER"     wahlen_api.py --jahr "$JAHR" --port $PORT_API
[ "$MIT_GRIST" = 1 ] && \
dienst grist-sync   "$DB_ORDNER"     grist_sync.py loop --intervall $GRIST_INTERVALL --jahr "$JAHR"
[ -n "$CASPAR_BIN" ] && \
dienst casparcg     "$CASPAR_ORDNER" --programm "$CASPAR_BIN" casparcg.config
CASPAR_ARG=()
[ -n "$CASPAR_BIN" ] && CASPAR_ARG=(--casparcg "127.0.0.1:$CASPAR_PORT")
dienst grafik       "$SERVER_ORDNER" grafik_server.py --jahr "$JAHR" --port $PORT_GRAFIK --host "$GRAFIK_HOST" \
                                     --wahlen-api "http://127.0.0.1:$PORT_API/api" --seiten-schweiz "$SEITEN_SCHWEIZ" \
                                     "${CASPAR_ARG[@]}"

warte_auf() {   # warte_auf <URL> <Name>
  for _ in $(seq 1 40); do erreichbar "$1" && { ok "$2"; return 0; }; sleep 0.25; done
  fehler "$2 startet nicht – Protokoll: $LOGS"; return 1
}
warte_auf "http://127.0.0.1:$PORT_API/api" "Daten-API    http://127.0.0.1:$PORT_API/api"
warte_auf "http://127.0.0.1:$PORT_GRAFIK/" "Grafik-Server http://127.0.0.1:$PORT_GRAFIK/"
[ "$MIT_GRIST" = 1 ] && ok "Grist-Abgleich alle $GRIST_INTERVALL s"
[ -n "$CASPAR_BIN" ] && ok "CasparCG läuft – Grafik-Server lädt die Renderer-Seiten selbst (Menü: Lampe «CasparCG (SDI)»)"
IP=$(hostname -I 2>/dev/null | awk '{print $1}')

if [ -n "$DISPLAY$WAYLAND_DISPLAY" ] && command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://127.0.0.1:$PORT_GRAFIK/" >/dev/null 2>&1 &
fi

echo
echo "${FETT}Bereit.${NORMAL}  Menü: ${FETT}http://127.0.0.1:$PORT_GRAFIK/${NORMAL}"
echo "  OBS-Browserquelle: http://127.0.0.1:$PORT_GRAFIK/renderer  (1920×1080) – in OBS einmal «Aktualisieren»"
echo "  Videowand:         http://127.0.0.1:$PORT_GRAFIK/renderer/wand  (Vollbild, eigener Ausgang)"
[ "$GRAFIK_HOST" = "0.0.0.0" ] && [ -n "$IP" ] && \
echo "  Vom Laptop aus:    http://$IP:$PORT_GRAFIK/   (Companion: Base URL http://$IP:$PORT_GRAFIK)"
echo "  Protokolle:        $LOGS"
echo
echo "${GELB}Dieses Fenster offen lassen. Beenden mit Ctrl+C (oder Fenster schliessen).${NORMAL}"
echo "-------------------------------------------------------------------------------"
touch "$LOGS/daten-api.log" "$LOGS/grist-sync.log" "$LOGS/grafik.log"
LOGLISTE=("$LOGS/daten-api.log" "$LOGS/grist-sync.log" "$LOGS/grafik.log")
[ -n "$CASPAR_BIN" ] && { touch "$LOGS/casparcg.log"; LOGLISTE+=("$LOGS/casparcg.log"); }
tail -n 0 -F "${LOGLISTE[@]}" &
TAIL_PID=$!
wait $TAIL_PID
