#!/usr/bin/env python3
"""
Wahlen-Datenbank: BFS-Dateien (opendata.swiss, Format 2023) in eine SQLite-Datenbank für mehrere Wahljahre.

Befehle:
  init        <db>                         Datenbank anlegen (Schema + Ansichten), Wahljahre eintragen
  import-nr   <db> <ordner> [--jahr J]     Nationalrat: alle NRW-Dateien eines Ordners importieren
  import-sr   <db> <ordner> [--jahr J]     Ständerat: SRW-Dateien (erster/zweiter Wahlgang)
  sitze       <db> <csv> --jahr J [--spalte S] [--geprueft]
                                           Soll-Sitze pro Kanton aus CSV (kanton_nummer + Spalte)
  sitze-aus-resultat <db> --jahr J         Soll-Sitze aus den Gewählten eines abgeschlossenen Jahres ableiten
  korrektur-sr <db> --jahr J --kanton N --name X --vorname Y --gewaehlt 0|1 [--partei P] [--ab D] [--grund T]
  views       <db>                         Ansichten neu anlegen (nach Änderungen an views.sql)

Ein Import ersetzt alle Zeilen des Wahljahres in den betroffenen Tabellen (in einer Transaktion).
Redaktionelle Felder (partei.farbe, reihenfolge, links_rechts; kanton.name_de) werden nie überschrieben.
--jahr überschreibt das Wahljahr aus der Datei (z. B. um Testdaten als 2027 zu laden).
"""
import datetime as dt
import glob
import json
import os
import re
import sqlite3
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
LANGS = ("de", "fr", "it", "en")
WAHLEN = [(2019, 2015, "2019-10-20"), (2023, 2019, "2023-10-22"), (2027, 2023, "2027-10-24")]
KANTON_DE = {1: "Zürich", 2: "Bern", 3: "Luzern", 4: "Uri", 5: "Schwyz", 6: "Obwalden", 7: "Nidwalden", 8: "Glarus",
             9: "Zug", 10: "Freiburg", 11: "Solothurn", 12: "Basel-Stadt", 13: "Basel-Landschaft", 14: "Schaffhausen",
             15: "Appenzell Ausserrhoden", 16: "Appenzell Innerrhoden", 17: "St. Gallen", 18: "Graubünden",
             19: "Aargau", 20: "Thurgau", 21: "Tessin", 22: "Waadt", 23: "Wallis", 24: "Neuenburg", 25: "Genf", 26: "Jura"}
SR_SITZE_HALB = {6, 7, 12, 13, 15, 16}   # Halbkantone: 1 Ständeratssitz


# ---------- Hilfen ----------

def jetzt():
    return dt.datetime.now().isoformat(timespec="seconds")


def load(ordner, muster):
    """Lädt die Datei, deren Name genau auf das Muster passt (Regex für den Teil nach 'sd-t-17.02-')."""
    for f in glob.glob(os.path.join(ordner, "*.json")):
        if re.fullmatch(r"sd-t-17[._]02-" + muster + r"\.json", os.path.basename(f)):
            if os.path.getsize(f) == 0:
                return None, f
            with open(f, encoding="utf-8-sig") as fh:
                return json.load(fh), f
    return None, None


def b(v):
    """Boolean aus true/false, 1/0, "true"/"false" -> 1/0/None."""
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(bool(v))
    s = str(v).strip().lower()
    return 1 if s in ("true", "1") else 0 if s in ("false", "0") else None


def s(v):
    return v.strip() if isinstance(v, str) else v


def datum(v):
    if isinstance(v, str) and re.fullmatch(r"\d\d\.\d\d\.\d{4}", v):
        return f"{v[6:]}-{v[3:5]}-{v[:2]}"
    return v


def langs(lst):
    out = {k: None for k in LANGS}
    for e in lst or []:
        if e.get("langKey") in out:
            out[e["langKey"]] = s(e.get("text"))
    return out


