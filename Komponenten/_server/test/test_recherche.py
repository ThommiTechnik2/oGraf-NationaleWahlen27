#!/usr/bin/env python3
"""Test Recherche-Seite: python3 test_recherche.py <db mit Historie> <jahr> <ausgabeordner> [wahlen_db-ordner]"""
import os, subprocess, sys, time, urllib.request
from playwright.sync_api import sync_playwright

HIER = os.path.dirname(os.path.abspath(__file__))
DB, JAHR, AUS = sys.argv[1], sys.argv[2], sys.argv[3]
API = os.path.join(sys.argv[4] if len(sys.argv) > 4 else "/home/claude/wahlen_db", "wahlen_api.py")
os.makedirs(AUS, exist_ok=True)
fehler = []

def pruefe(n, ist, soll):
    ok = (soll(ist) if callable(soll) else ist == soll)
    print(f"  {'OK  ' if ok else 'FEHL'} {n}: {ist}")
    if not ok: fehler.append(n)

def warten(url):
    for _ in range(50):
        try: urllib.request.urlopen(url, timeout=1); return
        except Exception: time.sleep(0.2)
    raise SystemExit(f"{url} startet nicht")

api = subprocess.Popen([sys.executable, API, "--db", DB, "--jahr", JAHR], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
srv = subprocess.Popen([sys.executable, os.path.join(HIER, "..", "grafik_server.py"), "--jahr", JAHR], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    warten("http://127.0.0.1:8790/api"); warten("http://127.0.0.1:8795/ograf/v1/")
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path="/usr/bin/google-chrome")
        s = b.new_page(viewport={"width": 1366, "height": 900})
        konsole = []
        s.on("pageerror", lambda e: konsole.append(str(e)))
        s.goto("http://127.0.0.1:8795/recherche"); time.sleep(1.2)
        zeilen = lambda sel: s.eval_on_selector_all(sel + " tr", "rs => rs.map(r => [...r.cells].map(c => c.innerText.trim()))")
        pruefe("Mitglieder geladen", len(zeilen("#m-zeilen")), lambda n: n > 0)
        s.select_option("#m-partei", "Grüne"); s.select_option("#m-kanton", "LU"); s.select_option("#m-geschlecht", "f"); time.sleep(0.8)
        z = zeilen("#m-zeilen"); print("   ", z[:2])
        pruefe("letzte grüne Frau LU", z[0][0].startswith("Cécile Bühlmann"), True)
        s.screenshot(path=os.path.join(AUS, "1_mitglieder.png"))
        s.click("button[data-zurueck=m]"); s.fill("#m-name", "glanz"); time.sleep(0.8)
        z = zeilen("#m-zeilen"); pruefe("Namenssuche + Familie", (z[0][0][:13], "Mitte" in z[0][1]), ("Ida Glanzmann", True))
        s.click("button[data-ansicht=staerke]"); time.sleep(0.3)
        s.select_option("#s-partei", "FDP"); time.sleep(0.8)
        s.click("#staerke th[data-sort=staerke]"); s.click("#staerke th[data-sort=staerke]"); time.sleep(0.8)   # aufsteigend
        z = zeilen("#s-zeilen"); print("   ", z[:3])
        pruefe("FDP tiefster Wert = laufende Wahl", (z[0][0], "tiefster Wert" in z[0][4], "laufende Wahl" in z[0][5]), ("2023", True, True))
        pruefe("Info-Zeile", s.inner_text("#s-info"), lambda t: "Laufende Wahl: FDP 14.3 %" in t)
        s.select_option("#s-partei", "Mitte"); s.select_option("#s-kanton", "LU"); time.sleep(0.8)
        z = zeilen("#s-zeilen"); pruefe("Mitte LU mit Vorgängern", any("CVP" in r[2] for r in z), True)
        s.screenshot(path=os.path.join(AUS, "2_staerke.png"))
        pruefe("Konsole ohne Fehler", konsole, [])
        b.close()
finally:
    srv.terminate(); api.terminate()
print("\nALLES OK" if not fehler else f"\nFEHLER: {fehler}")
sys.exit(1 if fehler else 0)
