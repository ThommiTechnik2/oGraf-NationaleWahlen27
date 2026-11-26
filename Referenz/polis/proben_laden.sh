#!/bin/bash
# =============================================================================
#  Polis-API: Beispielantworten zur Wahl vom 22.10.2023 holen (nur zum Anschauen)
#
#  Ruft NUR lesende Abfragen auf (GET Polis.Cases, .DataConditions, .Locations, .Elections).
#  Niemals Flush*/EnableCache/DisableCache – die wirken für alle Nutzer der Schnittstelle.
#
#  Aufruf:  bash proben_laden.sh
#  Ergebnis: Ordner «proben» neben diesem Skript
# =============================================================================
cd "$(dirname "$0")" || exit 1
mkdir -p proben && cd proben || exit 1
B="https://polisapi.media.int/v2"

# Schlüssel: Datei ~/.polis_api_key (chmod 600) oder Umgebungsvariable POLIS_AUTH_KEY.
# Er wird nie ausgegeben und gehört nicht in den Projektordner.
KEY="${POLIS_AUTH_KEY:-}"
[ -z "$KEY" ] && [ -f "$HOME/.polis_api_key" ] && KEY=$(tr -d ' \r\n' < "$HOME/.polis_api_key")
if [ -z "$KEY" ]; then
  echo "Kein Polis-Schlüssel gefunden (~/.polis_api_key). Siehe Anleitung im Chat bzw. README."
  exit 1
fi

hole() {   # hole <datei> <pfad?abfrage>
  local code hinweis=""
  code=$(curl -s -G -m 90 -w "%{http_code}" -o "$1" --data-urlencode "AuthKey=$KEY" "$B/$2")
  grep -q "Authentication Error" "$1" 2>/dev/null && hinweis="  ← Schlüssel abgelehnt"
  printf "  %-34s HTTP %s  %8s Bytes%s\n" "$1" "$code" "$(wc -c < "$1" | tr -d ' ')" "$hinweis"
}

feld() {   # feld <datei> <python-ausdruck auf variable d>  → gibt Wert aus (nur lokal, kein Netz)
  python3 - "$1" "$2" <<'PY'
import json, re, sys, datetime as dt
d = json.load(open(sys.argv[1], encoding="utf-8"))
def datum(v):
    m = re.search(r"/Date\((-?\d+)", str(v or ""))
    if m:
        return (dt.datetime(1970, 1, 1) + dt.timedelta(milliseconds=int(m.group(1)) + 7200000)).date().isoformat()
    return str(v or "")[:10]
liste = lambda x: x if isinstance(x, list) else (x.get("Result") or x.get("Results") or x.get("Data") or x.get("Items") or [x]) if isinstance(x, dict) else []
try:
    print(eval(sys.argv[2]) or "")
except Exception as e:
    print("")
PY
}

echo "Polis-API – Beispielantworten (nur lesen)"
hole cases.json          "Polis.Cases?ListAllCases=true&format=json"
hole dataconditions.json "Polis.DataConditions?format=json"
hole kantone.json        "Polis.Locations?Type=2&format=json"

CASE=$(feld cases.json 'next((c.get("Id") for c in liste(d) if datum(c.get("Date")) == "2023-10-22"), "")')
LU=$(feld kantone.json 'next((k.get("Id") for k in liste(d) if (k.get("ShortName") or "").upper() == "LU"), "")')
echo "  Wahl 2023: CaseId=${CASE:-nicht gefunden}, Kanton LU: LocationId=${LU:-nicht gefunden}"

if [ -n "$CASE" ]; then
  hole case_2023.json               "Polis.Cases?CaseId=$CASE&format=json"
  hole resultat_ch_parteien.json    "Polis.Elections?CaseId=$CASE&LocationTypeId=1&DataConditionId=3&SelectOnly=2&format=json"
  hole resultat_ch_meta.json        "Polis.Elections?CaseId=$CASE&LocationTypeId=1&DataConditionId=3&SelectOnly=4&format=json"
  hole hochrechnung1_ch.json        "Polis.Elections?CaseId=$CASE&LocationTypeId=1&DataConditionId=4&SelectOnly=2&format=json"
  hole resultat_kantone_meta.json   "Polis.Elections?CaseId=$CASE&LocationTypeId=2&DataConditionId=3&SelectOnly=4&format=json"
  [ -n "$LU" ] && hole resultat_lu_parteien.json "Polis.Elections?CaseId=$CASE&LocationId=$LU&DataConditionId=3&SelectOnly=2&format=json"
  [ -n "$LU" ] && hole resultat_lu_kandidierende.json "Polis.Elections?CaseId=$CASE&LocationId=$LU&DataConditionId=3&SelectOnly=1&format=json"
fi
echo
echo "Fertig. HTTP 200 = ok, 401/403 = Schlüssel nötig, 404 = Abfrage so nicht vorhanden."
