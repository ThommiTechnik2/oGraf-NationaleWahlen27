#!/usr/bin/env python3
"""
Abgleich zwischen Grist (Redaktion) und der Wahlen-Datenbank (SQLite).

  Grist  -> SQLite : Parteien (Anzeigenamen, Farbe, Reihenfolge, Links-rechts), Hochrechnungen,
                     Bauchbinden, Ständerats-Korrekturen
  SQLite -> Grist  : BFS-Stammdaten der Parteien (Kurznamen) und verdichtete Resultate zur Ansicht
                     (Parteien CH/Kanton, Fortschritt pro Kanton, Gewählte NR/SR)

Befehle:
  setup  [--config DATEI]                 Fehlende Tabellen und Spalten in Grist anlegen (ändert keine Daten)
  pull   [--config DATEI]                 Grist -> SQLite
  push   [--config DATEI] [--jahr J]      SQLite -> Grist (Standard: jahr aus Konfiguration)
  sync   [--config DATEI] [--jahr J]      pull, dann push
  loop   [--config DATEI] [--jahr J] [--intervall SEK]   sync wiederholt, bis Ctrl-C

Konfiguration (JSON, Standard: grist_config.json neben diesem Skript):
  {
    "api_url": "https://grist.example.ch/api",      // Basis-URL der API (bei Teams ggf. .../o/<team>/api)
    "doc_id":  "abc123...",                          // Dokument-ID aus der Grist-URL
    "api_key_datei": "~/.grist_api_key",             // Datei, die nur den Schlüssel enthält
    "db": "wahlen.sqlite",
    "wahl_jahr": 2027,
    "push_resultate": true
  }
Der Schlüssel kann statt in einer Datei auch in der Umgebungsvariable GRIST_API_KEY stehen.
Nie den Schlüssel selbst in die Konfiguration oder ins Repository schreiben.

Nur Python-Standardbibliothek, keine Zusatzpakete.
"""
import datetime as dt
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HIER = os.path.dirname(os.path.abspath(__file__))
STAPEL = 500   # Zeilen pro API-Aufruf

