"""
Ende-zu-Ende-Test: Wahlen-API -> Grafik-Server (Controller + oGraf-Server-API) -> Renderer-Seite in Chrome.
Aufruf: python3 test_kette.py <wahlen.sqlite> <jahr> <ausgabeordner> [<hintergrund.png>]
Steuert nur über die Controller-Befehle (/sd/...), wie das Stream Deck.
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

HIER = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HIER, "..", "grafik_server.py")
API = os.path.join(sys.argv[5] if len(sys.argv) > 5 else "/home/claude/wahlen_db", "wahlen_api.py")
DB, JAHR, AUS = sys.argv[1], sys.argv[2], sys.argv[3]
HG = sys.argv[4] if len(sys.argv) > 4 else None
os.makedirs(AUS, exist_ok=True)
fehler = 0


def pruefe(name, ist, soll):
    global fehler
    ok = ist == soll
    fehler += not ok
    print(f"  {'OK  ' if ok else 'FEHLER'} {name}: {ist}" + ("" if ok else f"  (erwartet {soll})"))


def sd(befehl):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:8795/sd/{befehl}", timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def warten(url):
    for _ in range(100):
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except Exception:
            time.sleep(0.1)
    raise SystemExit(f"{url} startet nicht")


prozesse = [
    subprocess.Popen([sys.executable, "-I", API, "--db", DB, "--port", "8790", "--jahr", JAHR], stdout=subprocess.DEVNULL),
    subprocess.Popen([sys.executable, "-I", SERVER, "--port", "8795", "--jahr", JAHR, "--intervall", "3600"],
                     stdout=subprocess.DEVNULL),
]
try:
    warten("http://127.0.0.1:8790/api")
    warten("http://127.0.0.1:8795/ograf/v1/")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--force-color-profile=srgb"])
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        konsole = []
        page.on("console", lambda m: konsole.append(f"{m.type}: {m.text}"))
        page.on("pageerror", lambda e: konsole.append(f"pageerror: {e}"))
        fehl_urls = []
        page.on("response", lambda r: fehl_urls.append(r.url) if r.status >= 400 else None)
        page.goto("http://127.0.0.1:8795/renderer")
        if HG:
            data = base64.b64encode(open(HG, "rb").read()).decode()
            page.evaluate(f"document.body.style.background = 'url(data:image/png;base64,{data})'")
        time.sleep(0.5)

        def bild(name):
            page.screenshot(path=os.path.join(AUS, f"{name}.png"))

        print("== oGraf-Server-API")
        with urllib.request.urlopen("http://127.0.0.1:8795/ograf/v1/graphics") as r:
            g = json.loads(r.read())
        pruefe("Grafik gelistet", "wahlen2027-hochrechnung-kanton" in [x["id"] for x in g["graphics"]], True)
        with urllib.request.urlopen("http://127.0.0.1:8795/ograf/v1/renderers/haupt") as r:
            pruefe("Renderer verbunden", json.loads(r.read())["renderer"]["status"]["connected"], True)

        print("== Ablauf BS (wie Referenz)")
        c, z = sd("ein")
        pruefe("Ein ohne Kanton abgelehnt", c, 409)
        c, z = sd("kanton/BS")
        pruefe("Kanton BS gewählt", (c, z["kanton"], z["auf_sendung"]), (200, "BS", False))
        pruefe("Titel", (z["daten"]["titel"], z["daten"]["untertitel"]), (f"{'Resultat' if JAHR == '2023' else 'Hochrechnung'} BS", "Nationalrat, 4 Sitze"))
        pruefe("Schritte total", z["schritte_total"], 6)
        c, z = sd("ein")
        pruefe("Ein", (c, z["auf_sendung"], z["schritt"]), (200, True, 0))
        time.sleep(0.2)
        bild("01_BS_sitze")
        c, z = sd("weiter")
        pruefe("Weiter -> Prozent", (c, z["schritt"]), (200, 1))
        time.sleep(0.2)
        bild("02_BS_prozent")
        c, z = sd("weiter")
        pruefe("Weiter -> Seite 2 Sitze", z["schritt"], 2)
        time.sleep(0.2)
        bild("03_BS_seite2_sitze")
        c, z = sd("weiter"); c, z = sd("weiter")
        pruefe("Seite 3 Sitze", z["schritt"], 4)
        time.sleep(0.2)
        bild("04_BS_seite3_sitze")
        c, z = sd("zurueck")
        pruefe("Zurück", z["schritt"], 3)
        c, z = sd("weiter"); c, z = sd("weiter")
        bild("05_BS_seite3_prozent")
        c, z = sd("weiter")
        pruefe("Nach letztem Schritt ausgeblendet", (z["auf_sendung"], z["schritt"]), (False, None))
        time.sleep(0.3)
        bild("06_BS_aus")
        n = page.evaluate("document.querySelector('#layer-1 > *').shadowRoot.querySelectorAll('.box').length")
        pruefe("Keine Boxen mehr sichtbar", n, 0)

        print("== Direkter Kantonswechsel auf Sendung (GR)")
        sd("kanton/BS"); sd("ein")
        c, z = sd("kanton/GR")
        pruefe("GR auf Sendung", (z["kanton"], z["auf_sendung"], z["schritt"]), ("GR", True, 0))
        time.sleep(0.2)
        bild("07_GR_sitze")
        c, z = sd("aus")
        pruefe("Aus", z["auf_sendung"], False)

        print("== Animationen messen (Einblenden BS, angehalten an Zeitpunkten)")
        sd("kanton/BS")
        page.evaluate("window.__anhalten = true")
        # Ein auslösen, sofort alle Animationen anhalten und an Zeitpunkten Bilder machen
        import threading
        t = threading.Thread(target=lambda: sd("ein")); t.start()
        for _ in range(100):
            n = page.evaluate("(() => { const el = document.querySelector('#layer-1 > *'); return el && el.shadowRoot ? el.shadowRoot.getAnimations().length : 0 })()")
            if n:
                break
            time.sleep(0.01)
        page.evaluate("document.querySelector('#layer-1 > *').shadowRoot.getAnimations().forEach(a => a.pause())")
        for ms in (0, 150, 300, 450, 600):
            page.evaluate(f"document.querySelector('#layer-1 > *').shadowRoot.getAnimations().forEach(a => a.currentTime = {ms})")
            bild(f"anim_ein_{ms:03d}ms")
        page.evaluate("document.querySelector('#layer-1 > *').shadowRoot.getAnimations().forEach(a => a.play())")
        t.join()
        for name, befehl in (("wechsel", "weiter"), ("seite", "weiter"), ("aus", "aus")):
            t = threading.Thread(target=lambda b=befehl: sd(b)); t.start()
            for _ in range(200):
                n = page.evaluate("(() => { const el = document.querySelector('#layer-1 > *'); return el && el.shadowRoot ? el.shadowRoot.getAnimations().length : 0 })()")
                if n:
                    break
                time.sleep(0.005)
            page.evaluate("document.querySelector('#layer-1 > *').shadowRoot.getAnimations().forEach(a => a.pause())")
            for ms in (100, 200, 300):
                page.evaluate(f"document.querySelector('#layer-1 > *').shadowRoot.getAnimations().forEach(a => a.currentTime = Math.min({ms}, a.effect.getComputedTiming().endTime))")
                bild(f"anim_{name}_{ms:03d}ms")
            page.evaluate("document.querySelector('#layer-1 > *').shadowRoot.getAnimations().forEach(a => a.play())")
            t.join()

        print("== Fehlerfälle")
        c, z = sd("kanton/XX")
        pruefe("Unbekannter Kanton -> 400", c, 400)
        c, z = sd("weiter")
        pruefe("Weiter ohne Sendung -> 409", c, 409)
        c, z = sd("leeren")
        pruefe("Leeren", (c, z["auf_sendung"]), (200, False))

        # Fehlende Schrift- und Wappen-Dateien sind erlaubt (Platzhalter), alles andere nicht
        erlaubt = ("/fonts/", "/wappen/")
        unerwartet_404 = [u for u in fehl_urls if not any(e in u for e in erlaubt)]
        pruefe("Keine unerwarteten HTTP-Fehler", unerwartet_404, [])
        fehler_konsole = [k for k in konsole if k.startswith(("error", "pageerror"))
                          and not ("Failed to load resource" in k and fehl_urls
                                   and not unerwartet_404)]
        pruefe("Keine Fehler in der Browser-Konsole", fehler_konsole, [])
        browser.close()
finally:
    for p in prozesse:
        p.terminate()

print("ALLE TESTS BESTANDEN" if not fehler else f"{fehler} FEHLER")
sys.exit(1 if fehler else 0)
