#!/bin/bash
# Testlauf des Grist-Abgleichs gegen den Nachbau der Grist-API
set -e
cd "$(dirname "$0")"
T=$(mktemp -d)
cp ../wahlen.sqlite "$T/wahlen.sqlite"
python3 -I ../wahlen_db.py views "$T/wahlen.sqlite" >/dev/null
echo -n "testschluessel" > "$T/key"
cat > "$T/config.json" <<EOF
{"api_url": "http://127.0.0.1:8495/api", "doc_id": "WahlenTest", "api_key_datei": "$T/key", "db": "$T/wahlen.sqlite", "wahl_jahr": 2023}
EOF
python3 -I mock_grist.py 8495 & PID=$!
trap "kill $PID" EXIT
sleep 1
API="http://127.0.0.1:8495/api/docs/WahlenTest"
AUTH="Authorization: Bearer testschluessel"

echo "== setup (zweimal: der zweite Lauf darf nichts ändern)"
python3 -I ../grist_sync.py setup --config "$T/config.json"
python3 -I ../grist_sync.py setup --config "$T/config.json"

echo "== erster sync (Grist leer)"
python3 -I ../grist_sync.py sync --config "$T/config.json"

echo "== Redaktion trägt in Grist ein: Farbe SVP, Anzeigename GRÜNE, eine Hochrechnung, eine Bauchbinde, Korrektur SH"
SVP=$(curl -s -H "$AUTH" "$API/tables/Parteien/records" | python3 -c "import sys,json;print([r['id'] for r in json.load(sys.stdin)['records'] if r['fields']['partei_id']==4][0])")
GRUENE=$(curl -s -H "$AUTH" "$API/tables/Parteien/records" | python3 -c "import sys,json;print([r['id'] for r in json.load(sys.stdin)['records'] if r['fields']['partei_id']==13][0])")
curl -s -X PATCH -H "$AUTH" -H "Content-Type: application/json" "$API/tables/Parteien/records" \
  -d "{\"records\":[{\"id\":$SVP,\"fields\":{\"farbe\":\"#4B8A3E\",\"reihenfolge\":10}},{\"id\":$GRUENE,\"fields\":{\"anzeige_de\":\"Grüne\",\"farbe\":\"#84B547\"}}]}"
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" "$API/tables/Hochrechnungen/records" \
  -d '{"records":[{"fields":{"wahl_jahr":2023,"rat":"NR","institut":"GFS Bern","nummer":1,"zeitpunkt":1698000000,"partei_id":4,"staerke":28.6,"staerke_fehler":1.1,"sitze":63,"freigegeben":true}},
                  {"fields":{"wahl_jahr":2023,"rat":"NR","institut":"GFS Bern","nummer":2,"zeitpunkt":1698010000,"partei_id":4,"staerke":28.0,"staerke_fehler":0.8,"sitze":62,"freigegeben":false}}]}' >/dev/null
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" "$API/tables/Bauchbinden/records" \
  -d '{"records":[{"fields":{"zeile1":"Lukas Golder","zeile2":"Politikwissenschafter GFS Bern","kategorie":"Expertise","sprache":"de","freigegeben":true}}]}' >/dev/null
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" "$API/tables/SR_Korrekturen/records" \
  -d '{"records":[{"fields":{"wahl_jahr":2023,"kanton_nummer":14,"name":"Stocker","vorname":"Simon","gewaehlt":false,"grund":"Test: Neuwahl SH"}},
                  {"fields":{"wahl_jahr":2023,"kanton_nummer":14,"name":"Testperson","vorname":"Neu","partei_id":1,"gewaehlt":true,"grund":"Test: Neuwahl SH"}}]}' >/dev/null

echo "== zweiter sync"
python3 -I ../grist_sync.py sync --config "$T/config.json"

echo "== Prüfungen in SQLite"
python3 -I - "$T/wahlen.sqlite" <<'PY'
import sqlite3, sys
db = sqlite3.connect(sys.argv[1]); q = lambda s: db.execute(s).fetchall()
ok = True
def pruefe(name, ist, soll):
    global ok
    r = "OK  " if ist == soll else "FEHLER"
    ok &= ist == soll
    print(f"  {r} {name}: {ist}" + ("" if ist == soll else f"  (erwartet {soll})"))
pruefe("Farbe SVP", q("select farbe, reihenfolge from partei where partei_id=4"), [("#4B8A3E", 10)])
pruefe("Anzeigename Grüne in v_partei_ch", q("select name_de from v_partei_ch where wahl_jahr=2023 and partei_id=13"), [("Grüne",)])
pruefe("BFS-Kurzname bleibt", q("select kurz_de from partei where partei_id=13"), [("GRÜNE",)])
pruefe("nur freigegebene Hochrechnung", q("select nummer, sitze, sitze_veraenderung from v_hochrechnung_aktuell"), [(1, 63, None)])
pruefe("Bauchbinde", q("select zeile1, kategorie from v_bauchbinde"), [("Lukas Golder", "Expertise")])
pruefe("SR SH nach Korrektur", sorted(q("select name, partei from v_sr_gewaehlte where wahl_jahr=2023 and kanton='SH'")),
       [("Germann", "SVP"), ("Testperson", "FDP")])
pruefe("SR total weiterhin 46", q("select count(*) from v_sr_gewaehlte where wahl_jahr=2023"), [(46,)])
sys.exit(0 if ok else 1)
PY

echo "== Prüfungen in Grist (Nachbau)"
python3 -I - "$API" <<'PY'
import json, sys, urllib.request
api = sys.argv[1]
def get(t):
    r = urllib.request.Request(f"{api}/tables/{t}/records", headers={"Authorization": "Bearer testschluessel"})
    return [x["fields"] for x in json.load(urllib.request.urlopen(r))["records"]]
ok = True
for t, soll in [("Parteien", 19), ("Resultat_Partei_CH", 15), ("Resultat_Kantone", 26), ("Resultat_NR_Gewaehlte", 200), ("Resultat_SR_Gewaehlte", 46)]:
    n = len(get(t)); ok &= n == soll
    print(f"  {'OK  ' if n == soll else 'FEHLER'} {t}: {n} Zeilen" + ("" if n == soll else f" (erwartet {soll})"))
p = {r["partei_id"]: r for r in get("Parteien")}
farbe_ok = p[4]["farbe"] == "#4B8A3E" and p[4]["bfs_kurz_de"] == "SVP"
ok &= farbe_ok
print(f"  {'OK  ' if farbe_ok else 'FEHLER'} Redaktionsfarbe nach push erhalten: {p[4]['farbe']}")
ch = {r["partei_id"]: r for r in get("Resultat_Partei_CH")}
ok &= ch[4]["sitze"] == 62
print(f"  {'OK  ' if ch[4]['sitze'] == 62 else 'FEHLER'} SVP Sitze in Grist: {ch[4]['sitze']}")
sys.exit(0 if ok else 1)
PY

echo "== dritter sync ohne Änderungen (keine doppelten Zeilen)"
python3 -I ../grist_sync.py sync --config "$T/config.json" | grep -E "Resultat_NR|Parteien"
echo "ALLE TESTS BESTANDEN"
rm -rf "$T"