def ersetzen(db, tabelle, jahr, zeilen, spalten, extra_where="", extra_args=()):
    db.execute(f"DELETE FROM {tabelle} WHERE wahl_jahr = ? {extra_where}", (jahr, *extra_args))
    db.executemany(f"INSERT INTO {tabelle} ({','.join(spalten)}) VALUES ({','.join('?' * len(spalten))})",
                   ([z.get(c) for c in spalten] for z in zeilen))
    return db.total_changes


def protokoll(db, jahr, datei, ts, n):
    db.execute("INSERT INTO import_log (importiert_um, wahl_jahr, datei, bfs_timestamp, zeilen) VALUES (?,?,?,?,?)",
               (jetzt(), jahr, os.path.basename(datei or ""), ts, n))


def oeffnen(pfad):
    db = sqlite3.connect(pfad)
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")   # Grafiken können lesen, während importiert wird
    return db


# ---------- Befehle ----------

NEUE_SPALTEN = {  # für Datenbanken, die mit einer älteren schema.sql angelegt wurden
    "partei": [("anzeige_de", "TEXT"), ("anzeige_fr", "TEXT"), ("anzeige_it", "TEXT")],
    "hochrechnung": [("kanton_nummer", "INTEGER")],
}


def migrieren(db):
    db.executescript(open(os.path.join(HIER, "schema.sql"), encoding="utf-8").read())
    for tabelle, spalten in NEUE_SPALTEN.items():
        vorhanden = {r[1] for r in db.execute(f"PRAGMA table_info({tabelle})")}
        for name, typ in spalten:
            if name not in vorhanden:
                db.execute(f"ALTER TABLE {tabelle} ADD COLUMN {name} {typ}")


def cmd_init(pfad):
    db = oeffnen(pfad)
    migrieren(db)
    db.executescript(open(os.path.join(HIER, "views.sql"), encoding="utf-8").read())
    for j, v, t in WAHLEN:
        db.execute("INSERT OR IGNORE INTO wahl (wahl_jahr, vorwahl_jahr, wahltag) VALUES (?,?,?)", (j, v, t))
    db.commit()
    print("Datenbank bereit:", pfad)


def cmd_views(pfad):
    db = oeffnen(pfad)
    migrieren(db)
    db.executescript(open(os.path.join(HIER, "views.sql"), encoding="utf-8").read())
    db.commit()
    print("Ansichten neu angelegt")


def stammdaten(db, meta):
    for k in meta.get("stand_kantone") or meta.get("kantone") or []:
        db.execute("""INSERT INTO kanton (kanton_nummer, kuerzel, name_bfs, name_de) VALUES (?,?,?,?)
                      ON CONFLICT(kanton_nummer) DO UPDATE SET kuerzel=excluded.kuerzel, name_bfs=excluded.name_bfs""",
                   (k["kanton_nummer"], k.get("kanton_bezeichnung_kurz"), s(k.get("kanton_bezeichnung")),
                    KANTON_DE.get(k["kanton_nummer"])))
    for p in meta.get("parteien", []):
        k, n = langs(p.get("partei_bezeichnung_kurz")), langs(p.get("partei_bezeichnung"))
        g, l = langs(p.get("parteigruppen_bezeichnung_kurz")), langs(p.get("parteipolitische_lager_bezeichnung_kurz"))
        db.execute("""INSERT INTO partei (partei_id, kurz_de, kurz_fr, kurz_it, kurz_en, name_de, name_fr, name_it, name_en,
                        parteigruppen_id, gruppe_kurz_de, gruppe_kurz_fr, gruppe_kurz_it,
                        lager_id, lager_kurz_de, lager_kurz_fr, lager_kurz_it)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                      ON CONFLICT(partei_id) DO UPDATE SET
                        kurz_de=excluded.kurz_de, kurz_fr=excluded.kurz_fr, kurz_it=excluded.kurz_it, kurz_en=excluded.kurz_en,
                        name_de=excluded.name_de, name_fr=excluded.name_fr, name_it=excluded.name_it, name_en=excluded.name_en,
                        parteigruppen_id=excluded.parteigruppen_id, gruppe_kurz_de=excluded.gruppe_kurz_de,
                        gruppe_kurz_fr=excluded.gruppe_kurz_fr, gruppe_kurz_it=excluded.gruppe_kurz_it,
                        lager_id=excluded.lager_id, lager_kurz_de=excluded.lager_kurz_de,
                        lager_kurz_fr=excluded.lager_kurz_fr, lager_kurz_it=excluded.lager_kurz_it""",
                   (p["partei_id"], k["de"], k["fr"], k["it"], k["en"], n["de"], n["fr"], n["it"], n["en"],
                    p.get("parteigruppen_id"), g["de"], g["fr"], g["it"],
                    p.get("parteipolitische_lager_id"), l["de"], l["fr"], l["it"]))
    for st in meta.get("kandidat_status", []):
        t = langs(st.get("kandidat_status"))
        db.execute("INSERT OR REPLACE INTO kandidat_status VALUES (?,?,?,?,?)",
                   (st["kandidat_status_id"], t["de"], t["fr"], t["it"], t["en"]))


