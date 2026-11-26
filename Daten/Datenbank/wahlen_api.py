#!/usr/bin/env python3
"""
Wahlen-API: liest die Ansichten der Wahlen-Datenbank und liefert JSON für die oGraf-Grafiken.
Nur lesend, nur Python-Standardbibliothek.

Start:
    python3 wahlen_api.py --db wahlen.sqlite [--port 8790] [--host 0.0.0.0] [--jahr 2027]

Alle Routen unter /api, Parameter als Query-String. Übersicht: GET /api
Gemeinsame Parameter:
    jahr=2027        Wahljahr (Standard: --jahr)
    lang=de|fr|it    Sprache der Parteinamen (Feld "partei")
    kanton=ZH|1      Kantonskürzel oder BFS-Nummer (wo sinnvoll)

Jede Antwort:
    {"jahr": 2027, "stand": {...}, "anzahl": n, "daten": [...]}
"stand" sagt, wie weit die Auszählung ist, damit eine Grafik «Zwischenstand» anzeigen kann.
"""
import argparse, re
import datetime as dt
import hashlib
import json
import os
import sqlite3
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ARGS = None
SPRACHEN = ("de", "fr", "it")


class Fehler(Exception):
    def __init__(self, code, meldung):
        super().__init__(meldung)
        self.code, self.meldung = code, meldung


