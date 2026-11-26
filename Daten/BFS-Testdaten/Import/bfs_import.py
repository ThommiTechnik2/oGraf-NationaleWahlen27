#!/usr/bin/env python3
"""
BFS-Wahldaten (Nationalrat, Format opendata.swiss 2023) -> SQLite + CSV.

Aufruf:
    python3 bfs_import.py <ordner_mit_json> <ausgabeordner> [--stand NAME]

Liest die Dateien sd-t-17.02-NRW<jahr>-*.json aus <ordner_mit_json>, schreibt
<ausgabeordner>/wahlen.sqlite und CSV-Dateien für den Grist-Import.

Robust gegen:
- UTF-8-BOM am Dateianfang
- fehlende Dateien oder fehlende Blöcke (z. B. leere Strukturen vor 12:00)
- Boolean-Werte als true/false, 1/0 oder Text "true"/"false"
Die grosse Tabelle «Kandidierende pro Gemeinde» wird nur in SQLite geschrieben,
nicht als CSV (zu gross für Grist).
"""
import csv
import glob
import json
import os
import re
import sqlite3
import sys

LANGS = ("de", "fr", "it", "en")


# ---------- Hilfsfunktionen ----------

def load(folder, name):
    # Exakter Name: «NRW<4 Ziffern>-<name>.json», damit z. B. «parteien» nicht «zeitreihen-parteien» trifft
    files = [f for f in glob.glob(os.path.join(folder, "sd-t-17.02-NRW*.json"))
             if re.fullmatch(rf"sd-t-17\.02-NRW\d{{4}}-{re.escape(name)}\.json", os.path.basename(f))]
    if not files:
        return None
    path = files[0]
    if os.path.getsize(path) == 0:          # listen-gde ist vor 12:00 leer (0 KB)
        return None
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def to_bool(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(bool(v))
    s = str(v).strip().lower()
    if s in ("true", "1", "ja", "yes"):
        return 1
    if s in ("false", "0", "nein", "no"):
        return 0
    return None


def langs(lst):
    """[{langKey, text}] -> {de:..., fr:..., ...}"""
    out = {k: None for k in LANGS}
    for e in lst or []:
        if e.get("langKey") in out:
            out[e["langKey"]] = e.get("text")
    return out


def clean(s):
    return s.strip() if isinstance(s, str) else s


class Out:
    def __init__(self, outdir):
        os.makedirs(outdir, exist_ok=True)
        self.outdir = outdir
        self.db = sqlite3.connect(os.path.join(outdir, "wahlen.sqlite"))
        self.counts = {}

    def table(self, name, cols, rows, csv_too=True, pk=None):
        rows = list(rows)
        c = self.db.cursor()
        c.execute(f'DROP TABLE IF EXISTS "{name}"')
        coldef = ", ".join(f'"{col}"' for col in cols)
        if pk:
            coldef += ", PRIMARY KEY (" + ", ".join(f'"{p}"' for p in pk) + ")"
        c.execute(f'CREATE TABLE "{name}" ({coldef})')
        c.executemany(
            f'INSERT INTO "{name}" VALUES ({",".join("?" * len(cols))})',
            [[r.get(col) for col in cols] for r in rows],
        )
        self.db.commit()
        if csv_too:
            with open(os.path.join(self.outdir, f"{name}.csv"), "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(cols)
                for r in rows:
                    w.writerow(["" if r.get(col) is None else r.get(col) for col in cols])
        self.counts[name] = len(rows)


# ---------- Tabellen ----------

def build(folder, outdir, stand_name):
    o = Out(outdir)
    meta = load(folder, "metadaten")
    part = load(folder, "parteien")
    bet = load(folder, "wahlbeteiligung")
    kand = load(folder, "kandidierende")
    listen = load(folder, "listen")
    zr_p = load(folder, "zeitreihen-parteien")
    zr_f = load(folder, "zeitreihen-frauen-beteiligung")

    # --- Stammdaten aus metadaten ---
    if meta:
        rows = []
        for p in meta.get("parteien", []):
            n, k = langs(p.get("partei_bezeichnung")), langs(p.get("partei_bezeichnung_kurz"))
            g, gk = langs(p.get("parteigruppen_bezeichnung")), langs(p.get("parteigruppen_bezeichnung_kurz"))
            l, lk = langs(p.get("parteipolitische_lager_bezeichnung")), langs(p.get("parteipolitische_lager_bezeichnung_kurz"))
            r = {"partei_id": p.get("partei_id"),
                 "parteigruppen_id": p.get("parteigruppen_id"),
                 "lager_id": p.get("parteipolitische_lager_id"),
                 # Redaktionelle Felder, in Grist zu pflegen:
                 "farbe": None, "reihenfolge": None}
            for L in LANGS:
                r[f"kurz_{L}"], r[f"name_{L}"] = k[L], n[L]
                r[f"gruppe_kurz_{L}"], r[f"gruppe_{L}"] = gk[L], g[L]
                r[f"lager_kurz_{L}"], r[f"lager_{L}"] = lk[L], l[L]
            rows.append(r)
        cols = ["partei_id"] + [f"kurz_{L}" for L in LANGS] + [f"name_{L}" for L in LANGS] + \
               ["parteigruppen_id"] + [f"gruppe_kurz_{L}" for L in LANGS] + [f"gruppe_{L}" for L in LANGS] + \
               ["lager_id"] + [f"lager_kurz_{L}" for L in LANGS] + [f"lager_{L}" for L in LANGS] + \
               ["farbe", "reihenfolge"]
        o.table("Parteien", cols, rows, pk=["partei_id"])

        o.table("Kantone", ["kanton_nummer", "kuerzel", "name", "gemeinden_total"],
                ({"kanton_nummer": k["kanton_nummer"], "kuerzel": k.get("kanton_bezeichnung_kurz"),
                  "name": k.get("kanton_bezeichnung"), "gemeinden_total": k.get("gemeinden_total")}
                 # Block heisst je nach Teststand «stand_kantone» oder «kantone»
                 for k in (meta.get("stand_kantone") or meta.get("kantone") or [])), pk=["kanton_nummer"])

        o.table("Kandidat_Status", ["kandidat_status_id"] + [f"text_{L}" for L in LANGS],
                ({"kandidat_status_id": s["kandidat_status_id"],
                  **{f"text_{L}": v for L, v in langs(s.get("kandidat_status")).items()}}
                 for s in meta.get("kandidat_status", [])), pk=["kandidat_status_id"])

        # Listenverbindungen flach: eine Zeile pro Liste
        lv = []
        for block in meta.get("listenverbindungen", []):
            for kt in block.get("kantone", []):
                for v in kt.get("listenverbindung", []):
                    for li in v.get("listen", []):
                        lv.append({"kanton_nummer": kt["kanton_nummer"], "liste_verbindung": v.get("liste_verbindung"),
                                   "liste_unterlistenverbindung": None,
                                   "liste_nummer_kanton": li.get("liste_nummer_kanton"),
                                   "liste_bezeichnung": li.get("liste_bezeichnung"), "partei_id": li.get("partei_id")})
                    for u in v.get("unterlistenverbindung", []):
                        for li in u.get("listen", []):
                            lv.append({"kanton_nummer": kt["kanton_nummer"], "liste_verbindung": v.get("liste_verbindung"),
                                       "liste_unterlistenverbindung": u.get("liste_unterlistenverbindung"),
                                       "liste_nummer_kanton": li.get("liste_nummer_kanton"),
                                       "liste_bezeichnung": li.get("liste_bezeichnung"), "partei_id": li.get("partei_id")})
        o.table("Listenverbindungen", ["kanton_nummer", "liste_verbindung", "liste_unterlistenverbindung",
                                       "liste_nummer_kanton", "liste_bezeichnung", "partei_id"], lv)

    # --- Stand (aus parteien, sonst wahlbeteiligung) ---
    src = part or bet or kand
    if src:
        s = src.get("stand", {})
        o.table("Stand", ["stand_name", "timestamp", "wahl_jahr", "wahl_abgeschlossen", "kantone_total",
                          "kantone_abgeschlossen", "gemeinden_total", "gemeinden_abgeschlossen"],
                [{"stand_name": stand_name, "timestamp": src.get("timestamp"),
                  "wahl_jahr": src.get("wahl_jahr", src.get("wahljahr")),
                  "wahl_abgeschlossen": to_bool(s.get("wahl_abgeschlossen")),
                  **{k: s.get(k) for k in ("kantone_total", "kantone_abgeschlossen", "gemeinden_total", "gemeinden_abgeschlossen")}}])
        sk = src.get("stand_kantone", src.get("Stand_kantone", []))
        o.table("Stand_Kantone", ["kanton_nummer", "kanton_abgeschlossen", "gemeinden_total", "gemeinden_abgeschlossen"],
                ({"kanton_nummer": k["kanton_nummer"], "kanton_abgeschlossen": to_bool(k.get("kanton_abgeschlossen")),
                  "gemeinden_total": k.get("gemeinden_total"), "gemeinden_abgeschlossen": k.get("gemeinden_abgeschlossen")}
                 for k in sk), pk=["kanton_nummer"])

    # --- Parteiresultate ---
    PCH = ["partei_id", "anzahl_listen", "anzahl_kandidierende", "anzahl_kandidierende_f", "anzahl_kandidierende_m",
           "anzahl_gewaehlte", "anzahl_gewaehlte_f", "anzahl_gewaehlte_m",
           "letzte_wahl_anzahl_gewaehlte", "letzte_wahl_anzahl_gewaehlte_f", "letzte_wahl_anzahl_gewaehlte_m",
           "differenz_anzahl_gewaehlte", "differenz_anzahl_gewaehlte_f", "differenz_anzahl_gewaehlte_m",
           "fiktive_waehlende", "letzte_wahl_fiktive_waehlende", "differenz_fiktive_waehlende",
           "partei_staerke", "letzte_wahl_partei_staerke", "differenz_partei_staerke",
           "partei_rang", "flag_staerkste_partei"]
    PKT = ["kanton_nummer"] + PCH[:17] + ["stimmen_partei", "letzte_wahl_stimmen_partei", "differenz_stimmen_partei"] + PCH[17:]
    PGD = ["gemeinde_nummer", "gemeinde_bezeichnung", "kanton_nummer", "partei_id",
           "stimmen_partei", "letzte_wahl_stimmen_partei", "differenz_stimmen_partei",
           "partei_staerke", "letzte_wahl_partei_staerke", "differenz_partei_staerke",
           "partei_rang", "flag_staerkste_partei"]
    if part:
        def norm(r, cols):
            d = {c: clean(r.get(c)) for c in cols}
            if "flag_staerkste_partei" in d:
                d["flag_staerkste_partei"] = to_bool(d["flag_staerkste_partei"])
            return d
        o.table("Ergebnis_Partei_CH", PCH, (norm(r, PCH) for r in part.get("level_ch") or []), pk=["partei_id"])
        o.table("Ergebnis_Partei_Kanton", PKT, (norm(r, PKT) for r in part.get("level_kantone") or []),
                pk=["kanton_nummer", "partei_id"])
        o.table("Ergebnis_Partei_Gemeinde", PGD, (norm(r, PGD) for r in part.get("level_gemeinden") or []),
                pk=["gemeinde_nummer", "partei_id"])

    # --- Wahlbeteiligung und Gemeinden ---
    BET = ["wahlberechtigte", "eingelegte_wahlzettel", "leere_wahlzettel", "ungueltige_wahlzettel",
           "gueltige_wahlzettel", "wahlbeteiligung", "letzte_wahl_wahlbeteiligung", "differenz_wahlbeteiligung"]
    if bet:
        ch = bet.get("level_ch")
        o.table("Wahlbeteiligung_CH", BET, [ch] if isinstance(ch, dict) and ch else [])
        o.table("Wahlbeteiligung_Kanton", ["kanton_nummer"] + BET, bet.get("level_kantone") or [], pk=["kanton_nummer"])
        gd = bet.get("level_gemeinden") or []
        o.table("Wahlbeteiligung_Gemeinde", ["gemeinde_nummer", "kanton_nummer"] + BET, gd, pk=["gemeinde_nummer"])
        o.table("Gemeinden", ["gemeinde_nummer", "name", "kanton_nummer", "sondergemeinde"],
                ({"gemeinde_nummer": g["gemeinde_nummer"], "name": clean(g.get("gemeinde_bezeichnung")),
                  "kanton_nummer": g.get("kanton_nummer"),
                  # Auslandschweizer-Pseudogemeinde: 19 + Kantonsnummer (2-stellig) + 0
                  "sondergemeinde": 1 if re.fullmatch(r"19\d\d0", str(g["gemeinde_nummer"])) else 0}
                 for g in gd), pk=["gemeinde_nummer"])

    # --- Listen ---
    if listen:
        LC = ["kanton_nummer", "liste_nummer_bfs", "liste_nummer_kanton", "liste_bezeichnung", "liste_verbindung",
              "liste_unterlistenverbindung", "partei_id", "anzahl_gewaehlte", "stimmen_liste", "listen_staerke"]
        o.table("Listen", LC, ({c: clean(r.get(c)) for c in LC} for r in listen.get("level_kantone") or []),
                pk=["kanton_nummer", "liste_nummer_bfs"])

    # --- Kandidierende ---
    if kand:
        KC = ["kanton_nummer", "liste_nummer_bfs", "liste_nummer_kanton", "kandidat_nummer",
              "kandidat_listenplatz_1", "kandidat_listenplatz_2", "name", "vorname", "geschlecht",
              "geburtsdatum", "geburtsjahr", "wohnort_gemeinde_nummer", "wohnort", "beruf",
              "kandidat_status_id", "kandidat_partei_id", "stimmen_kandidat", "flag_gewaehlt"]
        def nk(r):
            d = {c: clean(r.get(c)) for c in KC}
            d["flag_gewaehlt"] = to_bool(d["flag_gewaehlt"])
            g = d.get("geburtsdatum")          # 25.04.1980 -> 1980-04-25
            if isinstance(g, str) and re.fullmatch(r"\d\d\.\d\d\.\d{4}", g):
                d["geburtsdatum"] = f"{g[6:]}-{g[3:5]}-{g[:2]}"
            return d
        o.table("Kandidierende", KC, (nk(r) for r in kand.get("level_kantone") or []),
                pk=["kanton_nummer", "liste_nummer_bfs", "kandidat_nummer"])
        GC = ["kanton_nummer", "gemeinde_nummer", "liste_nummer_bfs", "kandidat_nummer",
              "kandidat_partei_id", "stimmen_kandidat", "flag_gewaehlt"]
        o.table("Kandidierende_Gemeinde", GC,
                ({**{c: r.get(c) for c in GC}, "flag_gewaehlt": to_bool(r.get("flag_gewaehlt"))}
                 for r in kand.get("level_gemeinden") or []),
                csv_too=False, pk=["gemeinde_nummer", "liste_nummer_bfs", "kandidat_nummer"])

    # --- Zeitreihen ---
    if zr_p:
        ZC = ["wahl_jahr", "partei_id", "anzahl_listen", "anzahl_kandidierende", "anzahl_kandidierende_f",
              "anzahl_kandidierende_m", "partei_staerke", "anzahl_gewaehlte", "anzahl_gewaehlte_f",
              "anzahl_gewaehlte_m", "frauen_anteil", "flag_staerkste_partei"]
        o.table("Zeitreihe_Partei_CH", ZC, zr_p.get("level_ch") or [], pk=["wahl_jahr", "partei_id"])
        o.table("Zeitreihe_Partei_Kanton", ["kanton_nummer"] + ZC, zr_p.get("level_kantone") or [],
                pk=["kanton_nummer", "wahl_jahr", "partei_id"])
    if zr_f:
        FC = ["wahl_jahr", "wahlbeteiligung", "frauen_anteil", "anzahl_listen", "anzahl_kandidierende",
              "anzahl_kandidierende_f", "anzahl_kandidierende_m", "anzahl_gewaehlte", "anzahl_gewaehlte_f",
              "anzahl_gewaehlte_m"]
        o.table("Zeitreihe_Beteiligung_Frauen_CH", FC, zr_f.get("level_ch") or [], pk=["wahl_jahr"])
        o.table("Zeitreihe_Beteiligung_Frauen_Kanton", ["kanton_nummer"] + FC, zr_f.get("level_kantone") or [],
                pk=["kanton_nummer", "wahl_jahr"])

    o.db.execute("VACUUM")
    o.db.close()
    return o.counts


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    name = sys.argv[sys.argv.index("--stand") + 1] if "--stand" in sys.argv else os.path.basename(sys.argv[1].rstrip("/"))
    counts = build(sys.argv[1], sys.argv[2], name)
    for k, v in counts.items():
        print(f"{k:40s} {v:>9}")
