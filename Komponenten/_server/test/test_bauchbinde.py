#!/usr/bin/env python3
"""End-to-End-Test Bauchbinden: Wahlen-API + Grafik-Server + Renderer (Chrome), Steuerung über /sd/bb/...

    python3 test_bauchbinde.py <db.sqlite> <jahr> <ausgabeordner> [hintergrund.png] [wahlen_db-ordner]
"""
import base64, json, os, subprocess, sys, time, urllib.request, urllib.error
from playwright.sync_api import sync_playwright

HIER = os.path.dirname(os.path.abspath(__file__))
DB, JAHR, AUS = sys.argv[1], sys.argv[2], sys.argv[3]
HG = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else None
API = os.path.join(sys.argv[5] if len(sys.argv) > 5 else "/home/claude/wahlen_db", "wahlen_api.py")
os.makedirs(AUS, exist_ok=True)
fehler = []

def pruefe(name, ist, soll):
    ok = ist == soll
    print(f"  {'OK  ' if ok else 'FEHL'} {name}: {ist}" + ("" if ok else f"  (erwartet {soll})"))
    if not ok:
        fehler.append(name)

def sd(befehl, erwarte=200, **body):
    url = f"http://127.0.0.1:8795/sd/bb/{befehl}"
    req = urllib.request.Request(url, method="POST" if body else "GET",
                                 data=json.dumps(body).encode() if body else None, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            code, d = r.status, (json.loads(r.read()) if "json" in r.headers.get("Content-Type", "") else r.read().decode())
    except urllib.error.HTTPError as e:
        code, d = e.code, json.loads(e.read())
    if code != erwarte:
        fehler.append(f"{befehl}: {code}")
        print(f"  FEHL {befehl}: HTTP {code} {d}")
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
    warten("http://127.0.0.1:8790/api")
    warten("http://127.0.0.1:8795/ograf/v1/")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--force-color-profile=srgb"])
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        konsole, fehl_urls = [], []
        page.on("console", lambda m: konsole.append(f"{m.type}: {m.text}"))
        page.on("pageerror", lambda e: konsole.append(f"pageerror: {e}"))
        page.on("response", lambda r: fehl_urls.append(r.url) if r.status >= 400 else None)
        page.goto("http://127.0.0.1:8795/renderer")
        if HG:
            data = base64.b64encode(open(HG, "rb").read()).decode()
            page.evaluate(f"document.body.style.background = 'url(data:image/png;base64,{data})'")
        time.sleep(0.5)
        bild = lambda n: page.screenshot(path=os.path.join(AUS, f"{n}.png"))

        print("== oGraf-Server-API")
        with urllib.request.urlopen("http://127.0.0.1:8795/ograf/v1/graphics") as r:
            ids = sorted(g["id"] for g in json.loads(r.read())["graphics"])
        pruefe("Bauchbinde gelistet", "wahlen2027-bauchbinde" in ids, True)

        print("== Liste aus Grist")
        z = sd("zustand")
        pruefe("Freigegebene Einträge", [e["zeile1"] for e in z["liste"]][:3], ["Lukas Golder", "Cloé Jans", "Sandro Brotz"])
        pruefe("Nicht freigegeben fehlt", any(e["zeile1"] == "Nicht freigegeben" for e in z["liste"]), False)
        pruefe("Erster Eintrag ausgewählt", z["index"], 0)
        pruefe("Slot 1 Text", sd("slottext/1"), "▶ Lukas Golder")

        print("== Ein / Aus")
        z = sd("ein"); time.sleep(0.8); bild("01_golder")
        pruefe("Auf Sendung", (z["auf_sendung"], z["eintrag_auf_sendung"]["zeile1"]), (True, "Lukas Golder"))
        pruefe("Status-Text", sd("status?format=text"), "ON AIR\nLukas Golder")
        z = sd("slot/2"); time.sleep(1.0); bild("02_jans_direkt")
        pruefe("Direkter Wechsel per Slot", z["eintrag_auf_sendung"]["zeile1"], "Cloé Jans")
        z = sd("aus"); time.sleep(0.4); bild("03_aus")
        pruefe("Aus", z["auf_sendung"], False)
        sichtbar = page.evaluate("""() => { const el=[...document.querySelectorAll('*')].find(e=>e.shadowRoot);
            return el ? getComputedStyle(el.shadowRoot.querySelector('.name')).visibility : 'keine' }""")
        pruefe("Nichts mehr sichtbar", sichtbar, "hidden")

        print("== Einzeilig, lang, Freitext")
        sd("waehle/4"); sd("ein"); time.sleep(0.8); bild("04_ort_einzeilig"); sd("aus")
        sd("waehle/5"); sd("ein"); time.sleep(0.8); bild("05_lang")
        breite = page.evaluate("""() => { const el=[...document.querySelectorAll('*')].find(e=>e.shadowRoot);
            return Math.max(el.shadowRoot.querySelector('.name').offsetWidth, el.shadowRoot.querySelector('.funktion').offsetWidth) }""")
        pruefe("Lange Texte passen (≤1720 px)", breite <= 1720, True)
        sd("aus"); time.sleep(0.3)
        z = sd("frei", zeile1="Thomas Probst", zeile2="Regie", ein="1"); time.sleep(0.8); bild("06_freitext")
        pruefe("Freitext auf Sendung", z["eintrag_auf_sendung"]["zeile1"], "Thomas Probst")
        sd("aus"); time.sleep(0.3)

        print("== Auto-Aus")
        sd("waehle/0"); sd("auto/2"); z = sd("ein")
        pruefe("Auto-Aus gesetzt", z["auto_aus"], 2)
        time.sleep(3.0)
        pruefe("Nach 2 s automatisch aus", sd("zustand")["auf_sendung"], False)
        sd("auto/0")

        print("== Ein und weiter, Navigation")
        z = sd("ein-weiter"); pruefe("Ein und nächste gewählt", (z["eintrag_auf_sendung"]["zeile1"], z["index"]), ("Lukas Golder", 1))
        sd("aus"); z = sd("vorherige"); pruefe("Vorherige", z["index"], 0)
        z = sd("naechste"); pruefe("Nächste", z["index"], 1)

        print("== Gewählte aus BFS-Daten")
        z = sd("quelle/nr/BS")
        pruefe("NR BS Einträge", [(e["zeile1"], e["zeile2"]) for e in z["liste"]][:2],
               [("Sarah Wyss", "Nationalrätin SP/BS"), ("Sibel Arslan", "Nationalrätin Grüne/BS")])
        z = sd("quelle/sr/BS")
        pruefe("SR BS", [(e["zeile1"], e["zeile2"]) for e in z["liste"]], [("Eva Herzog", "Ständerätin SP/BS")])
        z = sd("quelle/nr/ZH")
        neu = [e for e in z["liste"] if e["zeile2"].startswith("neu gewählt")]
        pruefe("Neu Gewählte markiert", len(neu) > 0, True)
        sd("quelle/grist")

        print("== Animation messen (Ein, angehalten)")
        sd("waehle/0")
        page.evaluate("""() => { window.__halt = true }""")
        sd("ein"); time.sleep(0.9); sd("aus"); time.sleep(0.4)
        # erneut einblenden und Animationen anhalten
        urllib.request.urlopen("http://127.0.0.1:8795/sd/bb/ein", timeout=10).read() if False else None
        import threading
        t = threading.Thread(target=lambda: sd("ein")); t.start()
        page.wait_for_function("""() => { const el=[...document.querySelectorAll('*')].find(e=>e.shadowRoot);
            return el && el.shadowRoot.getAnimations().length > 0 }""", timeout=5000)
        page.evaluate("""() => { const el=[...document.querySelectorAll('*')].find(e=>e.shadowRoot);
            el.shadowRoot.getAnimations().forEach(a => a.pause()) }""")
        for ms in (40, 120, 200, 300, 350, 420, 480):
            page.evaluate(f"""() => {{ const el=[...document.querySelectorAll('*')].find(e=>e.shadowRoot);
                el.shadowRoot.getAnimations().forEach(a => {{ a.currentTime = {ms} }}) }}""")
            bild(f"anim_ein_{ms:03d}ms")
        page.evaluate("""() => { const el=[...document.querySelectorAll('*')].find(e=>e.shadowRoot);
            el.shadowRoot.getAnimations().forEach(a => a.play()) }""")
        t.join(); time.sleep(0.6)
        sd("aus"); time.sleep(0.4)
        sd("leeren")

        unerwartet = [u for u in fehl_urls if "/fonts/" not in u]
        pruefe("Keine unerwarteten HTTP-Fehler", unerwartet, [])
        pruefe("Keine Fehler in der Browser-Konsole",
               [k for k in konsole if k.startswith(("error", "pageerror")) and "Failed to load resource" not in k], [])

        # Controller-Seite
        c = browser.new_page(viewport={"width": 1500, "height": 1000})
        c.goto("http://127.0.0.1:8795/controller/bauchbinden"); time.sleep(1.5)
        c.screenshot(path=os.path.join(AUS, "controller_bauchbinden.png"))
        browser.close()
finally:
    srv.terminate(); api.terminate()
print("ALLE TESTS BESTANDEN" if not fehler else f"FEHLER: {fehler}")
sys.exit(1 if fehler else 0)