# ---------------------------------------------------------------------------
# Tabellen in Grist. Typen: Text, Int, Numeric, Bool, Date, DateTime:Europe/Zurich
# "redaktion": Spalten, die in Grist gepflegt und nach SQLite übernommen werden.
# "bfs":       Spalten, die das Skript aus SQLite in Grist schreibt (nur zur Info, nicht ändern).
# ---------------------------------------------------------------------------
GRIST_TABELLEN = {
    "Parteien": {
        "schluessel": "partei_id",
        "spalten": [("partei_id", "Int", "BFS-Nr."), ("bfs_kurz_de", "Text", "BFS Kürzel DE"),
                    ("bfs_kurz_fr", "Text", "BFS Kürzel FR"), ("bfs_kurz_it", "Text", "BFS Kürzel IT"),
                    ("bfs_name_de", "Text", "BFS Name DE"),
                    ("anzeige_de", "Text", "Anzeige DE"), ("anzeige_fr", "Text", "Anzeige FR"),
                    ("anzeige_it", "Text", "Anzeige IT"), ("farbe", "Text", "Farbe (#RRGGBB)"),
                    ("reihenfolge", "Int", "Reihenfolge"), ("links_rechts", "Int", "Links-rechts (0–300)")],
    },
    "Hochrechnungen": {
        "spalten": [("wahl_jahr", "Int", "Wahljahr"), ("rat", "Choice", "Rat"),
                    ("kanton_nummer", "Int", "Kanton (BFS-Nr., 0 = Schweiz)"), ("institut", "Text", "Institut"),
                    ("nummer", "Int", "Hochrechnung Nr."), ("zeitpunkt", "DateTime:Europe/Zurich", "Zeitpunkt"),
                    ("partei_id", "Int", "Partei (BFS-Nr.)"), ("staerke", "Numeric", "Wähleranteil %"),
                    ("staerke_fehler", "Numeric", "± Prozentpunkte"), ("sitze", "Int", "Sitze"),
                    ("freigegeben", "Bool", "Freigegeben")],
        "choices": {"rat": ["NR", "SR"]},
    },
    "Hochrechnung_Beteiligung": {
        "spalten": [("wahl_jahr", "Int", "Wahljahr"), ("institut", "Text", "Institut"),
                    ("nummer", "Int", "Hochrechnung Nr."), ("zeitpunkt", "DateTime:Europe/Zurich", "Zeitpunkt"),
                    ("beteiligung", "Numeric", "Wahlbeteiligung %"), ("fehler", "Numeric", "± Prozentpunkte"),
                    ("freigegeben", "Bool", "Freigegeben")],
    },
    "Bauchbinden": {
        "spalten": [("zeile1", "Text", "Zeile 1 (Name)"), ("zeile2", "Text", "Zeile 2 (Funktion)"),
                    ("kategorie", "Choice", "Kategorie"), ("sprache", "Choice", "Sprache"),
                    ("partei_id", "Int", "Partei (BFS-Nr.)"), ("kanton_nummer", "Int", "Kanton (BFS-Nr.)"),
                    ("freigegeben", "Bool", "Freigegeben")],
        "choices": {"kategorie": ["Gast", "Politik", "Expertise", "Moderation", "Reporter", "Ort"],
                    "sprache": ["de", "fr", "it", "rm", "en"]},
    },
    "SR_Korrekturen": {
        "spalten": [("wahl_jahr", "Int", "Wahljahr"), ("kanton_nummer", "Int", "Kanton (BFS-Nr.)"),
                    ("name", "Text", "Name"), ("vorname", "Text", "Vorname"), ("partei_id", "Int", "Partei (BFS-Nr.)"),
                    ("gewaehlt", "Bool", "Gilt als gewählt"), ("gueltig_ab", "Date", "Gültig ab"),
                    ("grund", "Text", "Grund")],
    },
    # --- Resultate (nur Ansicht, werden bei jedem push überschrieben) ---
    "Resultat_Partei_CH": {
        "schluessel": "partei_id", "push_aus": "v_partei_ch",
        "spalten": [("partei_id", "Int", "BFS-Nr."), ("name_de", "Text", "Partei"), ("sitze", "Int", "Sitze"),
                    ("sitze_veraenderung", "Int", "± Sitze"), ("partei_staerke", "Numeric", "Wähleranteil %"),
                    ("staerke_veraenderung", "Numeric", "± Prozentpunkte"), ("partei_rang", "Int", "Rang")],
    },
    "Resultat_Partei_Kanton": {
        "schluessel": "zeile_id", "push_aus": "v_partei_kanton",
        "spalten": [("zeile_id", "Text", "Schlüssel"), ("kuerzel", "Text", "Kanton"), ("name_de", "Text", "Partei"),
                    ("sitze", "Int", "Sitze"), ("sitze_veraenderung", "Int", "± Sitze"),
                    ("partei_staerke", "Numeric", "Wähleranteil %"), ("staerke_veraenderung", "Numeric", "± Prozentpunkte"),
                    ("kanton_abgeschlossen", "Bool", "Kanton abgeschlossen")],
        "zeile_id": lambda r: f"{r['kuerzel']}-{r['partei_id']}",
    },
    "Resultat_Kantone": {
        "schluessel": "kuerzel", "push_aus": "v_kanton_fortschritt",
        "spalten": [("kuerzel", "Text", "Kanton"), ("sitze_total", "Int", "Sitze"), ("sitze_vergeben", "Int", "Vergeben"),
                    ("abgeschlossen", "Bool", "Abgeschlossen"), ("gemeinden_abgeschlossen", "Int", "Gemeinden gemeldet"),
                    ("gemeinden_total", "Int", "Gemeinden total")],
    },
    "Resultat_NR_Gewaehlte": {
        "schluessel": "zeile_id", "push_aus": "v_nr_gewaehlte",
        "spalten": [("zeile_id", "Text", "Schlüssel"), ("kanton", "Text", "Kanton"), ("vorname", "Text", "Vorname"),
                    ("name", "Text", "Name"), ("partei", "Text", "Partei"), ("status", "Text", "bisherig/neu"),
                    ("stimmen", "Int", "Stimmen"), ("beruf", "Text", "Beruf"), ("wohnort", "Text", "Wohnort")],
        "zeile_id": lambda r: f"{r['kanton']}-{r['name']}-{r['vorname']}",
    },
    "Resultat_SR_Gewaehlte": {
        "schluessel": "zeile_id", "push_aus": "v_sr_gewaehlte",
        "spalten": [("zeile_id", "Text", "Schlüssel"), ("kanton", "Text", "Kanton"), ("vorname", "Text", "Vorname"),
                    ("name", "Text", "Name"), ("partei", "Text", "Partei"), ("status", "Text", "bisherig/neu"),
                    ("wahlgang", "Int", "Wahlgang"), ("stimmen", "Int", "Stimmen"), ("korrektur", "Text", "Korrektur")],
        "zeile_id": lambda r: f"{r['kanton']}-{r['name']}-{r['vorname']}",
    },
}