def cmd_import_nr(pfad, ordner, jahr_vorgabe=None):
    db = oeffnen(pfad)
    meta, f_meta = load(ordner, r"NRW\d{4}-metadaten")
    part, f_part = load(ordner, r"NRW\d{4}-parteien")
    bet, f_bet = load(ordner, r"NRW\d{4}-wahlbeteiligung")
    kand, f_kand = load(ordner, r"NRW\d{4}-kandidierende")
    lis, f_lis = load(ordner, r"NRW\d{4}-listen")
    lgd, f_lgd = load(ordner, r"NRW\d{4}-listen-gde")
    zrp, f_zrp = load(ordner, r"NRW\d{4}-zeitreihen-parteien")
    zrf, f_zrf = load(ordner, r"NRW\d{4}-zeitreihen-frauen-beteiligung")

    quelle = part or bet or kand or meta
    if not quelle:
        sys.exit("Keine Nationalratsdateien gefunden in " + ordner)
    jahr = jahr_vorgabe or quelle.get("wahl_jahr") or quelle.get("wahljahr")
    if jahr not in {w[0] for w in WAHLEN}:
        db.execute("INSERT OR IGNORE INTO wahl (wahl_jahr, vorwahl_jahr) VALUES (?, ?)", (jahr, jahr - 4))
    n = {}
    with db:
        if meta:
            stammdaten(db, meta)

        # Stand
        st = quelle.get("stand", {})
        db.execute("DELETE FROM nr_stand WHERE wahl_jahr=?", (jahr,))
        db.execute("INSERT INTO nr_stand VALUES (?,?,?,?,?,?,?,?)",
                   (jahr, quelle.get("timestamp"), jetzt(), b(st.get("wahl_abgeschlossen")),
                    st.get("kantone_total"), st.get("kantone_abgeschlossen"),
                    st.get("gemeinden_total"), st.get("gemeinden_abgeschlossen")))
        sk = quelle.get("stand_kantone") or quelle.get("Stand_kantone") or []
        ersetzen(db, "nr_stand_kanton", jahr,
                 ({"wahl_jahr": jahr, "kanton_nummer": k["kanton_nummer"], "kanton_abgeschlossen": b(k.get("kanton_abgeschlossen")),
                   "gemeinden_total": k.get("gemeinden_total"), "gemeinden_abgeschlossen": k.get("gemeinden_abgeschlossen")} for k in sk),
                 ["wahl_jahr", "kanton_nummer", "kanton_abgeschlossen", "gemeinden_total", "gemeinden_abgeschlossen"])

        # Parteien
        if part:
            def pz(r, mit_kanton):
                z = {"wahl_jahr": jahr, "partei_id": r["partei_id"],
                     "anzahl_listen": r.get("anzahl_listen"), "anzahl_kandidierende": r.get("anzahl_kandidierende"),
                     "anzahl_kandidierende_f": r.get("anzahl_kandidierende_f"), "anzahl_kandidierende_m": r.get("anzahl_kandidierende_m"),
                     "sitze": r.get("anzahl_gewaehlte"), "sitze_f": r.get("anzahl_gewaehlte_f"), "sitze_m": r.get("anzahl_gewaehlte_m"),
                     "fiktive_waehlende": r.get("fiktive_waehlende"), "partei_staerke": r.get("partei_staerke"),
                     "partei_rang": r.get("partei_rang"), "staerkste_partei": b(r.get("flag_staerkste_partei")),
                     "bfs_letzte_wahl_sitze": r.get("letzte_wahl_anzahl_gewaehlte"),
                     "bfs_letzte_wahl_partei_staerke": r.get("letzte_wahl_partei_staerke")}
                if mit_kanton:
                    z["kanton_nummer"] = r["kanton_nummer"]
                    z["stimmen"] = r.get("stimmen_partei")
                return z
            sp = ["wahl_jahr", "partei_id", "anzahl_listen", "anzahl_kandidierende", "anzahl_kandidierende_f",
                  "anzahl_kandidierende_m", "sitze", "sitze_f", "sitze_m", "fiktive_waehlende", "partei_staerke",
                  "partei_rang", "staerkste_partei", "bfs_letzte_wahl_sitze", "bfs_letzte_wahl_partei_staerke"]
            ersetzen(db, "nr_partei_ch", jahr, (pz(r, False) for r in part.get("level_ch") or []), sp)
            ersetzen(db, "nr_partei_kanton", jahr, (pz(r, True) for r in part.get("level_kantone") or []),
                     sp + ["kanton_nummer", "stimmen"])
            gz = list(part.get("level_gemeinden") or [])
            ersetzen(db, "nr_partei_gemeinde", jahr,
                     ({"wahl_jahr": jahr, "gemeinde_nummer": r["gemeinde_nummer"], "kanton_nummer": r.get("kanton_nummer"),
                       "partei_id": r["partei_id"], "stimmen": r.get("stimmen_partei"), "partei_staerke": r.get("partei_staerke"),
                       "partei_rang": r.get("partei_rang"), "staerkste_partei": b(r.get("flag_staerkste_partei")),
                       "bfs_letzte_wahl_partei_staerke": r.get("letzte_wahl_partei_staerke")} for r in gz),
                     ["wahl_jahr", "gemeinde_nummer", "kanton_nummer", "partei_id", "stimmen", "partei_staerke",
                      "partei_rang", "staerkste_partei", "bfs_letzte_wahl_partei_staerke"])
            n["parteien_gemeinden"] = len(gz)
            protokoll(db, jahr, f_part, part.get("timestamp"), len(gz))

        # Wahlbeteiligung und Gemeinden
        if bet:
            bc = ["wahl_jahr", "ebene", "nummer", "kanton_nummer", "wahlberechtigte", "eingelegte_wahlzettel",
                  "leere_wahlzettel", "ungueltige_wahlzettel", "gueltige_wahlzettel", "wahlbeteiligung",
                  "bfs_letzte_wahl_wahlbeteiligung"]
            def bz(r, ebene, nummer, kt):
                return {"wahl_jahr": jahr, "ebene": ebene, "nummer": nummer, "kanton_nummer": kt,
                        **{c: r.get(c) for c in bc[4:-1]}, "bfs_letzte_wahl_wahlbeteiligung": r.get("letzte_wahl_wahlbeteiligung")}
            zeilen = []
            # Im Zwischenstand liefert das BFS den CH-Block mit leeren Werten: dann keine CH-Zeile
            if isinstance(bet.get("level_ch"), dict) and bet["level_ch"].get("wahlberechtigte") is not None:
                zeilen.append(bz(bet["level_ch"], "CH", 0, None))
            zeilen += [bz(r, "kanton", r["kanton_nummer"], r["kanton_nummer"]) for r in bet.get("level_kantone") or []]
            gd = bet.get("level_gemeinden") or []
            zeilen += [bz(r, "gemeinde", r["gemeinde_nummer"], r.get("kanton_nummer")) for r in gd]
            ersetzen(db, "nr_beteiligung", jahr, zeilen, bc)
            ersetzen(db, "gemeinde", jahr,
                     ({"wahl_jahr": jahr, "gemeinde_nummer": r["gemeinde_nummer"], "name": s(r.get("gemeinde_bezeichnung")),
                       "kanton_nummer": r.get("kanton_nummer")} for r in gd),
                     ["wahl_jahr", "gemeinde_nummer", "name", "kanton_nummer"])
            n["gemeinden"] = len(gd)
            protokoll(db, jahr, f_bet, bet.get("timestamp"), len(zeilen))

        # Listen
        if lis:
            lc = ["kanton_nummer", "liste_nummer_bfs", "liste_nummer_kanton", "liste_bezeichnung", "liste_verbindung",
                  "liste_unterlistenverbindung", "partei_id", "anzahl_gewaehlte", "stimmen_liste", "listen_staerke"]
            lz = [{"wahl_jahr": jahr, **{c: s(r.get(c)) for c in lc}} for r in lis.get("level_kantone") or []]
            ersetzen(db, "nr_liste", jahr, lz, ["wahl_jahr"] + lc)
            n["listen"] = len(lz)
            protokoll(db, jahr, f_lis, lis.get("timestamp"), len(lz))
        if lgd:
            lg = lgd.get("level_gemeinden") or []
            ersetzen(db, "nr_liste_gemeinde", jahr,
                     ({"wahl_jahr": jahr, "gemeinde_nummer": r["gemeinde_nummer"], "kanton_nummer": r.get("kanton_nummer"),
                       "liste_nummer_bfs": r["liste_nummer_bfs"], "partei_id": r.get("partei_id"),
                       "stimmen_liste": r.get("stimmen_liste")} for r in lg),
                     ["wahl_jahr", "gemeinde_nummer", "kanton_nummer", "liste_nummer_bfs", "partei_id", "stimmen_liste"])
            n["listen_gemeinden"] = len(lg)
            protokoll(db, jahr, f_lgd, lgd.get("timestamp"), len(lg))

        # Kandidierende
        if kand:
            kz = []
            for r in kand.get("level_kantone") or []:
                kz.append({"wahl_jahr": jahr, "kanton_nummer": r["kanton_nummer"], "liste_nummer_bfs": r["liste_nummer_bfs"],
                           "kandidat_nummer": r["kandidat_nummer"], "liste_nummer_kanton": s(r.get("liste_nummer_kanton")),
                           "kandidat_listenplatz_1": r.get("kandidat_listenplatz_1"),
                           "kandidat_listenplatz_2": r.get("kandidat_listenplatz_2"),
                           "name": s(r.get("name")), "vorname": s(r.get("vorname")), "geschlecht": r.get("geschlecht"),
                           "geburtsdatum": datum(r.get("geburtsdatum")), "geburtsjahr": r.get("geburtsjahr"),
                           "wohnort_gemeinde_nummer": r.get("wohnort_gemeinde_nummer"), "wohnort": s(r.get("wohnort")),
                           "beruf": s(r.get("beruf")), "kandidat_status_id": r.get("kandidat_status_id"),
                           "partei_id": r.get("kandidat_partei_id"), "stimmen": r.get("stimmen_kandidat"),
                           "gewaehlt": b(r.get("flag_gewaehlt"))})
            ersetzen(db, "nr_kandidat", jahr, kz, list(kz[0].keys()) if kz else ["wahl_jahr"])
            kg = kand.get("level_gemeinden") or []
            ersetzen(db, "nr_kandidat_gemeinde", jahr,
                     ({"wahl_jahr": jahr, "gemeinde_nummer": r["gemeinde_nummer"], "kanton_nummer": r["kanton_nummer"],
                       "liste_nummer_bfs": r["liste_nummer_bfs"], "kandidat_nummer": r["kandidat_nummer"],
                       "stimmen": r.get("stimmen_kandidat")} for r in kg),
                     ["wahl_jahr", "gemeinde_nummer", "kanton_nummer", "liste_nummer_bfs", "kandidat_nummer", "stimmen"])
            n["kandidierende"], n["kandidierende_gemeinden"] = len(kz), len(kg)
            protokoll(db, jahr, f_kand, kand.get("timestamp"), len(kz) + len(kg))

        # Zeitreihen (nicht jahresgebunden: ersetzt alle Jahre der Datei)
        if zrp:
            rows = [(r["wahl_jahr"], 0, r) for r in zrp.get("level_ch") or []] + \
                   [(r["wahl_jahr"], r["kanton_nummer"], r) for r in zrp.get("level_kantone") or []]
            db.execute("DELETE FROM nr_zeitreihe_partei")
            db.executemany("INSERT INTO nr_zeitreihe_partei VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                           [(j, k, r["partei_id"], r.get("anzahl_listen"), r.get("anzahl_kandidierende"), r.get("partei_staerke"),
                             r.get("anzahl_gewaehlte"), r.get("anzahl_gewaehlte_f"), r.get("anzahl_gewaehlte_m"),
                             r.get("frauen_anteil"), b(r.get("flag_staerkste_partei"))) for j, k, r in rows])
            n["zeitreihe_parteien"] = len(rows)
        if zrf:
            rows = [(r["wahl_jahr"], 0, r) for r in zrf.get("level_ch") or []] + \
                   [(r["wahl_jahr"], r["kanton_nummer"], r) for r in zrf.get("level_kantone") or []]
            db.execute("DELETE FROM nr_zeitreihe_beteiligung")
            db.executemany("INSERT INTO nr_zeitreihe_beteiligung VALUES (?,?,?,?,?,?,?,?,?)",
                           [(j, k, r.get("wahlbeteiligung"), r.get("frauen_anteil"), r.get("anzahl_listen"),
                             r.get("anzahl_kandidierende"), r.get("anzahl_kandidierende_f"), r.get("anzahl_gewaehlte"),
                             r.get("anzahl_gewaehlte_f")) for j, k, r in rows])
            n["zeitreihe_beteiligung"] = len(rows)
    print(f"Nationalrat {jahr} importiert:", n)