# ---------------------------------------------------------------------------
# Datenbank
# ---------------------------------------------------------------------------
def verbinden():
    uri = "file:" + urllib.parse.quote(os.path.abspath(ARGS.db)) + "?mode=ro"
    db = sqlite3.connect(uri, uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    db.create_function("schluessel", 1, schluessel, deterministic=True)
    return db


def schluessel(k):
    """Parteikürzel vergleichbar machen: klein, ohne Leerzeichen und Punkte (wie historie_laden.py)."""
    return re.sub(r"[\s.]", "", (k or "").lower())


def abfrage(db, sql, args=()):
    return [dict(r) for r in db.execute(sql, args)]


def kanton_nummer(db, wert):
    if wert in (None, "", "CH", "ch"):
        return None
    if str(wert).isdigit():
        n = int(wert)
    else:
        r = db.execute("SELECT kanton_nummer FROM kanton WHERE upper(kuerzel) = upper(?)", (wert,)).fetchone()
        if not r:
            raise Fehler(400, f"Unbekannter Kanton: {wert}")
        n = r[0]
    if not 1 <= n <= 26:
        raise Fehler(400, f"Unbekannter Kanton: {wert}")
    return n


def stand(db, jahr):
    r = db.execute("SELECT * FROM nr_stand WHERE wahl_jahr = ?", (jahr,)).fetchone()
    if not r:
        return {"vorhanden": False}
    r = dict(r)
    return {"vorhanden": True, "abgeschlossen": bool(r["wahl_abgeschlossen"]),
            "kantone_abgeschlossen": r["kantone_abgeschlossen"], "kantone_total": r["kantone_total"],
            "gemeinden_abgeschlossen": r["gemeinden_abgeschlossen"], "gemeinden_total": r["gemeinden_total"],
            "bfs_zeitstempel": r["timestamp"], "importiert_um": r["importiert_um"]}


def partei_name(zeilen, lang, feld="partei"):
    """Setzt das Feld 'partei' auf den Namen in der gewünschten Sprache und entfernt die anderen."""
    for z in zeilen:
        if f"name_{lang}" in z:
            z[feld] = z.get(f"name_{lang}") or z.get("name_de")
        for s in SPRACHEN:
            z.pop(f"name_{s}", None)
        for s in ("kurz_de", "kurz_fr", "kurz_it"):
            z.pop(s, None)
    return zeilen


def bools(zeilen, *felder):
    for z in zeilen:
        for f in felder:
            if z.get(f) is not None:
                z[f] = bool(z[f])
    return zeilen


SORT_PARTEI = "ORDER BY reihenfolge IS NULL, reihenfolge, sitze DESC, partei_staerke DESC"


# ---------------------------------------------------------------------------
# Routen
# ---------------------------------------------------------------------------
def r_status(db, p, jahr):
    kt = bools(abfrage(db, """SELECT kuerzel AS kanton, sitze_total, sitze_vergeben, abgeschlossen,
                                      gemeinden_abgeschlossen, gemeinden_total
                               FROM v_kanton_fortschritt WHERE wahl_jahr = ? ORDER BY kanton_nummer""", (jahr,)), "abgeschlossen")
    letzter_sync = db.execute("SELECT MAX(zeit) FROM sync_log").fetchone()[0]
    return kt, {"letzter_grist_abgleich": letzter_sync}


def r_nr_parteien(db, p, jahr):
    kt = kanton_nummer(db, p.get("kanton"))
    if kt is None:
        z = abfrage(db, f"SELECT * FROM v_partei_ch WHERE wahl_jahr = ? {SORT_PARTEI}", (jahr,))
    else:
        z = abfrage(db, f"SELECT * FROM v_partei_kanton WHERE wahl_jahr = ? AND kanton_nummer = ? {SORT_PARTEI}", (jahr, kt))
        bools(z, "kanton_abgeschlossen")
    if p.get("min_sitze"):
        z = [r for r in z if (r.get("sitze") or 0) >= int(p["min_sitze"])]
    if p.get("min_staerke"):
        z = [r for r in z if (r.get("partei_staerke") or 0) >= float(p["min_staerke"])]
    for r in z:
        for f in ("partei_staerke", "staerke_vorwahl", "bfs_letzte_wahl_partei_staerke"):
            if r.get(f) is not None:
                r[f] = round(r[f], 2)
    return partei_name(z, p["lang"]), None


def r_nr_teilresultat(db, p, jahr):
    kt = kanton_nummer(db, p.get("kanton"))
    if kt is None:
        raise Fehler(400, "Parameter kanton fehlt")
    z = abfrage(db, """SELECT t.partei_id, COALESCE(pa.anzeige_de, pa.kurz_de) AS name_de,
                              COALESCE(pa.anzeige_fr, pa.kurz_fr) AS name_fr, COALESCE(pa.anzeige_it, pa.kurz_it) AS name_it,
                              pa.farbe, pa.reihenfolge, t.stimmen, t.staerke_teilresultat AS partei_staerke, t.gemeinden_gemeldet
                       FROM v_partei_kanton_teilresultat t JOIN partei pa USING (partei_id)
                       WHERE t.wahl_jahr = ? AND t.kanton_nummer = ?
                       ORDER BY pa.reihenfolge IS NULL, pa.reihenfolge, t.stimmen DESC""", (jahr, kt))
    st = db.execute("SELECT kanton_abgeschlossen, gemeinden_abgeschlossen, gemeinden_total FROM nr_stand_kanton "
                    "WHERE wahl_jahr = ? AND kanton_nummer = ?", (jahr, kt)).fetchone()
    extra = {"kanton_abgeschlossen": bool(st[0]) if st else False,
             "gemeinden_gemeldet": st[1] if st else 0, "gemeinden_total": st[2] if st else None,
             "hinweis": "Teilresultat aus den bereits gemeldeten Gemeinden, nicht hochgerechnet"}
    return partei_name(z, p["lang"]), extra


def r_nr_kantone(db, p, jahr):
    z = abfrage(db, """SELECT s.kanton_nummer, s.kuerzel, s.name_de AS kanton, s.sitze, s.sitze_vorwahl, s.sitze_veraenderung,
                              s.wahlverfahren, f.sitze_vergeben, f.abgeschlossen, f.gemeinden_abgeschlossen, f.gemeinden_total
                       FROM v_sitze_kanton s
                       LEFT JOIN v_kanton_fortschritt f ON f.wahl_jahr = s.wahl_jahr AND f.kanton_nummer = s.kanton_nummer
                       WHERE s.wahl_jahr = ? ORDER BY s.kanton_nummer""", (jahr,))
    return bools(z, "abgeschlossen"), None


def r_nr_gewaehlte(db, p, jahr):
    sql, args = "SELECT * FROM v_nr_gewaehlte WHERE wahl_jahr = ?", [jahr]
    kt = kanton_nummer(db, p.get("kanton"))
    if kt is not None:
        sql += " AND kanton_nummer = ?"; args.append(kt)
    if p.get("partei"):
        sql += " AND partei_id = ?"; args.append(int(p["partei"]))
    if p.get("status") in ("bisherig", "neu"):
        sql += " AND status = ?"; args.append(p["status"])
    if p.get("geschlecht") in ("F", "M"):
        sql += " AND geschlecht = ?"; args.append(p["geschlecht"])
    sql += " ORDER BY kanton_nummer, stimmen DESC"
    return abfrage(db, sql, args), None


def r_nr_abgewaehlte(db, p, jahr):
    sql, args = "SELECT * FROM v_nr_abgewaehlte WHERE wahl_jahr = ?", [jahr]
    if p.get("kanton"):
        sql += " AND kanton = (SELECT kuerzel FROM kanton WHERE kanton_nummer = ?)"; args.append(kanton_nummer(db, p["kanton"]))
    return abfrage(db, sql + " ORDER BY kanton, stimmen DESC", args), None


def r_sr_gewaehlte(db, p, jahr):
    sql, args = "SELECT * FROM v_sr_gewaehlte WHERE wahl_jahr = ?", [jahr]
    kt = kanton_nummer(db, p.get("kanton"))
    if kt is not None:
        sql += " AND kanton_nummer = ?"; args.append(kt)
    return abfrage(db, sql + " ORDER BY kanton_nummer, stimmen DESC", args), None


def r_sr_parteien(db, p, jahr):
    return abfrage(db, """SELECT v.*, pa.farbe, pa.reihenfolge FROM v_sr_partei v LEFT JOIN partei pa USING (partei_id)
                          WHERE v.wahl_jahr = ? ORDER BY pa.reihenfolge IS NULL, pa.reihenfolge, v.sitze DESC""", (jahr,)), None


def r_sr_stand(db, p, jahr):
    z = abfrage(db, """SELECT k.kuerzel AS kanton, s.wahlgang, s.wahlgang_datum, s.stille_wahl, s.zweiter_wahlgang_noetig,
                              s.wahlgang_abgeschlossen
                       FROM sr_stand_kanton s JOIN kanton k USING (kanton_nummer)
                       WHERE s.wahl_jahr = ? ORDER BY s.kanton_nummer, s.wahlgang""", (jahr,))
    return bools(z, "stille_wahl", "zweiter_wahlgang_noetig", "wahlgang_abgeschlossen"), None


def r_hochrechnung(db, p, jahr):
    sql, args = "SELECT * FROM v_hochrechnung_aktuell WHERE wahl_jahr = ?", [jahr]
    rat = (p.get("rat") or "NR").upper()
    sql += " AND rat = ?"; args.append(rat)
    if p.get("institut"):
        sql += " AND institut = ?"; args.append(p["institut"])
    sql += " ORDER BY institut, reihenfolge IS NULL, reihenfolge, sitze DESC, staerke DESC"
    return partei_name(abfrage(db, sql, args), p["lang"]), None


def r_bauchbinden(db, p, jahr):
    sql, args = "SELECT * FROM v_bauchbinde WHERE 1=1", []
    if p.get("kategorie"):
        sql += " AND kategorie = ?"; args.append(p["kategorie"])
    if p.get("lang") and p.get("nur_sprache"):
        sql += " AND sprache = ?"; args.append(p["lang"])
    if p.get("id"):
        sql += " AND id = ?"; args.append(int(p["id"]))
    return abfrage(db, sql + " ORDER BY id", args), None


def r_beteiligung(db, p, jahr):
    kt = kanton_nummer(db, p.get("kanton"))
    if kt is None:
        z = abfrage(db, """SELECT b.wahlbeteiligung, v.wahlbeteiligung AS beteiligung_vorwahl,
                                  ROUND(b.wahlbeteiligung - v.wahlbeteiligung, 2) AS veraenderung,
                                  b.wahlberechtigte, b.eingelegte_wahlzettel
                           FROM nr_beteiligung b JOIN wahl w ON w.wahl_jahr = b.wahl_jahr
                           LEFT JOIN nr_beteiligung v ON v.wahl_jahr = w.vorwahl_jahr AND v.ebene = 'CH'
                           WHERE b.wahl_jahr = ? AND b.ebene = 'CH' AND b.wahlbeteiligung IS NOT NULL""", (jahr,))
        if not z:  # CH-Wert kommt vom BFS erst am Schluss: bis dahin alle Kantone liefern
            z = abfrage(db, "SELECT * FROM v_beteiligung_kanton WHERE wahl_jahr = ? ORDER BY kanton_nummer", (jahr,))
    else:
        z = abfrage(db, "SELECT * FROM v_beteiligung_kanton WHERE wahl_jahr = ? AND kanton_nummer = ?", (jahr, kt))
    for r in z:
        for f in ("wahlbeteiligung", "beteiligung_vorwahl"):
            if r.get(f) is not None:
                r[f] = round(r[f], 2)
    return z, None


TEXTE = {
    "hochrechnung":  {"de": "Hochrechnung", "fr": "Projection", "it": "Proiezione"},
    "resultat":      {"de": "Resultat", "fr": "Résultat", "it": "Risultato"},
    "zwischenstand": {"de": "Zwischenstand", "fr": "Résultats partiels", "it": "Risultati parziali"},
    "rat":           {"de": "Nationalrat", "fr": "Conseil national", "it": "Consiglio nazionale"},
    "sitz":          {"de": ("Sitz", "Sitze"), "fr": ("siège", "sièges"), "it": ("seggio", "seggi")},
    "schweiz":       {"de": "Schweiz", "fr": "Suisse", "it": "Svizzera"},
    "parteistaerke": {"de": "Parteistärke", "fr": "force des partis", "it": "forza dei partiti"},
}
PARTEI_UEBRIGE = 35


def diff_unsicher(z, staerke, vorwahl):
    """Veränderung liegt innerhalb des Fehlerbereichs der Hochrechnung (Grist: «± Prozentpunkte»)."""
    fehler = z["staerke_fehler"] if "staerke_fehler" in z.keys() else None
    if fehler is None or staerke is None or vorwahl is None:
        return False
    return abs(round(staerke - vorwahl, 1)) <= fehler


def r_nr_kanton_insert(db, p, jahr):
    """Daten für das Insert «Hochrechnung Kanton»: Titel, Sitzzahl und Parteien eines Kantons.
    quelle=auto (Standard): Hochrechnung, falls freigegeben; sonst Resultat, falls Kanton abgeschlossen;
    sonst Zwischenstand aus den gemeldeten Gemeinden (ohne Sitze)."""
    kt = kanton_nummer(db, p.get("kanton"))
    if kt is None:
        raise Fehler(400, "Parameter kanton fehlt")
    lang = p["lang"]
    quelle = p.get("quelle", "auto")
    min_staerke = float(p.get("min_staerke", 2.0))
    max_parteien = int(p.get("max_parteien", 9))
    k = db.execute("SELECT kuerzel, name_de FROM kanton WHERE kanton_nummer = ?", (kt,)).fetchone()
    s = db.execute("SELECT nr_sitze FROM kanton_sitze WHERE wahl_jahr = ? AND kanton_nummer = ?", (jahr, kt)).fetchone()
    st = db.execute("SELECT kanton_abgeschlossen FROM nr_stand_kanton WHERE wahl_jahr = ? AND kanton_nummer = ?",
                    (jahr, kt)).fetchone()
    abgeschlossen = bool(st and st[0])
    name = "COALESCE(pa.anzeige_{0}, pa.kurz_{0})".format(lang)

    zeilen, modus = [], None
    if quelle in ("auto", "hochrechnung"):
        zeilen = abfrage(db, f"""SELECT h.partei_id, {name} AS partei, pa.farbe, h.sitze, h.sitze_vorwahl,
                                        h.staerke AS partei_staerke, h.staerke_vorwahl, h.staerke_fehler,
                                        h.institut, h.nummer, h.zeitpunkt
                                 FROM v_hochrechnung_kanton h JOIN partei pa USING (partei_id)
                                 WHERE h.wahl_jahr = ? AND h.kanton_nummer = ?""", (jahr, kt))
        modus = "hochrechnung" if zeilen else None
    if not modus and quelle in ("auto", "resultat") and (abgeschlossen or quelle == "resultat"):
        zeilen = abfrage(db, f"""SELECT v.partei_id, {name} AS partei, pa.farbe, v.sitze, v.sitze_vorwahl,
                                        v.partei_staerke, v.staerke_vorwahl
                                 FROM v_partei_kanton v JOIN partei pa USING (partei_id)
                                 WHERE v.wahl_jahr = ? AND v.kanton_nummer = ?""", (jahr, kt))
        modus = "resultat" if zeilen else None
    if not modus and quelle in ("auto", "zwischenstand"):
        zeilen = abfrage(db, f"""SELECT t.partei_id, {name} AS partei, pa.farbe, NULL AS sitze, NULL AS sitze_vorwahl,
                                        t.staerke_teilresultat AS partei_staerke,
                                        COALESCE(v.partei_staerke, a.bfs_letzte_wahl_partei_staerke) AS staerke_vorwahl
                                 FROM v_partei_kanton_teilresultat t JOIN partei pa USING (partei_id)
                                 JOIN wahl w ON w.wahl_jahr = t.wahl_jahr
                                 LEFT JOIN nr_partei_kanton v ON v.wahl_jahr = w.vorwahl_jahr
                                      AND v.kanton_nummer = t.kanton_nummer AND v.partei_id = t.partei_id
                                 LEFT JOIN nr_partei_kanton a ON a.wahl_jahr = t.wahl_jahr
                                      AND a.kanton_nummer = t.kanton_nummer AND a.partei_id = t.partei_id
                                 WHERE t.wahl_jahr = ? AND t.kanton_nummer = ?""", (jahr, kt))
        modus = "zwischenstand" if zeilen else None

    parteien = []
    for z in zeilen:
        sitze, sv, st_, sv_st = z["sitze"], z["sitze_vorwahl"], z["partei_staerke"], z["staerke_vorwahl"]
        relevant = (sitze or 0) > 0 or (sv or 0) > 0 or (st_ or 0) >= min_staerke
        if not relevant or (z["partei_id"] == PARTEI_UEBRIGE and not (sitze or 0)):
            continue
        parteien.append({
            "partei_id": z["partei_id"], "kurz": z["partei"], "farbe": z["farbe"] or "#8A8A8A",
            "sitze": sitze, "sitze_diff": (sitze - (sv or 0)) if sitze is not None else None,
            "staerke": round(st_, 1) if st_ is not None else None,
            "staerke_diff": round(st_ - sv_st, 1) if st_ is not None and sv_st is not None else None,
            "staerke_diff_unsicher": diff_unsicher(z, st_, sv_st)})
    parteien.sort(key=lambda r: (-(r["sitze"] or 0), -(r["staerke"] or 0)))
    parteien = parteien[:max_parteien]

    n = s[0] if s else None
    sitz_txt = TEXTE["sitz"][lang][0 if n == 1 else 1]
    extra = {"kanton": k[0] if k else None, "kanton_name": k[1] if k else None, "modus": modus,
             "kanton_abgeschlossen": abgeschlossen, "sitze_total": n,
             "titel": f"{TEXTE[modus or 'hochrechnung'][lang]} {k[0] if k else ''}".strip(),
             "untertitel": f"{TEXTE['rat'][lang]}, {n} {sitz_txt}" if n else TEXTE["rat"][lang],
             "mit_sitzen": modus in ("hochrechnung", "resultat") and any(r["sitze"] is not None for r in parteien)}
    if modus == "hochrechnung" and zeilen:
        extra.update({"institut": zeilen[0]["institut"], "hochrechnung_nr": zeilen[0]["nummer"],
                      "zeitpunkt": zeilen[0]["zeitpunkt"]})
    return parteien, extra


def r_nr_schweiz_insert(db, p, jahr):
    """Daten für das Insert «Hochrechnung Schweiz» (Nationalrat, Parteistärke).
    quelle=auto (Standard): neueste freigegebene Hochrechnung Schweiz (?institut=); sonst Resultat, sobald die
    Wahl abgeschlossen ist. Reihenfolge: Parteistärke absteigend (sort=vorwahl: nach Stärke der letzten Wahl),
    Übrige am Schluss. sitze=1: auch Sitze."""
    lang = p["lang"]
    quelle = p.get("quelle", "auto")
    min_staerke = float(p.get("min_staerke", 0.5))
    max_parteien = int(p.get("max_parteien", 15))
    mit_sitzen_wunsch = p.get("sitze") in ("1", "true", "ja")
    name = "COALESCE(pa.anzeige_{0}, pa.kurz_{0})".format(lang)
    st = db.execute("SELECT wahl_abgeschlossen FROM nr_stand WHERE wahl_jahr = ?", (jahr,)).fetchone()
    abgeschlossen = bool(st and st[0])

    zeilen, modus = [], None
    if quelle in ("auto", "hochrechnung"):
        institut = p.get("institut")
        if not institut:   # neueste Hochrechnung über alle Institute
            r = db.execute("""SELECT institut FROM v_hochrechnung_aktuell WHERE wahl_jahr = ? AND rat = 'NR'
                              ORDER BY zeitpunkt DESC, nummer DESC LIMIT 1""", (jahr,)).fetchone()
            institut = r[0] if r else None
        if institut is not None:
            zeilen = abfrage(db, f"""SELECT h.partei_id, {name} AS partei, pa.farbe, h.sitze, h.sitze_vorwahl,
                                            h.staerke AS partei_staerke, h.staerke_vorwahl, h.staerke_fehler,
                                            h.institut, h.nummer, h.zeitpunkt
                                     FROM v_hochrechnung_aktuell h JOIN partei pa USING (partei_id)
                                     WHERE h.wahl_jahr = ? AND h.rat = 'NR' AND h.institut IS ?""", (jahr, institut))
        modus = "hochrechnung" if zeilen else None
    if not modus and quelle in ("auto", "resultat") and (abgeschlossen or quelle == "resultat"):
        zeilen = abfrage(db, f"""SELECT v.partei_id, {name} AS partei, pa.farbe, v.sitze, v.sitze_vorwahl,
                                        v.partei_staerke, v.staerke_vorwahl
                                 FROM v_partei_ch v JOIN partei pa USING (partei_id)
                                 WHERE v.wahl_jahr = ? AND v.partei_staerke IS NOT NULL""", (jahr,))
        zeilen = [z for z in zeilen if (z["partei_staerke"] or 0) >= min_staerke or (z["sitze"] or 0) > 0
                  or z["partei_id"] == PARTEI_UEBRIGE]
        modus = "resultat" if zeilen else None

    parteien = []
    for z in zeilen:
        sitze, sv, st_, sv_st = z["sitze"], z["sitze_vorwahl"], z["partei_staerke"], z["staerke_vorwahl"]
        if st_ is None:
            continue
        parteien.append({
            "partei_id": z["partei_id"], "kurz": z["partei"], "farbe": z["farbe"] or "#8A8A8A",
            "sitze": sitze, "sitze_diff": (sitze - (sv or 0)) if sitze is not None else None,
            "staerke": round(st_, 1),
            "staerke_diff": round(st_ - sv_st, 1) if sv_st is not None else None,
            "staerke_diff_unsicher": diff_unsicher(z, st_, sv_st),
            "staerke_vorwahl": round(sv_st, 2) if sv_st is not None else None})
    if p.get("sort") == "vorwahl":   # feste Reihenfolge nach Stärke der letzten Wahl (Parteien springen nicht)
        parteien.sort(key=lambda r: (r["partei_id"] == PARTEI_UEBRIGE, -(r["staerke_vorwahl"] or 0), -(r["staerke"] or 0)))
    else:
        parteien.sort(key=lambda r: (r["partei_id"] == PARTEI_UEBRIGE, -(r["staerke"] or 0)))
    if len(parteien) > max_parteien:   # Übrige bleibt am Schluss
        ueb = [r for r in parteien if r["partei_id"] == PARTEI_UEBRIGE]
        parteien = [r for r in parteien if r["partei_id"] != PARTEI_UEBRIGE][:max_parteien - len(ueb)] + ueb

    mit_sitzen = mit_sitzen_wunsch and modus is not None and all(r["sitze"] is not None for r in parteien)
    extra = {"modus": modus, "wahl_abgeschlossen": abgeschlossen,
             "titel": f"{TEXTE[modus or 'hochrechnung'][lang]} {TEXTE['schweiz'][lang]}",
             "untertitel": f"{TEXTE['rat'][lang]}, {TEXTE['parteistaerke'][lang]}" if not mit_sitzen
                           else f"{TEXTE['rat'][lang]}, 200 {TEXTE['sitz'][lang][1]}",
             "mit_sitzen": mit_sitzen}
    if modus == "hochrechnung" and zeilen:
        extra.update({"institut": zeilen[0]["institut"], "hochrechnung_nr": zeilen[0]["nummer"],
                      "zeitpunkt": zeilen[0]["zeitpunkt"]})
    return parteien, extra


def r_auszaehlung_nr(db, p, jahr):
    """Auszählungsstand Nationalrat für die Karte: pro Kanton resultat (Kanton abgeschlossen) →
    hochrechnung (freigegebene Kantons-Hochrechnung) → keines. Dazu die Zähler für die Legende."""
    z = abfrage(db, """SELECT k.kanton_nummer, k.kuerzel AS kanton, COALESCE(f.abgeschlossen, 0) AS abgeschlossen,
                              EXISTS (SELECT 1 FROM v_hochrechnung_kanton h
                                      WHERE h.wahl_jahr = f.wahl_jahr AND h.kanton_nummer = k.kanton_nummer) AS hochrechnung
                       FROM kanton k JOIN v_kanton_fortschritt f ON f.kanton_nummer = k.kanton_nummer AND f.wahl_jahr = ?
                       ORDER BY k.kanton_nummer""", (jahr,))
    for r in z:
        r["status"] = "resultat" if r["abgeschlossen"] else "hochrechnung" if r["hochrechnung"] else "keines"
        del r["abgeschlossen"], r["hochrechnung"]
    zaehler = {s: sum(1 for r in z if r["status"] == s) for s in ("resultat", "hochrechnung", "keines")}
    return z, {"zaehler": zaehler, "kantone_total": len(z)}


def r_beteiligung_schweiz(db, p, jahr):
    """Ein Wert für die Grafik «Wahlbeteiligung»: Hochrechnung (Grist, freigegeben) → Schlussresultat BFS →
    Zwischenstand (Summe der gemeldeten Kantone). Mit Vergleich zur letzten Wahl."""
    quelle = p.get("quelle", "auto")
    wert = modus = None
    extra = {}
    if quelle in ("auto", "hochrechnung"):
        sql = """SELECT institut, nummer, zeitpunkt, beteiligung, fehler FROM hochrechnung_beteiligung
                 WHERE wahl_jahr = ? AND freigegeben = 1 AND beteiligung IS NOT NULL"""
        args = [jahr]
        if p.get("institut"):
            sql += " AND institut = ?"; args.append(p["institut"])
        r = db.execute(sql + " ORDER BY zeitpunkt DESC, nummer DESC LIMIT 1", args).fetchone()
        if r:
            wert, modus = r[3], "hochrechnung"
            extra = {"institut": r[0], "hochrechnung_nr": r[1], "zeitpunkt": r[2], "fehler": r[4]}
    if wert is None and quelle in ("auto", "resultat"):
        r = db.execute("""SELECT wahlbeteiligung FROM nr_beteiligung WHERE wahl_jahr = ? AND ebene = 'CH'
                          AND wahlbeteiligung IS NOT NULL""", (jahr,)).fetchone()
        if r:
            wert, modus = r[0], "resultat"
    if wert is None and quelle in ("auto", "zwischenstand"):
        r = db.execute("""SELECT SUM(eingelegte_wahlzettel), SUM(wahlberechtigte), COUNT(*) FROM nr_beteiligung
                          WHERE wahl_jahr = ? AND ebene = 'kanton' AND wahlberechtigte > 0
                          AND eingelegte_wahlzettel IS NOT NULL""", (jahr,)).fetchone()
        if r and r[1]:
            wert, modus = 100.0 * r[0] / r[1], "zwischenstand"
            extra = {"kantone": r[2]}
    vorwahl = db.execute("""SELECT COALESCE(v.wahlbeteiligung, a.bfs_letzte_wahl_wahlbeteiligung)
                            FROM wahl w
                            LEFT JOIN nr_beteiligung v ON v.wahl_jahr = w.vorwahl_jahr AND v.ebene = 'CH'
                            LEFT JOIN nr_beteiligung a ON a.wahl_jahr = w.wahl_jahr AND a.ebene = 'CH'
                            WHERE w.wahl_jahr = ?""", (jahr,)).fetchone()
    vorwahl = vorwahl[0] if vorwahl else None
    daten = [] if wert is None else [{
        "wert": round(wert, 1), "vorwahl": round(vorwahl, 1) if vorwahl is not None else None,
        "diff": round(wert - vorwahl, 1) if vorwahl is not None else None}]
    return daten, {"modus": modus, **extra}


# ---------------------------------------------------------------------------
# Historie / Recherche (freie Suche für die Moderation)
# ---------------------------------------------------------------------------
FAMILIE_SQL = "COALESCE((SELECT f.familie FROM partei_familie f WHERE f.schluessel = schluessel({0})), {0})"
KT_KUERZEL = ["CH", "ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG", "FR", "SO", "BS", "BL", "SH", "AR", "AI",
              "SG", "GR", "AG", "TG", "TI", "VD", "VS", "NE", "GE", "JU"]


def familie_sql(db, spalte):
    """Parteifamilie zu einem Kürzel; ohne geladene Tabelle partei_familie ist das Kürzel selbst die Familie."""
    return FAMILIE_SQL.format(spalte) if hat_tabelle(db, "partei_familie") else spalte


def hat_tabelle(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (name,)).fetchone() is not None


def jahr_param(p, name):
    v = (p.get(name) or "").strip()
    if not v:
        return None
    if not v.isdigit():
        raise ValueError(f"{name}={v}")
    return int(v)


def r_hist_mitglieder(db, p, jahr):
    """Ratsmitglieder seit 1848, eine Zeile pro Amtszeit. Filter frei kombinierbar."""
    if not hat_tabelle(db, "hist_mitglied"):
        return [], {"hinweis": "Historie noch nicht geladen (python3 historie_laden.py)", "total": 0}
    fam = familie_sql(db, "m.partei")
    wo, args = [], []
    if p.get("name"):
        for wort in p["name"].split():
            wo.append("(m.vorname || ' ' || m.nachname) LIKE ?"); args.append(f"%{wort}%")
    if p.get("partei"):
        wo.append(f"(schluessel({fam}) = schluessel(?) OR schluessel(m.partei) = schluessel(?))"); args += [p["partei"]] * 2
    if p.get("kanton") and p["kanton"].upper() != "CH":
        wo.append("m.kanton = ?"); args.append(p["kanton"].upper())
    if p.get("rat"):
        wo.append("m.rat = ?"); args.append(p["rat"].upper())
    if p.get("geschlecht") in ("f", "m"):
        wo.append("m.geschlecht = ?"); args.append(p["geschlecht"])
    von, bis = jahr_param(p, "von"), jahr_param(p, "bis")
    if von:
        wo.append("(m.austritt IS NULL OR m.austritt >= ?)"); args.append(f"{von}-01-01")
    if bis:
        wo.append("m.eintritt <= ?"); args.append(f"{bis}-12-31")
    if p.get("im_amt") in ("1", "true", "ja"):
        wo.append("m.austritt IS NULL")
    bedingung = (" WHERE " + " AND ".join(wo)) if wo else ""
    sortierung = {"eintritt": "m.eintritt", "austritt": "COALESCE(m.austritt, '9999')", "name": "m.nachname, m.vorname",
                  "dauer": "dauer", "geburt": "m.geburt", "alter": "alter_eintritt", "kanton": "m.kanton, m.eintritt",
                  "partei": "familie, m.partei, m.eintritt"}.get(p.get("sort", "eintritt"), "m.eintritt")
    richtung = "ASC" if p.get("richtung", "ab") == "auf" else "DESC"
    if " " in sortierung or "," in sortierung:
        sortierung = ", ".join(f"{t} {richtung}" for t in sortierung.split(", "))
    else:
        sortierung = f"{sortierung} {richtung}"
    limit = max(1, min(int(p.get("limit", 300)), 3000))
    total = db.execute(f"SELECT COUNT(*) FROM hist_mitglied m{bedingung}", args).fetchone()[0]
    zeilen = abfrage(db, f"""SELECT m.vorname, m.nachname, m.geschlecht, m.kanton, m.rat, m.partei, m.partei_name,
                                    {fam} AS familie, m.fraktion, m.eintritt, m.austritt, m.geburt, m.tod,
                                    ROUND((julianday(COALESCE(m.austritt, date('now'))) - julianday(m.eintritt)) / 365.25, 1) AS dauer,
                                    CAST((julianday(m.eintritt) - julianday(m.geburt)) / 365.25 AS INTEGER) AS alter_eintritt
                             FROM hist_mitglied m{bedingung}
                             ORDER BY {sortierung}, m.nachname LIMIT ?""", args + [limit])
    return zeilen, {"total": total, "limit": limit}


def r_hist_parteistaerke(db, p, jahr):
    """Parteistärke Nationalrat seit 1971 (BFS) plus laufende Wahl (Resultat oder Hochrechnung).
    gruppiert=familie (Standard: CVP+BDP → Mitte usw. zusammengezählt) oder partei."""
    teile, args = [], []
    nach_familie = p.get("gruppiert", "familie") != "partei"
    if hat_tabelle(db, "hist_partei_staerke"):
        fam = familie_sql(db, "h.partei") if nach_familie else "h.partei"
        teile.append(f"""SELECT h.wahl_jahr, h.kanton_nummer, {fam} AS partei, h.partei AS einzeln, h.staerke, 'bfs' AS quelle
                         FROM hist_partei_staerke h WHERE h.wahl_jahr <> ?""")
        args.append(jahr)
    name = "COALESCE(p.kurz_de, p.anzeige_de)"
    fam_akt = familie_sql(db, name) if nach_familie else name
    # Zeitreihe aus der BFS-Schnittstelle (ab 1991) für Jahre, die in der langen BFS-Reihe fehlen
    if hat_tabelle(db, "nr_zeitreihe_partei"):
        luecke = "NOT EXISTS (SELECT 1 FROM hist_partei_staerke x WHERE x.wahl_jahr = z.wahl_jahr)" \
            if hat_tabelle(db, "hist_partei_staerke") else "1"
        teile.append(f"""SELECT z.wahl_jahr AS wahl_jahr, z.kanton_nummer AS kanton_nummer, {fam_akt} AS partei, {name} AS einzeln,
                                z.partei_staerke AS staerke, 'bfs-zeitreihe' AS quelle
                         FROM nr_zeitreihe_partei z JOIN partei p USING (partei_id)
                         WHERE z.wahl_jahr <> ? AND z.partei_staerke IS NOT NULL AND {luecke}""")
        args.append(jahr)
    teile.append(f"""SELECT v.wahl_jahr AS wahl_jahr, 0 AS kanton_nummer, {fam_akt} AS partei, {name} AS einzeln,
                            v.partei_staerke AS staerke, 'resultat' AS quelle
                     FROM nr_partei_ch v JOIN partei p USING (partei_id) WHERE v.wahl_jahr = ? AND v.partei_staerke IS NOT NULL""")
    args.append(jahr)
    teile.append(f"""SELECT v.wahl_jahr, v.kanton_nummer, {fam_akt}, {name}, v.partei_staerke, 'resultat'
                     FROM nr_partei_kanton v JOIN partei p USING (partei_id) WHERE v.wahl_jahr = ? AND v.partei_staerke IS NOT NULL""")
    args.append(jahr)
    teile.append(f"""SELECT h.wahl_jahr, 0, {familie_sql(db, name) if nach_familie else name}, {name}, h.staerke,
                            'hochrechnung ' || COALESCE(h.institut, '')
                     FROM v_hochrechnung_aktuell h JOIN partei p USING (partei_id)
                     WHERE h.wahl_jahr = ? AND h.rat = 'NR'
                       AND NOT EXISTS (SELECT 1 FROM nr_partei_ch x WHERE x.wahl_jahr = h.wahl_jahr AND x.partei_staerke IS NOT NULL)""")
    args.append(jahr)
    basis = " UNION ALL ".join(teile)
    wo, w_args = [], []
    if p.get("partei"):
        wo.append("schluessel(partei) = schluessel(?)"); w_args.append(p["partei"])
    kt = (p.get("kanton") or "CH").upper()
    if kt != "ALLE":
        if kt not in KT_KUERZEL:
            raise Fehler(400, f"Unbekannter Kanton: {kt}")
        wo.append("kanton_nummer = ?"); w_args.append(KT_KUERZEL.index(kt))
    von, bis = jahr_param(p, "von"), jahr_param(p, "bis")
    if von:
        wo.append("wahl_jahr >= ?"); w_args.append(von)
    if bis:
        wo.append("wahl_jahr <= ?"); w_args.append(bis)
    bedingung = (" WHERE " + " AND ".join(wo)) if wo else ""
    zeilen = abfrage(db, f"""SELECT wahl_jahr, kanton_nummer, partei, ROUND(SUM(staerke), 2) AS staerke,
                                    GROUP_CONCAT(DISTINCT einzeln) AS enthaelt, MIN(quelle) AS quelle
                             FROM ({basis}) {bedingung}
                             GROUP BY wahl_jahr, kanton_nummer, partei""", args + w_args)
    # Rang innerhalb derselben Partei und desselben Gebiets: 1 = höchster bzw. tiefster Wert seit Beginn der Reihe
    gruppen = {}
    for z in zeilen:
        z["kanton"] = KT_KUERZEL[z.pop("kanton_nummer")] if 0 <= z.get("kanton_nummer", -1) < len(KT_KUERZEL) else None
        gruppen.setdefault((z["partei"], z["kanton"]), []).append(z)
    for g in gruppen.values():
        werte = sorted(x["staerke"] for x in g if x["staerke"] is not None)
        for z in g:
            if z["staerke"] is None:
                continue
            z["rang_hoch"] = sum(1 for w in werte if w > z["staerke"]) + 1
            z["rang_tief"] = sum(1 for w in werte if w < z["staerke"]) + 1
            z["wahlen_in_reihe"] = len(werte)
            if z["enthaelt"] and schluessel(z["enthaelt"]) == schluessel(z["partei"]):
                z["enthaelt"] = None
    schl = {"jahr": lambda z: (z["wahl_jahr"], z["kanton"] or "", z["partei"]),
            "staerke": lambda z: (z["staerke"] if z["staerke"] is not None else -1, z["wahl_jahr"]),
            "partei": lambda z: (z["partei"].lower(), z["kanton"] or "", z["wahl_jahr"]),
            "kanton": lambda z: (z["kanton"] or "", z["partei"].lower(), z["wahl_jahr"])}.get(p.get("sort", "jahr"))
    zeilen.sort(key=schl or (lambda z: z["wahl_jahr"]), reverse=p.get("richtung", "ab") != "auf")
    limit = max(1, min(int(p.get("limit", 500)), 5000))
    return zeilen[:limit], {"total": len(zeilen), "gruppiert": "familie" if nach_familie else "partei",
                            "hinweis": None if hat_tabelle(db, "hist_partei_staerke") else
                            "BFS-Reihe noch nicht geladen (python3 historie_laden.py), nur laufende Wahl"}


def r_hist_optionen(db, p, jahr):
    """Auswahllisten für die Recherche-Seite."""
    familien, quellen, jahre = set(), [], {}
    if hat_tabelle(db, "hist_mitglied"):
        familien |= {r[0] for r in db.execute(f"SELECT DISTINCT {familie_sql(db, 'partei')} FROM hist_mitglied") if r[0]}
        r = db.execute("SELECT MIN(substr(eintritt,1,4)), MAX(substr(eintritt,1,4)), COUNT(*) FROM hist_mitglied").fetchone()
        jahre["mitglieder"] = {"von": r[0], "bis": r[1], "anzahl": r[2]}
    if hat_tabelle(db, "hist_partei_staerke"):
        familien |= {r[0] for r in db.execute(f"SELECT DISTINCT {familie_sql(db, 'partei')} FROM hist_partei_staerke") if r[0]}
        r = db.execute("SELECT MIN(wahl_jahr), MAX(wahl_jahr), COUNT(*) FROM hist_partei_staerke").fetchone()
        jahre["parteistaerke"] = {"von": r[0], "bis": r[1], "anzahl": r[2]}
    familien |= {r[0] for r in db.execute(f"""SELECT DISTINCT {familie_sql(db, 'COALESCE(p.kurz_de, p.anzeige_de)')}
                                              FROM partei p JOIN nr_zeitreihe_partei z USING (partei_id)""") if r[0]}
    if hat_tabelle(db, "hist_quelle"):
        quellen = abfrage(db, "SELECT * FROM hist_quelle ORDER BY quelle")
    haeufig = ["SVP", "SP", "FDP", "Mitte", "Grüne", "GLP", "EVP", "EDU"]
    liste = [f for f in haeufig if f in familien] + sorted((familien - set(haeufig)), key=str.lower)
    return [], {"familien": liste, "kantone": KT_KUERZEL, "raete": ["NR", "SR"], "jahre": jahre, "quellen": quellen}


ROUTEN = {
    "/api/nr/schweiz-insert": (r_nr_schweiz_insert, "Insert «Hochrechnung Schweiz» und Videowand National: quelle=auto|hochrechnung|resultat, institut, sort=aktuell|vorwahl, sitze=1, min_staerke, max_parteien"),
    "/api/nr/kanton-insert":  (r_nr_kanton_insert, "Insert «Hochrechnung Kanton»: ?kanton= (Pflicht), quelle=auto|hochrechnung|resultat|zwischenstand, min_staerke, max_parteien"),
    "/api/status":            (r_status,          "Fortschritt der Auszählung pro Kanton"),
    "/api/nr/parteien":       (r_nr_parteien,     "Parteien Nationalrat (CH oder ?kanton=), min_sitze, min_staerke"),
    "/api/nr/teilresultat":   (r_nr_teilresultat, "Parteistärke aus gemeldeten Gemeinden, ?kanton= (Pflicht)"),
    "/api/nr/kantone":        (r_nr_kantone,      "Sitze pro Kanton mit Veränderung und Fortschritt"),
    "/api/nr/gewaehlte":      (r_nr_gewaehlte,    "Gewählte Nationalrat, ?kanton= ?partei= ?status=bisherig|neu ?geschlecht=F|M"),
    "/api/nr/abgewaehlte":    (r_nr_abgewaehlte,  "Nicht wiedergewählte Bisherige, ?kanton="),
    "/api/sr/gewaehlte":      (r_sr_gewaehlte,    "Gewählte Ständerat, ?kanton="),
    "/api/sr/parteien":       (r_sr_parteien,     "Ständeratssitze pro Partei mit Veränderung"),
    "/api/sr/stand":          (r_sr_stand,        "Ständerat: Wahlgänge und stille Wahlen pro Kanton"),
    "/api/hochrechnung":      (r_hochrechnung,    "Neueste freigegebene Hochrechnung, ?rat=NR|SR ?institut="),
    "/api/bauchbinden":       (r_bauchbinden,     "Freigegebene Bauchbinden, ?kategorie= ?id="),
    "/api/auszaehlung/nr":    (r_auszaehlung_nr,  "Auszählungsstand Nationalrat pro Kanton: status=resultat|hochrechnung|keines, plus Zähler"),
    "/api/beteiligung/schweiz": (r_beteiligung_schweiz, "Ein Wert Wahlbeteiligung Schweiz: Hochrechnung → Resultat → Zwischenstand, quelle=, institut="),
    "/api/historie/mitglieder":    (r_hist_mitglieder,    "Recherche: Ratsmitglieder seit 1848 (name, partei=Familie oder Kürzel, kanton, rat=NR|SR, geschlecht=f|m, von, bis, im_amt=1, sort=eintritt|austritt|name|dauer|alter|kanton|partei, richtung=auf|ab, limit)"),
    "/api/historie/parteistaerke": (r_hist_parteistaerke, "Recherche: Parteistärke NR seit 1971 plus laufende Wahl (partei, kanton=CH|Kürzel|alle, von, bis, gruppiert=familie|partei, sort=jahr|staerke|partei|kanton, richtung)"),
    "/api/historie/optionen":     (r_hist_optionen,      "Recherche: Auswahllisten und Stand der geladenen Daten"),
    "/api/beteiligung":       (r_beteiligung,     "Wahlbeteiligung CH oder ?kanton="),
}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "WahlenAPI/1.0"

    def log_message(self, fmt, *a):
        if ARGS.log:
            sys.stderr.write("%s %s\n" % (dt.datetime.now().strftime("%H:%M:%S"), fmt % a))

    def _senden(self, code, daten):
        body = json.dumps(daten, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        etag = '"' + hashlib.sha1(body).hexdigest()[:16] + '"'
        if code == 200 and self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self._kopf(etag)
            self.end_headers()
            return
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._kopf(etag)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _kopf(self, etag):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("ETag", etag)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "If-None-Match")
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        pfad = url.path.rstrip("/") or "/"
        p = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query).items()}
        if pfad in ("/", "/api"):
            return self._senden(200, {"routen": {r: b for r, (_, b) in ROUTEN.items()},
                                      "parameter": {"jahr": f"Wahljahr (Standard {ARGS.jahr})", "lang": "de|fr|it",
                                                    "kanton": "Kürzel oder BFS-Nummer"}})
        if pfad not in ROUTEN:
            return self._senden(404, {"fehler": f"Unbekannte Route: {pfad}", "routen": list(ROUTEN)})
        try:
            jahr = int(p.get("jahr", ARGS.jahr))
            p["lang"] = p.get("lang", "de") if p.get("lang", "de") in SPRACHEN else "de"
            db = verbinden()
            try:
                daten, extra = ROUTEN[pfad][0](db, p, jahr)
                antwort = {"jahr": jahr, "stand": stand(db, jahr), "anzahl": len(daten), "daten": daten}
                if extra:
                    antwort.update(extra)
            finally:
                db.close()
            self._senden(200, antwort)
        except Fehler as e:
            self._senden(e.code, {"fehler": e.meldung})
        except ValueError as e:
            self._senden(400, {"fehler": f"Ungültiger Parameter: {e}"})
        except sqlite3.Error as e:
            self._senden(503, {"fehler": f"Datenbank nicht verfügbar: {e}"})


def main():
    global ARGS
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--db", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "wahlen.sqlite"))
    a.add_argument("--host", default="127.0.0.1", help="0.0.0.0 = im ganzen Netz erreichbar")
    a.add_argument("--port", type=int, default=8790)
    a.add_argument("--jahr", type=int, default=2027)
    a.add_argument("--log", action="store_true", help="Anfragen protokollieren")
    ARGS = a.parse_args()
    if not os.path.exists(ARGS.db):
        sys.exit(f"Datenbank nicht gefunden: {ARGS.db}")
    print(f"Wahlen-API auf http://{ARGS.host}:{ARGS.port}/api  (Datenbank {ARGS.db}, Jahr {ARGS.jahr})")
    try:
        ThreadingHTTPServer((ARGS.host, ARGS.port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")


if __name__ == "__main__":
    main()
