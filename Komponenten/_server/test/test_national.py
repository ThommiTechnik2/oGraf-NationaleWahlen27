#!/usr/bin/env python3
"""End-to-End-Test Videowand «Hochrechnung National» (Renderer «wand»).

    python3 test_national.py <db.sqlite mit Hochrechnung Schweiz> <jahr> <ausgabeordner> [wahlen_db-ordner]
"""
import json, os, subprocess, sys, threading, time, urllib.request, urllib.error
from playwright.sync_api import sync_playwright

HIER = os.path.dirname(os.path.abspath(__file__))
DB, JAHR, AUS = sys.argv[1], sys.argv[2], sys.argv[3]
API = os.path.join(sys.argv[4] if len(sys.argv) > 4 else "/home/claude/wahlen_db", "wahlen_api.py")
os.makedirs(AUS, exist_ok=True)
fehler = []

def pruefe(name, ist, soll):
    ok = ist == soll
    print(f"  {'OK  ' if ok else 'FEHL'} {name}: {ist}" + ("" if ok else f"  (erwartet {soll})"))
    if not ok:
        fehler.append(name)

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
        try:
            urllib.request.urlopen(url, timeout=1); return
        except Exception:
            time.sleep(0.2)
    raise SystemExit(f"{url} startet nicht")