# ---------------------------------------------------------------------------
# Grist-API
# ---------------------------------------------------------------------------
class GristFehler(Exception):
    pass


class Grist:
    def __init__(self, api_url, doc_id, api_key, timeout=30):
        self.basis = f"{api_url.rstrip('/')}/docs/{urllib.parse.quote(doc_id)}"
        self.key, self.timeout = api_key, timeout

    def _anfrage(self, methode, pfad, daten=None, versuche=3):
        url = self.basis + pfad
        body = json.dumps(daten).encode("utf-8") if daten is not None else None
        for versuch in range(1, versuche + 1):
            req = urllib.request.Request(url, data=body, method=methode, headers={
                "Authorization": f"Bearer {self.key}", "Content-Type": "application/json", "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    text = r.read().decode("utf-8")
                    return json.loads(text) if text.strip() else None
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300]
                if e.code in (429, 500, 502, 503, 504) and versuch < versuche:
                    time.sleep(2 * versuch)
                    continue
                raise GristFehler(f"{methode} {pfad}: HTTP {e.code} {detail}") from None
            except urllib.error.URLError as e:
                if versuch < versuche:
                    time.sleep(2 * versuch)
                    continue
                raise GristFehler(f"{methode} {pfad}: {e.reason}") from None

    def tabellen(self):
        return {t["id"] for t in (self._anfrage("GET", "/tables") or {}).get("tables", [])}

    def spalten(self, tabelle):
        return {c["id"] for c in (self._anfrage("GET", f"/tables/{tabelle}/columns") or {}).get("columns", [])}

    def tabelle_anlegen(self, tabelle, spalten):
        self._anfrage("POST", "/tables", {"tables": [{"id": tabelle, "columns": spalten}]})

    def spalten_anlegen(self, tabelle, spalten):
        self._anfrage("POST", f"/tables/{tabelle}/columns", {"columns": spalten})

    def zeilen(self, tabelle):
        return (self._anfrage("GET", f"/tables/{tabelle}/records?limit=0") or {}).get("records", [])

    def upsert(self, tabelle, schluessel, zeilen):
        for i in range(0, len(zeilen), STAPEL):
            teil = [{"require": {schluessel: z[schluessel]},
                     "fields": {k: v for k, v in z.items() if k != schluessel}} for z in zeilen[i:i + STAPEL]]
            self._anfrage("PUT", f"/tables/{tabelle}/records", {"records": teil})

    def loeschen(self, tabelle, ids):
        for i in range(0, len(ids), STAPEL):
            self._anfrage("POST", f"/tables/{tabelle}/records/delete", ids[i:i + STAPEL])


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------
def konfig_laden(pfad):
    with open(pfad, encoding="utf-8") as f:
        k = json.load(f)
    key = os.environ.get("GRIST_API_KEY")
    if not key and k.get("api_key_datei"):
        with open(os.path.expanduser(k["api_key_datei"]), encoding="utf-8") as f:
            key = f.read().strip()
    if not key:
        sys.exit("Kein API-Schlüssel: GRIST_API_KEY setzen oder api_key_datei in der Konfiguration angeben.")
    if "api_key" in k:
        sys.exit("Bitte den Schlüssel nicht in die Konfiguration schreiben, sondern in eine eigene Datei (api_key_datei).")
    db = k.get("db", "wahlen.sqlite")
    k["db"] = db if os.path.isabs(db) else os.path.join(os.path.dirname(os.path.abspath(pfad)), db)
    return k, Grist(k["api_url"], k["doc_id"], key)


def spalten_def(tabelle):
    t = GRIST_TABELLEN[tabelle]
    out = []
    for sid, typ, label in t["spalten"]:
        fields = {"label": label, "type": typ}
        if typ == "Choice" and sid in t.get("choices", {}):
            fields["widgetOptions"] = json.dumps({"choices": t["choices"][sid]})
        out.append({"id": sid, "fields": fields})
    return out


def iso_zeit(v):
    """Grist liefert DateTime als Unix-Sekunden, Date als Unix-Sekunden um Mitternacht UTC."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return dt.datetime.fromtimestamp(v, dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    return str(v)


def iso_datum(v):
    if isinstance(v, (int, float)):
        return dt.datetime.fromtimestamp(v, dt.timezone.utc).date().isoformat()
    return v or None


def ganz(v):
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def zahl(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def log(db, richtung, tabelle, n, meldung=""):
    db.execute("INSERT INTO sync_log (zeit, richtung, tabelle, zeilen, meldung) VALUES (?,?,?,?,?)",
               (dt.datetime.now().isoformat(timespec="seconds"), richtung, tabelle, n, meldung))
    print(f"  {richtung:6s} {tabelle:24s} {n:>6} Zeilen {meldung}")


# ---------------------------------------------------------------------------
# Befehle
# ---------------------------------------------------------------------------
def setup(grist):
    vorhanden = grist.tabellen()
    for name in GRIST_TABELLEN:
        defs = spalten_def(name)
        if name not in vorhanden:
            grist.tabelle_anlegen(name, defs)
            print(f"  Tabelle angelegt: {name}")
        else:
            fehlend = [d for d in defs if d["id"] not in grist.spalten(name)]
            if fehlend:
                grist.spalten_anlegen(name, fehlend)
                print(f"  {name}: Spalten ergänzt: {', '.join(d['id'] for d in fehlend)}")
    print("Setup fertig.")


def pull(grist, db):
    # Parteien: nur redaktionelle Spalten übernehmen, Zeilen ohne bekannte partei_id ignorieren
    n = 0
    bekannt = {r[0] for r in db.execute("SELECT partei_id FROM partei")}
    for r in grist.zeilen("Parteien"):
        f = r["fields"]
        pid = ganz(f.get("partei_id"))
        if pid not in bekannt:
            continue
        db.execute("""UPDATE partei SET anzeige_de=?, anzeige_fr=?, anzeige_it=?, farbe=?, reihenfolge=?, links_rechts=?
                      WHERE partei_id=?""",
                   (f.get("anzeige_de") or None, f.get("anzeige_fr") or None, f.get("anzeige_it") or None,
                    (f.get("farbe") or "").strip() or None, ganz(f.get("reihenfolge")) or None,
                    ganz(f.get("links_rechts")) or None, pid))   # Grist liefert leere Zahlen als 0: 0 = nicht gesetzt
        n += 1
    log(db, "pull", "Parteien", n)

    # Hochrechnungen, Bauchbinden, Korrekturen: Tabelle vollständig ersetzen (Grist ist die Quelle)
    hr = grist.zeilen("Hochrechnungen")
    db.execute("DELETE FROM hochrechnung")
    db.executemany("""INSERT INTO hochrechnung (grist_id, wahl_jahr, rat, kanton_nummer, institut, nummer, zeitpunkt,
                      partei_id, staerke, staerke_fehler, sitze, freigegeben) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                   [(r["id"], ganz(f.get("wahl_jahr")), f.get("rat") or "NR", ganz(f.get("kanton_nummer")) or None,
                     f.get("institut"), ganz(f.get("nummer")),
                     iso_zeit(f.get("zeitpunkt")), ganz(f.get("partei_id")), zahl(f.get("staerke")),
                     zahl(f.get("staerke_fehler")), ganz(f.get("sitze")), 1 if f.get("freigegeben") else 0)
                    for r in hr for f in [r["fields"]] if ganz(f.get("wahl_jahr"))])
    log(db, "pull", "Hochrechnungen", len(hr))

    hb = grist.zeilen("Hochrechnung_Beteiligung")
    db.execute("DELETE FROM hochrechnung_beteiligung")
    db.executemany("""INSERT INTO hochrechnung_beteiligung (grist_id, wahl_jahr, institut, nummer, zeitpunkt,
                      beteiligung, fehler, freigegeben) VALUES (?,?,?,?,?,?,?,?)""",
                   [(r["id"], ganz(f.get("wahl_jahr")), f.get("institut"), ganz(f.get("nummer")),
                     iso_zeit(f.get("zeitpunkt")), zahl(f.get("beteiligung")), zahl(f.get("fehler")),
                     1 if f.get("freigegeben") else 0)
                    for r in hb for f in [r["fields"]] if ganz(f.get("wahl_jahr"))])
    log(db, "pull", "Hochrechnung_Beteiligung", len(hb))

    bb = grist.zeilen("Bauchbinden")
    db.execute("DELETE FROM bauchbinde")
    db.executemany("INSERT INTO bauchbinde VALUES (?,?,?,?,?,?,?,?)",
                   [(r["id"], f.get("zeile1"), f.get("zeile2"), f.get("kategorie"), f.get("sprache") or "de",
                     ganz(f.get("partei_id")), ganz(f.get("kanton_nummer")), 1 if f.get("freigegeben") else 0)
                    for r in bb for f in [r["fields"]]])
    log(db, "pull", "Bauchbinden", len(bb))

    kr = grist.zeilen("SR_Korrekturen")
    db.execute("DELETE FROM sr_korrektur")
    db.executemany("INSERT OR REPLACE INTO sr_korrektur VALUES (?,?,?,?,?,?,?,?)",
                   [(ganz(f.get("wahl_jahr")), ganz(f.get("kanton_nummer")), f.get("name"), f.get("vorname"),
                     ganz(f.get("partei_id")), 1 if f.get("gewaehlt") else 0, iso_datum(f.get("gueltig_ab")), f.get("grund"))
                    for r in kr for f in [r["fields"]]
                    if ganz(f.get("wahl_jahr")) and ganz(f.get("kanton_nummer")) and f.get("name") and f.get("vorname")])
    log(db, "pull", "SR_Korrekturen", len(kr))
    db.commit()


