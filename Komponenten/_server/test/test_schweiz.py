#!/usr/bin/env python3
"""End-to-End-Test Hochrechnung Schweiz: Fortsetzen nach Ausblenden, Seitenwahl, Layer-Teilung mit Kanton.

    python3 test_schweiz.py <db.sqlite mit Hochrechnung Schweiz> <jahr> <ausgabeordner> [hintergrund.png] [wahlen_db-ordner]
Die DB wird während des Tests verändert (zweite Hochrechnung) – eine Kopie verwenden.
"""
import base64, json, os, sqlite3, subprocess, sys, time, urllib.request, urllib.error
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
    req = urllib.request.Request(f"http://127.0.0.1:8795/sd/{befehl}", method="POST" if body else "GET",
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
srv = subprocess.Popen([sys.executable, os.path.join(HIER, "..", "grafik_server.py"), "--jahr", JAHR,
                        "--seiten-schweiz", "3,3,2,3", "--intervall", "2"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        def sichtbar():
            return page.evaluate("""() => { const el=[...document.querySelectorAll('*')].find(e=>e.shadowRoot && e.shadowRoot.querySelector('.reihe'));
                return el ? [...el.shadowRoot.querySelectorAll('.kopf')].map(k=>k.textContent) : [] }""")

        print("== Daten")
        z = sd("ch/neu")
        pruefe("Titel", (z["daten"]["titel"], z["daten"]["untertitel"]), ("Hochrechnung Schweiz", "Nationalrat, Parteistärke"))
        pruefe("Seiten 3,3,2,3", [s["parteien"] for s in z["seiten"]],
               [["SVP", "SP", "Mitte"], ["FDP", "Grüne", "GLP"], ["EVP", "EDU"], ["PdA/Sol.", "Lega", "Übrige"]])
        pruefe("Ohne Sitze: 4 Schritte", z["schritte_total"], 4)
        pruefe("Start Seite 1", z["naechster_start"]["seite"], 1)

        print("== Ablauf mit kurzfristigem Ausblenden")
        sd("ch/ein"); time.sleep(1.0); bild("01_seite1")
        pruefe("Seite 1 sichtbar", sichtbar(), ["SVP", "SP", "Mitte"])
        sd("ch/weiter"); time.sleep(0.8); bild("02_seite2")
        pruefe("Seite 2 sichtbar", sichtbar(), ["FDP", "Grüne", "GLP"])
        z = sd("ch/aus?sofort=1"); time.sleep(0.3)
        pruefe("Nach Aus: nächster Start Seite 3", z["naechster_start"]["seite"], 3)
        pruefe("Status-Text", sd("ch/status?format=text"), "bereit\nab Seite 3")
        z = sd("ch/ein"); time.sleep(1.0); bild("03_fortgesetzt_seite3")
        pruefe("Fortgesetzt mit Seite 3", (z["seite_aktuell"], sichtbar()), (3, ["EVP", "EDU"]))
        sd("ch/weiter"); time.sleep(0.8); bild("04_seite4")
        pruefe("Seite 4", sichtbar(), ["PdA/Sol.", "Lega", "Übrige"])
        z = sd("ch/weiter"); time.sleep(0.8)
        pruefe("Nach letzter Seite ausgeblendet", z["auf_sendung"], False)
        pruefe("… und nächstes Mal von vorne", z["naechster_start"]["seite"], 1)

        print("== Aus auf der letzten Seite")
        sd("ch/seite/4"); z = sd("ch/ein"); time.sleep(0.8)
        pruefe("Direkt Seite 4 ein", z["seite_aktuell"], 4)
        z = sd("ch/aus"); time.sleep(0.6)
        pruefe("Aus auf letzter Seite: wieder Seite 1", z["naechster_start"]["seite"], 1)

        print("== Seitenwahl und Von vorne")
        z = sd("ch/seite/2"); pruefe("Seite 2 vorgemerkt", z["naechster_start"]["seite"], 2)
        z = sd("ch/vonvorne"); pruefe("Von vorne", z["naechster_start"]["seite"], 1)
        sd("ch/ein"); time.sleep(0.8)
        z = sd("ch/seite/3"); time.sleep(0.8)
        pruefe("Auf Sendung zu Seite 3 springen", (z["seite_aktuell"], sichtbar()), (3, ["EVP", "EDU"]))

        print("== Gleicher Platz wie Kanton")
        sd("kanton/BS"); z = sd("ein"); time.sleep(1.2); bild("05_kanton_verdraengt_schweiz")
        zc = sd("ch/zustand")
        pruefe("Schweiz automatisch aus", zc["auf_sendung"], False)
        pruefe("Schweiz merkt sich Seite 4", zc["naechster_start"]["seite"], 4)
        pruefe("Kanton auf Sendung", sichtbar()[:1], ["SP"])
        z = sd("ch/ein"); time.sleep(1.2)
        pruefe("Kanton automatisch aus", sd("zustand")["auf_sendung"], False)
        pruefe("Schweiz wieder da, Seite 4", (z["seite_aktuell"], sichtbar()), (4, ["PdA/Sol.", "Lega", "Übrige"]))
        z = sd("ch/aus"); time.sleep(0.6)

        print("== Neue Hochrechnung setzt zurück")
        sd("ch/seite/3")
        pruefe("Vorgemerkt Seite 3", sd("ch/zustand")["naechster_start"]["seite"], 3)
        c = sqlite3.connect(DB)
        c.execute("""INSERT INTO hochrechnung (grist_id,wahl_jahr,rat,kanton_nummer,institut,nummer,zeitpunkt,partei_id,staerke,freigegeben)
                     SELECT grist_id+100, wahl_jahr, rat, kanton_nummer, institut, 2, '2023-10-22T17:00:00', partei_id,
                            staerke + CASE partei_id WHEN 3 THEN 0.6 ELSE 0 END, 1 FROM hochrechnung WHERE nummer = 1""")
        c.commit(); c.close()
        time.sleep(3.0)
        z = sd("ch/zustand")
        pruefe("Hochrechnung Nr. 2 erkannt", z["meta"]["hochrechnung_nr"], 2)
        pruefe("Nächste Einblendung wieder Seite 1", z["naechster_start"]["seite"], 1)

        print("== Aktualisierung auf Sendung")
        sd("ch/ein"); time.sleep(1.0)
        c = sqlite3.connect(DB)
        c.execute("UPDATE hochrechnung SET staerke = staerke + 0.3 WHERE nummer = 2 AND partei_id = 4"); c.commit(); c.close()
        time.sleep(3.5); bild("06_aktualisiert")
        werte = page.evaluate("""() => { const el=[...document.querySelectorAll('*')].find(e=>e.shadowRoot && e.shadowRoot.querySelector('.reihe'));
            return [...el.shadowRoot.querySelectorAll('.zelle:last-child .wert')].map(k=>k.textContent) }""")
        pruefe("Neuer Wert auf Sendung (SVP 29.3%)", werte[0], "29.3%")
        sd("ch/aus"); time.sleep(0.6); sd("ch/leeren")

        pruefe("Keine unerwarteten HTTP-Fehler", [u for u in fehl_urls if "/fonts/" not in u and "/wappen/" not in u], [])
        pruefe("Keine Fehler in der Browser-Konsole",
               [k for k in konsole if k.startswith(("error", "pageerror")) and "Failed to load resource" not in k], [])
        c = browser.new_page(viewport={"width": 1500, "height": 1000})
        sd("ch/seite/3")
        c.goto("http://127.0.0.1:8795/controller/schweiz"); time.sleep(1.5)
        c.screenshot(path=os.path.join(AUS, "controller_schweiz.png"))
        browser.close()
finally:
    srv.terminate(); api.terminate()
print("ALLE TESTS BESTANDEN" if not fehler else f"FEHLER: {fehler}")
sys.exit(1 if fehler else 0)
