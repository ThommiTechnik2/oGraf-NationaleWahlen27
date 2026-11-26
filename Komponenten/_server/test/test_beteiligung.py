#!/usr/bin/env python3
"""End-to-End-Test Videowand «Wahlbeteiligung».
    python3 test_beteiligung.py <db.sqlite> <jahr> <ausgabeordner> [wahlen_db-ordner]
"""
import json, os, subprocess, sys, time, urllib.request, urllib.error
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
srv = subprocess.Popen([sys.executable, os.path.join(HIER, "..", "grafik_server.py"), "--jahr", JAHR], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        sichtbar = lambda: wand.evaluate("""() => { const el=[...document.querySelectorAll('*')].find(e=>e.shadowRoot&&e.shadowRoot.querySelector('svg.ring'));
            if(!el) return null; const s=el.shadowRoot; return {opacity:s.querySelector('.stage').style.opacity, wert:s.querySelector('.wert').textContent,
            anteil:s.querySelector('circle.anteil').style.strokeDasharray} }""")

        z = sd("wb/status"); print("== Daten", z["meta"], z["daten"])
        pruefe("Wert vorhanden", z["daten"].get("wert") is not None, True)
        sd("wb/ein"); time.sleep(0.5); bild("1_anfang"); time.sleep(1.8); bild("2_fertig")
        s = sichtbar(); print("  ", s)
        pruefe("Grafik sichtbar", s and s["opacity"], "1")
        pruefe("Wert-Text", s and s["wert"], f"{z['daten']['wert']:.1f}%")
        pruefe("on air", sd("wert/wb_onair"), "1")
        print("  Anzeige:", repr(sd("wert/wb_anzeige")))
        sd("wb/neu"); time.sleep(0.8)
        # Layer-Übernahme: National ein -> Beteiligung aus
        sd("nat/ein"); time.sleep(1.0)
        pruefe("Beteiligung aus nach National", sd("wert/wb_onair"), "0")
        sd("wb/ein"); time.sleep(1.0)
        pruefe("National aus nach Beteiligung", sd("wert/nat_onair"), "0")
        pruefe("Beteiligung wieder an", sd("wert/wb_onair"), "1")
        sd("wb/aus"); time.sleep(0.6)
        pruefe("aus", sd("wert/wb_onair"), "0")
        pruefe("Konsole ohne Fehler", konsole, [])
        browser.close()
finally:
    srv.terminate(); api.terminate()
print("\nALLES OK" if not fehler else f"\nFEHLER: {fehler}")
sys.exit(1 if fehler else 0)