def push(grist, db, jahr, resultate=True):
    db.row_factory = sqlite3.Row
    # BFS-Stammdaten der Parteien nach Grist (redaktionelle Spalten bleiben unberührt)
    parteien = [{"partei_id": r["partei_id"], "bfs_kurz_de": r["kurz_de"], "bfs_kurz_fr": r["kurz_fr"],
                 "bfs_kurz_it": r["kurz_it"], "bfs_name_de": r["name_de"]}
                for r in db.execute("SELECT * FROM partei ORDER BY partei_id")]
    grist.upsert("Parteien", "partei_id", parteien)
    log(db, "push", "Parteien (BFS-Spalten)", len(parteien))

    if not resultate:
        db.commit()
        return
    for name, t in GRIST_TABELLEN.items():
        if "push_aus" not in t:
            continue
        spalten = [s[0] for s in t["spalten"]]
        zeilen = []
        for r in db.execute(f"SELECT * FROM {t['push_aus']} WHERE wahl_jahr = ?", (jahr,)):
            r = dict(r)
            if "zeile_id" in t:
                r["zeile_id"] = t["zeile_id"](r)
            z = {s: r.get(s) for s in spalten}
            for s, typ, _ in t["spalten"]:
                if typ == "Bool" and z[s] is not None:
                    z[s] = bool(z[s])
            zeilen.append(z)
        schluessel = t["schluessel"]
        grist.upsert(name, schluessel, zeilen)
        # Zeilen löschen, die es im aktuellen Stand nicht mehr gibt
        aktuell = {z[schluessel] for z in zeilen}
        alt = [r["id"] for r in grist.zeilen(name) if r["fields"].get(schluessel) not in aktuell]
        if alt:
            grist.loeschen(name, alt)
        log(db, "push", name, len(zeilen), f"(gelöscht: {len(alt)})" if alt else "")
    db.commit()


