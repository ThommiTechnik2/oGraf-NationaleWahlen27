"""Test der Wahlen-API. Aufruf: python3 test_api.py <db_2023> [<db_2027_simuliert>]"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

HIER = __file__.rsplit("/", 2)[0]
fehler = 0


def starte(db, port, jahr):
    p = subprocess.Popen([sys.executable, "-I", f"{HIER}/wahlen_api.py", "--db", db, "--port", str(port), "--jahr", str(jahr)],
                         stdout=subprocess.DEVNULL)
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api", timeout=1)
            return p
        except Exception:
            time.sleep(0.1)
    raise SystemExit("API startet nicht")


def get(port, pfad, code=200, headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{pfad}", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, dict(r.headers), json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        body = e.read()
        return e.code, dict(e.headers), json.loads(body) if body else None


def pruefe(name, ist, soll):
    global fehler
    ok = ist == soll
    fehler += not ok
    print(f"  {'OK  ' if ok else 'FEHLER'} {name}: {ist}" + ("" if ok else f"  (erwartet {soll})"))


# ---------- 2023 (abgeschlossen) ----------
p = starte(sys.argv[1], 8791, 2023)
try:
    print("== 2023, Endresultat")
    c, h, d = get(8791, "/api/nr/parteien")
    pruefe("Status", c, 200)
    pruefe("CORS-Kopf", h.get("Access-Control-Allow-Origin"), "*")
    pruefe("Stand abgeschlossen", d["stand"]["abgeschlossen"], True)
    pruefe("Top 3 Sitze", [(r["partei"], r["sitze"]) for r in d["daten"][:3]], [("SVP", 62), ("SP", 41), ("Mitte", 29)])
    pruefe("Summe Sitze", sum(r["sitze"] or 0 for r in d["daten"]), 200)
    c, _, d = get(8791, "/api/nr/parteien?lang=fr&min_sitze=10")
    pruefe("Französisch, ab 10 Sitzen", [r["partei"] for r in d["daten"]], ["UDC", "PS", "Centre", "PLR", "VERT-E-S", "PVL"])
    c, _, d = get(8791, "/api/nr/parteien?kanton=ZH")
    pruefe("Kanton ZH Sitze total", sum(r["sitze"] or 0 for r in d["daten"]), 36)
    c, _, d = get(8791, "/api/nr/parteien?kanton=1")
    pruefe("Kanton per Nummer = per Kürzel", sum(r["sitze"] or 0 for r in d["daten"]), 36)
    c, _, d = get(8791, "/api/nr/kantone")
    pruefe("26 Kantone, Total 200", (d["anzahl"], sum(r["sitze"] for r in d["daten"])), (26, 200))
    c, _, d = get(8791, "/api/nr/gewaehlte?kanton=GL")
    pruefe("Gewählte GL", [(r["name"], r["partei"]) for r in d["daten"]], [("Schnyder", "SVP")])
    c, _, d = get(8791, "/api/nr/gewaehlte?status=neu")
    pruefe("Neu Gewählte 2023", d["anzahl"], 48)
    c, _, d = get(8791, "/api/sr/parteien")
    pruefe("SR Mitte", [(r["partei"], r["sitze"]) for r in d["daten"]][:2], [("Mitte", 15), ("FDP", 11)])
    c, _, d = get(8791, "/api/sr/stand")
    pruefe("SR stille Wahlen", sorted(r["kanton"] for r in d["daten"] if r["stille_wahl"]), ["BE", "OW"])
    c, _, d = get(8791, "/api/beteiligung")
    pruefe("Beteiligung CH", d["daten"][0]["wahlbeteiligung"], 46.66)
    c, _, d = get(8791, "/api/nr/parteien?kanton=XY")
    pruefe("Unbekannter Kanton -> 400", (c, d["fehler"]), (400, "Unbekannter Kanton: XY"))
    c, _, d = get(8791, "/api/gibtsnicht")
    pruefe("Unbekannte Route -> 404", c, 404)
    c, _, d = get(8791, "/api/nr/parteien?jahr=abc")
    pruefe("Ungültiges Jahr -> 400", c, 400)
    c, _, d = get(8791, "/api/nr/gewaehlte?kanton=ZH%27%3B%20DROP%20TABLE%20partei%3B--")
    pruefe("SQL-Einschleusung abgewiesen", c, 400)
    c, h, _ = get(8791, "/api/nr/parteien")
    c2, _, _ = get(8791, "/api/nr/parteien", headers={"If-None-Match": h["ETag"]})
    pruefe("ETag: unveränderte Daten -> 304", c2, 304)
finally:
    p.terminate()

# ---------- 2027 simuliert (BFS-Teststand 2 als 2027) ----------
if len(sys.argv) > 2:
    p = starte(sys.argv[2], 8792, 2027)
    try:
        print("== 2027 simuliert, Zwischenstand")
        c, _, d = get(8792, "/api/status")
        pruefe("Stand nicht abgeschlossen", (d["stand"]["abgeschlossen"], d["stand"]["kantone_abgeschlossen"]), (False, 1))
        lu = [r for r in d["daten"] if r["kanton"] == "LU"][0]
        pruefe("LU abgeschlossen, x von y", (lu["abgeschlossen"], lu["sitze_vergeben"], lu["sitze_total"]), (True, 9, 10))
        c, _, d = get(8792, "/api/nr/teilresultat?kanton=BL")
        pruefe("BL Teilresultat", (d["kanton_abgeschlossen"], d["gemeinden_gemeldet"], d["gemeinden_total"]), (False, 28, 86))
        pruefe("BL Teilresultat summiert 100 %", round(sum(r["partei_staerke"] for r in d["daten"])), 100)
        c, _, d = get(8792, "/api/nr/parteien?kanton=LU")
        svp = [r for r in d["daten"] if r["partei_id"] == 4][0]
        pruefe("LU SVP Veränderung zu 2023", (svp["sitze"], svp["sitze_vorwahl"], svp["staerke_veraenderung"]), (2, 2, -1.03))
        c, _, d = get(8792, "/api/nr/kantone")
        be = [r for r in d["daten"] if r["kuerzel"] == "BE"][0]
        pruefe("BE Sitzveränderung 2027", (be["sitze"], be["sitze_vorwahl"], be["sitze_veraenderung"]), (23, 24, -1))
        c, _, d = get(8792, "/api/nr/abgewaehlte")
        pruefe("Abgewählte (nur abgeschlossene Kantone)", sorted(r["name"] for r in d["daten"]), ["Müri", "Schilliger"])
        c, _, d = get(8792, "/api/beteiligung")
        pruefe("Beteiligung: ohne CH-Wert die Kantone", d["anzahl"], 26)
    finally:
        p.terminate()

print("ALLE TESTS BESTANDEN" if not fehler else f"{fehler} FEHLER")
sys.exit(1 if fehler else 0)
