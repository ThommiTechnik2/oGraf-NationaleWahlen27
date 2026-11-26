#!/usr/bin/env python3
"""End-to-End-Test Videowand «Auszählungsstand Nationalrat».
    python3 test_auszaehlung.py <db.sqlite> <jahr> <ausgabeordner> [wahlen_db-ordner]
Die DB wird verändert (Kanton-Status wird während des Tests umgestellt): Kopie verwenden.
"""
import json, os, sqlite3, subprocess, sys, time, urllib.request, urllib.error
from playwright.sync_api import sync_playwright

HIER = os.path.dirname(os.path.abspath(__file__))
DB, JAHR, AUS = sys.argv[1], sys.argv[2], sys.argv[3]
API = os.path.join(sys.argv[4] if len(sys.argv) > 4 else "/home/claude/wahlen_db", "wahlen_api.py")
os.makedirs(AUS, exist_ok=True)
fehler = []

def pruefe(name, ist, soll):
    ok = ist == soll
    print(f"  {'OK  ' if ok else 'FEHL'} {name}: {ist}" + ("" if ok else f"  (erwartet {soll})"))
    if not ok: fehler.append(name)

def sd(befehl, erwarte=200):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:8795/sd/{befehl}", timeout=30) as r:
            code, d = r.status, (json.loads(r.read()) if "json" in r.headers.get("Content-Type", "") else r.read().decode())
    except urllib.error.HTTPError as e:
        code, d = e.code, json.loads(e.read())
    if code != erwarte:
        fehler.append(f"{befehl}: {code}"); print(f"  FEHL {befehl}: HTTP {code} {d}")
    return d

def warten(url):
    for _ in range(50):
        try: urllib.request.urlopen(url, timeout=1); return
        except Exception: time.sleep(0.2)
    raise SystemExit(f"{url} startet nicht")

api = subprocess.Popen([sys.executable, API, "--db", DB, "--jahr", JAHR], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
srv = subprocess.Popen([sys.executable, os.path.join(HIER, "..", "grafik_server.py"), "--jahr", JAHR, "--intervall", "2"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    warten("http://127.0.0.1:8790/api"); warten("http://127.0.0.1:8795/ograf/v1/")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--force-color-profile=srgb"])
        wand = browser.new_page(viewport={"width": 1920, "height": 1080})
        konsole = []
        wand.on("pageerror", lambda e: konsole.append(f"pageerror: {e}"))
        wand.on("console", lambda m: konsole.append(f"{m.type}: {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
        wand.goto("http://127.0.0.1:8795/renderer/wand"); time.sleep(0.8)
        bild = lambda n: wand.screenshot(path=os.path.join(AUS, f"{n}.png"))
        lesen = lambda: wand.evaluate("""() => { const el=[...document.querySelectorAll('*')].find(e=>e.shadowRoot&&e.shadowRoot.querySelector('svg.karte'));
            if(!el) return null; const s=el.shadowRoot;
            return {opacity:s.querySelector('.stage').style.opacity, kantone:s.querySelectorAll('path.kt').length,
                    zahlen:[...s.querySelectorAll('.kasten')].map(k=>k.textContent),
                    zg:getComputedStyle(s.querySelector('path[data-kt=ZG]')).fill, gr:getComputedStyle(s.querySelector('path[data-kt=GR]')).fill} }""")

        z = sd("az/status"); print("== Daten", z["meta"])
        pruefe("Zähler aus API", z["meta"]["zaehler"], {"resultat": 1, "hochrechnung": 2, "keines": 23})
        sd("az/ein"); time.sleep(0.3); bild("1_anfang"); time.sleep(1.0); bild("2_fertig")
        s = lesen(); print("  ", s)
        pruefe("sichtbar", s["opacity"], "1")
        pruefe("26 Kantone", s["kantone"], 26)
        pruefe("Legende", s["zahlen"], ["1", "2", "23"])
        pruefe("ZG dunkelrot", s["zg"], "rgb(155, 10, 60)")
        pruefe("GR rosa", s["gr"], "rgb(236, 87, 116)")
        pruefe("Stream Deck Anzeige", sd("wert/az_anzeige"), "ON AIR\n1 / 2 / 23")
        # Live-Änderung: GR und BE abgeschlossen -> Auto-Update färbt um
        db = sqlite3.connect(DB)
        db.execute("UPDATE nr_stand_kanton SET kanton_abgeschlossen=1 WHERE wahl_jahr=? AND kanton_nummer IN (2,18)", (JAHR,)); db.commit(); db.close()
        time.sleep(3.5); bild("3_update")
        s = lesen(); print("  ", s)
        pruefe("Legende nach Update", s["zahlen"], ["3", "1", "22"])
        pruefe("GR jetzt dunkelrot", s["gr"], "rgb(155, 10, 60)")
        # Layer teilen mit Wahlbeteiligung
        sd("wb/ein"); time.sleep(1.0)
        pruefe("Auszählung aus nach Beteiligung", sd("wert/az_onair"), "0")
        sd("az/ein"); time.sleep(1.0)
        pruefe("Beteiligung aus nach Auszählung", sd("wert/wb_onair"), "0")
        sd("az/aus"); time.sleep(0.6)
        pruefe("aus", sd("wert/az_onair"), "0")
        pruefe("Konsole ohne Fehler", konsole, [])
        browser.close()
finally:
    srv.terminate(); api.terminate()
print("\nALLES OK" if not fehler else f"\nFEHLER: {fehler}")
sys.exit(1 if fehler else 0)