def argwert(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("setup", "pull", "push", "sync", "loop"):
        sys.exit(__doc__)
    befehl = sys.argv[1]
    konfig, grist = konfig_laden(argwert("--config", os.path.join(HIER, "grist_config.json")))
    jahr = int(argwert("--jahr", konfig.get("wahl_jahr", 2027)))
    resultate = konfig.get("push_resultate", True)

    if befehl == "setup":
        setup(grist)
        return
    db = sqlite3.connect(konfig["db"], timeout=30)
    db.execute("PRAGMA busy_timeout = 30000")
    if befehl == "pull":
        pull(grist, db)
    elif befehl == "push":
        push(grist, db, jahr, resultate)
    elif befehl == "sync":
        pull(grist, db)
        push(grist, db, jahr, resultate)
    elif befehl == "loop":
        intervall = int(argwert("--intervall", "30"))
        print(f"Abgleich alle {intervall} s, Wahljahr {jahr}. Beenden mit Ctrl-C.")
        while True:
            beginn = time.time()
            print(dt.datetime.now().strftime("%H:%M:%S"), "Abgleich")
            try:
                pull(grist, db)
                push(grist, db, jahr, resultate)
            except GristFehler as e:
                db.rollback()
                log(db, "fehler", "-", 0, str(e))
                db.commit()
            time.sleep(max(1, intervall - (time.time() - beginn)))


if __name__ == "__main__":
    try:
        main()
    except GristFehler as e:
        sys.exit(f"Grist-Fehler: {e}")
    except KeyboardInterrupt:
        print("\nBeendet.")