def cmd_import_sr(pfad, ordner, jahr_vorgabe=None):
    db = oeffnen(pfad)
    n = {}
    with db:
        for wg, muster in ((1, r"SRW\d{4}-kandidierende_erster-wahlgang"), (2, r"SRW\d{4}-kandidierende_zweiter-wahlgang")):
            d, f = load(ordner, muster)
            if not d:
                continue
            jahr = jahr_vorgabe or d.get("wahl_jahr")
            db.execute("DELETE FROM sr_stand_kanton WHERE wahl_jahr=? AND wahlgang=?", (jahr, wg))
            db.executemany("INSERT INTO sr_stand_kanton VALUES (?,?,?,?,?,?,?)",
                           [(jahr, wg, k["kanton_nummer"], k.get("wahlgang_datum"), b(k.get("stille_wahl")),
                             b(k.get("zweiter_wahlgang_noetig")), b(k.get("wahlgang_abgeschlossen")))
                            for k in d.get("stand_kantone") or []])
            db.execute("DELETE FROM sr_kandidat WHERE wahl_jahr=? AND wahlgang=?", (jahr, wg))
            lauf = {}
            zeilen = []
            for r in d.get("kandidierende") or []:
                kt = r["kanton_nummer"]
                lauf[kt] = lauf.get(kt, 0) + 1
                name = s(r.get("name"))
                zeilen.append((jahr, wg, kt, lauf[kt], name, s(r.get("vorname")) or None, r.get("geschlecht"),
                               datum(r.get("geburtsdatum")), r.get("geburtsjahr"), r.get("kandidat_status_id"),
                               r.get("kandidat_partei_id"), r.get("stimmen_kandidat"), b(r.get("flag_gewaehlt")),
                               1 if name and name.startswith("Vereinzelte") else 0))
            db.executemany("INSERT INTO sr_kandidat VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", zeilen)
            protokoll(db, jahr, f, d.get("timestamp"), len(zeilen))
            n[f"wahlgang_{wg}"] = len(zeilen)
    print("Ständerat importiert:", n)