api = subprocess.Popen([sys.executable, API, "--db", DB, "--jahr", JAHR], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
srv = subprocess.Popen([sys.executable, os.path.join(HIER, "..", "grafik_server.py"), "--jahr", JAHR],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    warten("http://127.0.0.1:8790/api"); warten("http://127.0.0.1:8795/ograf/v1/")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--force-color-profile=srgb"])
        wand = browser.new_page(viewport={"width": 1920, "height": 1080})
        haupt = browser.new_page(viewport={"width": 1920, "height": 1080})
        konsole = []
        for p in (wand, haupt):
            p.on("pageerror", lambda e: konsole.append(f"pageerror: {e}"))
            p.on("console", lambda m: konsole.append(f"{m.type}: {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
        wand.goto("http://127.0.0.1:8795/renderer/wand")
        haupt.goto("http://127.0.0.1:8795/renderer")
        time.sleep(0.8)
        bild = lambda n, p=wand: p.screenshot(path=os.path.join(AUS, f"{n}.png"))
        def spalten(p=wand):
            return p.evaluate("""() => { const el=[...document.querySelectorAll('*')].find(e=>e.shadowRoot && e.shadowRoot.querySelector('.flaeche'));
                return el ? [...el.shadowRoot.querySelectorAll('.spalte .name')].map(n=>n.textContent) : null }""")

        print("== Renderer")
        with urllib.request.urlopen("http://127.0.0.1:8795/ograf/v1/renderers") as r:
            pruefe("Zwei Renderer", [x["id"] for x in json.loads(r.read())["renderers"]], ["haupt", "wand"])
        with urllib.request.urlopen("http://127.0.0.1:8795/controller/api/system") as r:
            pruefe("Wand verbunden", json.loads(r.read())["renderer_wand"]["verbunden"], True)

        print("== Daten")
        z = sd("nat/neu")
        pruefe("Titel", z["daten"]["titel"], "Hochrechnung Nationalrat")
        pruefe("Reihenfolge nach Vorwahl, Seiten 6/5", [s["parteien"] for s in z["seiten"]],
               [["SVP", "SP", "FDP", "Mitte", "Grüne", "GLP"], ["EVP", "PdA/Sol.", "EDU", "Lega", "Übrige"]])
        pruefe("11 Schritte", z["schritte_total"], 11)

        print("== Ablauf")
        sd("nat/ein"); time.sleep(1.2)
        pruefe("Erster Balken SVP", spalten(), ["SVP"])
        pruefe("Nichts auf dem Hauptausgang", spalten(haupt), None)
        for _ in range(5):
            sd("nat/weiter"); time.sleep(0.7)
        bild("01_seite1_komplett")
        pruefe("Seite 1 komplett", spalten(), ["SVP", "SP", "FDP", "Mitte", "Grüne", "GLP"])
        z = sd("nat/weiter"); time.sleep(1.2); bild("02_seite2_evp")
        pruefe("Neue Seite: nur EVP", (spalten(), z["seite_aktuell"]), (["EVP"], 2))
        z = sd("nat/zurueck"); time.sleep(0.8)
        pruefe("Zurück auf Seite 1 (alle 6)", spalten(), ["SVP", "SP", "FDP", "Mitte", "Grüne", "GLP"])
        sd("nat/weiter"); time.sleep(1.0); sd("nat/weiter"); time.sleep(0.8)
        z = sd("nat/aus?sofort=1"); time.sleep(0.3)
        pruefe("Nach Aus: nächster Start EDU (Schritt 8)", (z["naechster_start"]["schritt"], z["daten"]["parteien"][8]["kurz"]), (8, "EDU"))
        z = sd("nat/ein"); time.sleep(1.3); bild("03_fortgesetzt_edu")
        pruefe("Fortgesetzt: EVP, PdA stehen, EDU neu", spalten(), ["EVP", "PdA/Sol.", "EDU"])
        sd("nat/weiter"); time.sleep(0.7); sd("nat/weiter"); time.sleep(1.0); bild("04_seite2_komplett")
        pruefe("Seite 2 komplett", spalten(), ["EVP", "PdA/Sol.", "EDU", "Lega", "Übrige"])

        print("== Gleichzeitig: Schweiz-Insert auf dem Hauptausgang")
        sd("ch/ein"); time.sleep(1.0)
        pruefe("Wand bleibt stehen", sd("nat/zustand")["auf_sendung"], True)
        pruefe("Insert auf Hauptausgang", haupt.evaluate("""() => !!([...document.querySelectorAll('*')].find(e=>e.shadowRoot && e.shadowRoot.querySelector('.reihe')))"""), True)
        sd("ch/aus"); time.sleep(0.6)

        print("== Wand-Seite neu laden (z. B. Videowand-Rechner startet neu)")
        wand.reload(); time.sleep(1.5)
        pruefe("Nach Neuladen wieder alles da", spalten(), ["EVP", "PdA/Sol.", "EDU", "Lega", "Übrige"])

        print("== Seitenwahl und Ende")
        z = sd("nat/seite/1"); time.sleep(1.0)
        pruefe("Seite 1 direkt (SVP)", (z["seite_aktuell"], spalten()), (1, ["SVP"]))
        sd("nat/seite/2"); time.sleep(1.0)
        for _ in range(4):
            sd("nat/weiter"); time.sleep(0.6)
        z = sd("nat/weiter"); time.sleep(0.6)
        pruefe("Nach Übrige: ausgeblendet, nächstes Mal von vorne", (z["auf_sendung"], z["naechster_start"]["schritt"]), (False, 0))

        print("== Animation (Balken SP wächst)")
        sd("nat/ein"); time.sleep(1.2)
        t = threading.Thread(target=lambda: sd("nat/weiter")); t.start()
        wand.wait_for_function("""() => { const el=[...document.querySelectorAll('*')].find(e=>e.shadowRoot && e.shadowRoot.querySelector('.flaeche'));
            return el && el.shadowRoot.getAnimations().length > 0 }""", timeout=5000)
        wand.evaluate("""() => { const el=[...document.querySelectorAll('*')].find(e=>e.shadowRoot && e.shadowRoot.querySelector('.flaeche'));
            el.shadowRoot.getAnimations().forEach(a => a.pause()) }""")
        for ms in (0, 100, 200, 300, 420):
            wand.evaluate(f"""() => {{ const el=[...document.querySelectorAll('*')].find(e=>e.shadowRoot && e.shadowRoot.querySelector('.flaeche'));
                el.shadowRoot.getAnimations().forEach(a => {{ a.currentTime = {ms} }}) }}""")
            bild(f"anim_sp_{ms:03d}ms")
        wand.evaluate("""() => { const el=[...document.querySelectorAll('*')].find(e=>e.shadowRoot && e.shadowRoot.querySelector('.flaeche'));
            el.shadowRoot.getAnimations().forEach(a => a.play()) }""")
        t.join(); time.sleep(0.5)
        sd("nat/leeren")
        pruefe("Keine Fehler in der Browser-Konsole", konsole, [])
        c = browser.new_page(viewport={"width": 1500, "height": 1000})
        c.goto("http://127.0.0.1:8795/controller/national"); time.sleep(1.5)
        c.screenshot(path=os.path.join(AUS, "controller_national.png"))
        c.goto("http://127.0.0.1:8795/"); time.sleep(2.5)
        c.screenshot(path=os.path.join(AUS, "menu.png"))
        browser.close()
finally:
    srv.terminate(); api.terminate()
print("ALLE TESTS BESTANDEN" if not fehler else f"FEHLER: {fehler}")
sys.exit(1 if fehler else 0)