def cmd_sitze(pfad, csv_pfad, jahr, spalte, geprueft):
    import csv
    db = oeffnen(pfad)
    with db, open(csv_pfad, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
        db.execute("DELETE FROM kanton_sitze WHERE wahl_jahr=?", (jahr,))
        for r in rows:
            kt = int(r["kanton_nummer"])
            db.execute("INSERT INTO kanton_sitze VALUES (?,?,?,?,?,?)",
                       (jahr, kt, int(r[spalte]), 1 if kt in SR_SITZE_HALB else 2, os.path.basename(csv_pfad), 1 if geprueft else 0))
    total = db.execute("SELECT SUM(nr_sitze), SUM(sr_sitze) FROM kanton_sitze WHERE wahl_jahr=?", (jahr,)).fetchone()
    print(f"Soll-Sitze {jahr}: Nationalrat {total[0]}, Ständerat {total[1]}")


def cmd_sitze_aus_resultat(pfad, jahr):
    db = oeffnen(pfad)
    with db:
        db.execute("DELETE FROM kanton_sitze WHERE wahl_jahr=?", (jahr,))
        db.execute("""INSERT INTO kanton_sitze
                      SELECT wahl_jahr, kanton_nummer, COUNT(*),
                             CASE WHEN kanton_nummer IN (6,7,12,13,15,16) THEN 1 ELSE 2 END,
                             'abgeleitet aus Gewählten (BFS)', 1
                      FROM nr_kandidat WHERE wahl_jahr=? AND gewaehlt=1 GROUP BY kanton_nummer""", (jahr,))
    total = db.execute("SELECT SUM(nr_sitze), COUNT(*) FROM kanton_sitze WHERE wahl_jahr=?", (jahr,)).fetchone()
    print(f"Soll-Sitze {jahr} aus Resultat: {total[0]} Sitze in {total[1]} Kantonen")


def cmd_korrektur_sr(pfad, a):
    db = oeffnen(pfad)
    with db:
        db.execute("INSERT OR REPLACE INTO sr_korrektur VALUES (?,?,?,?,?,?,?,?)",
                   (int(a["--jahr"]), int(a["--kanton"]), a["--name"], a["--vorname"],
                    int(a["--partei"]) if a.get("--partei") else None, int(a["--gewaehlt"]), a.get("--ab"), a.get("--grund")))
    print("Korrektur gespeichert")


def argwert(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    befehl, db_pfad = sys.argv[1], sys.argv[2]
    jahr = int(argwert("--jahr")) if argwert("--jahr") else None
    if befehl == "init":
        cmd_init(db_pfad)
    elif befehl == "views":
        cmd_views(db_pfad)
    elif befehl == "import-nr":
        cmd_import_nr(db_pfad, sys.argv[3], jahr)
    elif befehl == "import-sr":
        cmd_import_sr(db_pfad, sys.argv[3], jahr)
    elif befehl == "sitze":
        cmd_sitze(db_pfad, sys.argv[3], jahr, argwert("--spalte", f"nr_sitze_{jahr}"), "--geprueft" in sys.argv)
    elif befehl == "sitze-aus-resultat":
        cmd_sitze_aus_resultat(db_pfad, jahr)
    elif befehl == "korrektur-sr":
        keys = ["--jahr", "--kanton", "--name", "--vorname", "--gewaehlt", "--partei", "--ab", "--grund"]
        cmd_korrektur_sr(db_pfad, {k: argwert(k) for k in keys})
    else:
        sys.exit(__doc__)
