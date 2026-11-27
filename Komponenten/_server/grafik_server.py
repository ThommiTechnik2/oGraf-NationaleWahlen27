#!/usr/bin/env python3
"""
Grafik-Server Wahlen 2027 – nur Python-Standardbibliothek.

Enthält drei Teile, alle auf einem Port (Standard 8795):

1. oGraf-Server (Teilmenge der EBU OGraf Server API v1) unter /ograf/v1
   GET  /ograf/v1/                                            Server-Info
   GET  /ograf/v1/graphics                                    Grafiken (alle *.ograf.json im Komponenten-Ordner)
   GET  /ograf/v1/graphics/{graphicId}                        Manifest
   GET  /ograf/v1/renderers, /renderers/{id}, /renderers/{id}/target?renderTarget=...
   POST /ograf/v1/renderers/{id}/target/graphicInstance/load
   POST /ograf/v1/renderers/{id}/target/graphicInstance/playAction | stopAction | updateAction
   POST /ograf/v1/renderers/{id}/target/graphicInstance/customActions/{customActionId}
   PUT  /ograf/v1/renderers/{id}/target/graphicInstance/clear
   RenderTarget: {"layer": <Zahl>}

2. Renderer-Seite für OBS (Browserquelle 1920x1080):  /renderer   (Renderer-Id "haupt")
   Die Seite holt Befehle per Server-Sent Events und ruft die OGraf-Methoden der Grafiken auf.

3. Controller (Web-Seite und Stream-Deck-Befehle), sprechen ausschliesslich die oGraf-Server-API
   (Standard: dieser Server; per --ograf-api auch ein anderer):
   Hochrechnung Kanton   /controller              /sd/...       Layer --layer (1)
   Hochrechnung Schweiz  /controller/schweiz      /sd/ch/...    Layer --layer (1, gleicher Platz wie Kanton)
   Bauchbinden           /controller/bauchbinden  /sd/bb/...    Layer --layer-bauchbinde (2)

Start:
    python3 grafik_server.py --komponenten .. --wahlen-api http://127.0.0.1:8790/api --jahr 2027
"""
import argparse
import json
import os
import queue
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HIER = os.path.dirname(os.path.abspath(__file__))
ARGS = None
API_PREFIX = "/ograf/v1"
RENDERER_ID = "haupt"
ANTWORT_TIMEOUT = 15

KANTONE = ["ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG", "FR", "SO", "BS", "BL",
           "SH", "AR", "AI", "SG", "GR", "AG", "TG", "TI", "VD", "VS", "NE", "GE", "JU"]


# =============================================================================
# 1. oGraf-Server
# =============================================================================
class Renderer:
    """Verbindung zu einer Renderer-Seite (per SSE). Befehle gehen raus, Antworten kommen per POST zurück."""

    def __init__(self):
        self.verbindungen = {}         # verbindung_id -> queue.Queue
        self.quellen = {}              # verbindung_id -> «casparcg», «obs», «vorschau» … (aus ?quelle= der Seite)
        self.antworten = {}            # befehl_id -> (Event, [Antwort], [Anzahl «unbekannt»], Anzahl Empfänger)
        self.instanzen = {}            # instance_id -> {"graphicId", "layer"}
        # Was gerade pro Layer geladen/sichtbar ist. Damit bekommt eine Renderer-Seite, die später
        # verbindet oder neu lädt (z. B. OBS-Browserquelle), sofort den aktuellen Stand.
        self.stand = {}                # layer -> {"load": befehl, "schritt": int | None}
        self.lock = threading.Lock()

    def wiederherstellen_befehle(self):
        with self.lock:
            return [{"typ": "wiederherstellen", "id": uuid.uuid4().hex, "layer": layer,
                     "load": dict(st["load"]), "schritt": st["schritt"]}
                    for layer, st in sorted(self.stand.items())]

    def verbunden(self):
        return bool(self.verbindungen)

    def verbunden_mit(self, quelle):
        with self.lock:
            return any(q == quelle for q in self.quellen.values())

    def senden(self, befehl):
        if not self.verbindungen:
            raise ServerFehler(503, "Kein Renderer verbunden (Renderer-Seite in OBS/Browser öffnen)")
        befehl["id"] = uuid.uuid4().hex
        ev, ablage = threading.Event(), []
        with self.lock:
            self.antworten[befehl["id"]] = (ev, ablage, [0], len(self.verbindungen))
            for q in self.verbindungen.values():
                q.put(befehl)
        if not ev.wait(ANTWORT_TIMEOUT):
            with self.lock:
                self.antworten.pop(befehl["id"], None)
            raise ServerFehler(504, "Renderer antwortet nicht")
        with self.lock:
            self.antworten.pop(befehl["id"], None)
        if ablage[0].get("fehler") == "GraphicInstance in keinem Renderer vorhanden":
            raise ServerFehler(404, ablage[0]["fehler"])
        return ablage[0]

    def antwort(self, befehl_id, daten):
        with self.lock:
            eintrag = self.antworten.get(befehl_id)
        if not eintrag:
            return
        ev, ablage, unbekannt, empfaenger = eintrag
        if daten.get("unbekannt"):
            # Diese Renderer-Seite kennt die Instanz nicht. Fehler erst, wenn keine Seite sie kennt.
            unbekannt[0] += 1
            if unbekannt[0] >= empfaenger and not ablage:
                ablage.append({"fehler": "GraphicInstance in keinem Renderer vorhanden"})
                ev.set()
            return
        if not ablage:   # mehrere Renderer-Seiten: die erste gültige Antwort zählt
            ablage.append(daten)
            ev.set()


RENDERER_NAMEN = {
    "haupt": "Renderer Hauptausgang (OBS-Browserquelle /renderer)",
    "wand": "Renderer Videowand (Browserquelle/Vollbild /renderer/wand)",
}
RENDERERS = {rid: Renderer() for rid in RENDERER_NAMEN}
RENDERER = RENDERERS["haupt"]


class GrafikHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # Browser lädt neu oder schliesst die Verbindung: normal, kein Fehler
        art = sys.exc_info()[0]
        if art and issubclass(art, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)


class ServerFehler(Exception):
    def __init__(self, code, meldung):
        super().__init__(meldung)
        self.code, self.meldung = code, meldung


def grafiken():
    """Alle *.ograf.json unter dem Komponenten-Ordner (eine Ebene tief)."""
    out = {}
    basis = ARGS.komponenten
    for name in sorted(os.listdir(basis)):
        ordner = os.path.join(basis, name)
        if not os.path.isdir(ordner) or name.startswith(("_", ".")):
            continue
        for f in os.listdir(ordner):
            # «._name» sind macOS-Begleitdateien (beim Kopieren auf USB-Stick/Netzlaufwerk), keine Manifeste
            if f.endswith(".ograf.json") and not f.startswith("."):
                try:
                    with open(os.path.join(ordner, f), encoding="utf-8") as fh:
                        m = json.load(fh)
                    out[m["id"]] = {"manifest": m, "ordner": name, "datei": f}
                except (OSError, ValueError, KeyError) as e:
                    print(f"Manifest {name}/{f} ungültig: {e}", file=sys.stderr)
    return out


def render_target(wert):
    if isinstance(wert, str):
        wert = json.loads(wert)
    if not isinstance(wert, dict) or not isinstance(wert.get("layer"), int):
        raise ServerFehler(404, 'RenderTarget unbekannt: erwartet {"layer": <Zahl>}')
    return wert


def ograf_api(methode, pfad, query, body):
    """Gibt (status, json) zurück."""
    teile = [urllib.parse.unquote(t) for t in pfad.strip("/").split("/") if t]
    if methode == "GET" and not teile:
        return 200, {"name": "Grafik-Server Wahlen 2027", "description": "Teilmenge der OGraf Server API v1",
                     "author": {"name": "Wahlen 2027"}}
    if teile[:1] == ["graphics"]:
        g = grafiken()
        if methode == "GET" and len(teile) == 1:
            return 200, {"graphics": [{"id": k, "version": v["manifest"].get("version"), "name": v["manifest"].get("name"),
                                       "description": v["manifest"].get("description")} for k, v in g.items()]}
        if methode == "GET" and len(teile) == 2:
            if teile[1] not in g:
                raise ServerFehler(404, f"Grafik {teile[1]} nicht gefunden")
            return 200, {"graphic": {"id": teile[1]}, "manifest": g[teile[1]]["manifest"]}
        raise ServerFehler(405, "Nicht unterstützt")
    if teile[:1] == ["renderers"]:
        if methode == "GET" and len(teile) == 1:
            return 200, {"renderers": [{"id": rid, "name": n} for rid, n in RENDERER_NAMEN.items()]}
        if len(teile) < 2 or teile[1] not in RENDERERS:
            raise ServerFehler(404, "Renderer nicht gefunden")
        R = RENDERERS[teile[1]]
        info = {"id": teile[1], "name": RENDERER_NAMEN[teile[1]],
                "description": RENDERER_NAMEN[teile[1]], "status": {"connected": R.verbunden()},
                "renderTargetSchema": {"type": "object", "properties": {"layer": {"type": "integer", "minimum": 0, "maximum": 9}},
                                       "required": ["layer"]}}
        if methode == "GET" and len(teile) == 2:
            return 200, {"renderer": info}
        if methode == "GET" and teile[2:] == ["target"]:
            rt = render_target(query.get("renderTarget"))
            inst = [{"graphicInstanceId": i, "graphic": {"id": v["graphicId"]}}
                    for i, v in R.instanzen.items() if v["layer"] == rt["layer"]]
            return 200, {"renderTarget": rt, "name": f"Layer {rt['layer']}", "graphicInstances": inst}
        if teile[2:4] == ["target", "graphicInstance"]:
            aktion = teile[4] if len(teile) > 4 else None
            rt = render_target(body.get("renderTarget"))
            if aktion == "load" and methode == "POST":
                g = grafiken()
                gid = body.get("graphicId")
                if gid not in g:
                    raise ServerFehler(404, f"Grafik {gid} nicht gefunden")
                params = body.get("params") or {}
                if "data" not in params:
                    raise ServerFehler(400, "params.data fehlt")
                iid = f"{gid}-{uuid.uuid4().hex[:8]}"
                main = f"/grafiken/{urllib.parse.quote(g[gid]['ordner'])}/{g[gid]['manifest']['main']}"
                a = R.senden({"typ": "load", "layer": rt["layer"], "graphicId": gid, "instanceId": iid,
                                     "main": main, "version": g[gid]["manifest"].get("version", ""), "data": params["data"]})
                if a.get("fehler"):
                    raise ServerFehler(550, a["fehler"])
                # Eine Grafik pro Layer: alte Instanzen dieses Layers wurden von der Renderer-Seite entfernt
                for i in [i for i, v in R.instanzen.items() if v["layer"] == rt["layer"]]:
                    R.instanzen.pop(i, None)
                R.instanzen[iid] = {"graphicId": gid, "layer": rt["layer"]}
                befehl = {"typ": "load", "layer": rt["layer"], "graphicId": gid, "instanceId": iid,
                          "main": main, "version": g[gid]["manifest"].get("version", ""), "data": params["data"]}
                with R.lock:
                    R.stand[rt["layer"]] = {"load": befehl, "schritt": None}
                return 200, {"graphicInstanceId": iid, **(a.get("ergebnis") or {"statusCode": 200})}
            if aktion == "clear" and methode == "PUT":
                a = R.senden({"typ": "clear", "layer": rt["layer"]})
                for i in [i for i, v in R.instanzen.items() if v["layer"] == rt["layer"]]:
                    R.instanzen.pop(i, None)
                with R.lock:
                    R.stand.pop(rt["layer"], None)
                return 200, {"graphicInstances": a.get("entfernt", [])}
            methoden = {"playAction": "playAction", "stopAction": "stopAction", "updateAction": "updateAction"}
            if methode == "POST" and (aktion in methoden or aktion == "customActions"):
                iid = body.get("graphicInstanceId")
                if iid not in R.instanzen or R.instanzen[iid]["layer"] != rt["layer"]:
                    raise ServerFehler(404, "GraphicInstance nicht gefunden")
                if aktion == "customActions":
                    params = {"id": teile[5], "payload": body.get("payload"), "skipAnimation": body.get("skipAnimation", False)}
                    m = "customAction"
                else:
                    params, m = body.get("params") or {}, methoden[aktion]
                a = R.senden({"typ": "aktion", "instanceId": iid, "methode": m, "params": params})
                if a.get("fehler"):
                    raise ServerFehler(550, a["fehler"])
                erg = a.get("ergebnis") or {"statusCode": 200}
                with R.lock:
                    st = R.stand.get(rt["layer"])
                    if st and st["load"]["instanceId"] == iid:
                        if m == "playAction":
                            st["schritt"] = erg.get("currentStep")
                        elif m == "stopAction":
                            st["schritt"] = None
                        elif m == "updateAction" and "data" in params:
                            st["load"]["data"] = params["data"]
                return 200, {"graphicInstanceId": iid, **erg}
    raise ServerFehler(404, "Unbekannter Pfad")


# =============================================================================
# 3. Controller
# =============================================================================
class OgrafKlient:
    """HTTP-Client für die oGraf-Server-API (eine Grafik auf einem Layer)."""

    layer = 1
    renderer_id = "haupt"
    BESITZER = {}            # layer -> Controller, der dort zuletzt geladen hat
    BESITZER_LOCK = threading.Lock()

    def _layer_uebernehmen(self):
        """Teilen sich zwei Controller einen Layer (Kanton/Schweiz), blendet der andere zuerst sauber aus."""
        with OgrafKlient.BESITZER_LOCK:
            schluessel = (self.renderer_id, self.layer)
            anderer = OgrafKlient.BESITZER.get(schluessel)
            OgrafKlient.BESITZER[schluessel] = self
        if anderer is not None and anderer is not self and getattr(anderer, "auf_sendung", False):
            try:
                anderer.aus()
            except ServerFehler:
                anderer.auf_sendung = False

    def _api(self, methode, pfad, body=None):
        url = ARGS.ograf_api.rstrip("/") + pfad
        req = urllib.request.Request(url, method=methode, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=ANTWORT_TIMEOUT + 5) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read()).get("title") or ""
            except Exception:
                detail = ""
            raise ServerFehler(e.code, f"oGraf-Server: {detail or e.reason}") from None
        except urllib.error.URLError as e:
            raise ServerFehler(502, f"oGraf-Server nicht erreichbar: {e.reason}") from None

    def _ziel(self):
        return {"layer": self.layer}

    def _instanz_pfad(self, aktion):
        rid = self.renderer_id
        if rid == "haupt" and ARGS.renderer_id is not None:
            rid = ARGS.renderer_id
        return f"/renderers/{rid}/target/graphicInstance/{aktion}"


def wahlen_api(pfad, **q):
    q = {k: v for k, v in q.items() if v not in (None, "")}
    url = f"{ARGS.wahlen_api.rstrip('/')}/{pfad}?{urllib.parse.urlencode(q)}"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise ServerFehler(502, f"Wahlen-API: {e.code} {e.reason}") from None
    except Exception as e:
        raise ServerFehler(502, f"Wahlen-API nicht erreichbar: {e}") from None


class Controller(OgrafKlient):
    """Zustand und Ablauf für das Insert «Hochrechnung Kanton». Spricht nur die oGraf-Server-API."""

    GRAFIK = "wahlen2027-hochrechnung-kanton"

    def __init__(self):
        self.layer = ARGS.layer
        self.lock = threading.RLock()
        self.kanton = None
        self.daten = None              # zuletzt geholte Grafikdaten
        self.meta = {}                 # Modus, Stand usw. aus der Wahlen-API
        self.instanz = None
        self.auf_sendung = False
        self.schritt = None
        self.meldung = ""
        self.zuletzt_gesendet = None

    # ---------- Daten aus der Wahlen-API ----------
    def daten_holen(self, kanton):
        q = urllib.parse.urlencode({"kanton": kanton, "jahr": ARGS.jahr, "lang": ARGS.sprache})
        try:
            with urllib.request.urlopen(f"{ARGS.wahlen_api.rstrip('/')}/nr/kanton-insert?{q}", timeout=5) as r:
                a = json.loads(r.read())
        except Exception as e:
            raise ServerFehler(502, f"Wahlen-API nicht erreichbar: {e}") from None
        parteien = [{k: v for k, v in p.items() if v is not None and k in
                     ("kurz", "farbe", "sitze", "sitze_diff", "staerke", "staerke_diff", "staerke_diff_unsicher")} for p in a.get("daten", [])]
        for p in parteien:   # GDD color-rrggbb verlangt Kleinbuchstaben
            p["farbe"] = (p.get("farbe") or "#8a8a8a").lower()
        daten = {"titel": a.get("titel", ""), "untertitel": a.get("untertitel", ""), "kanton": a.get("kanton") or "",
                 "mit_sitzen": bool(a.get("mit_sitzen")), "nachkommastellen": ARGS.nachkommastellen,
                 "pro_seite": 3, "parteien": parteien}
        meta = {"modus": a.get("modus"), "kanton_abgeschlossen": a.get("kanton_abgeschlossen"),
                "sitze_total": a.get("sitze_total"), "institut": a.get("institut"),
                "hochrechnung_nr": a.get("hochrechnung_nr"), "stand": a.get("stand")}
        return daten, meta

    def schritte(self):
        if not self.daten:
            return 0
        seiten = -(-len(self.daten["parteien"]) // self.daten["pro_seite"])
        return seiten * (2 if self.daten["mit_sitzen"] else 1)

    # ---------- Bedienung ----------
    def waehlen(self, kanton):
        kanton = kanton.upper()
        if kanton not in KANTONE:
            raise ServerFehler(400, f"Unbekannter Kanton: {kanton}")
        with self.lock:
            daten, meta = self.daten_holen(kanton)
            wechsel_auf_sendung = self.auf_sendung and kanton != self.kanton
            self.kanton, self.daten, self.meta = kanton, daten, meta
            self.meldung = "" if daten["parteien"] else f"Keine Daten für {kanton}"
            if wechsel_auf_sendung:
                # Direkter Wechsel: aktuelle Grafik aus, neuen Kanton ein
                self.aus()
                if daten["parteien"]:
                    self.ein()
        return self.zustand()

    def ein(self):
        with self.lock:
            if not self.kanton:
                raise ServerFehler(409, "Zuerst einen Kanton wählen")
            self.daten, self.meta = self.daten_holen(self.kanton)
            if not self.daten["parteien"]:
                raise ServerFehler(409, f"Keine Daten für {self.kanton}")
            if self.auf_sendung:
                return self.zustand()
            self._layer_uebernehmen()
            r = self._api("POST", self._instanz_pfad("load"),
                          {"renderTarget": self._ziel(), "graphicId": self.GRAFIK, "params": {"data": self.daten}})
            self.instanz = r["graphicInstanceId"]
            r = self._api("POST", self._instanz_pfad("playAction"),
                          {"renderTarget": self._ziel(), "graphicInstanceId": self.instanz, "params": {"goto": 0}})
            self.auf_sendung, self.schritt = True, r.get("currentStep", 0)
            self.zuletzt_gesendet = json.dumps(self.daten, sort_keys=True)
        return self.zustand()

    def schritt_aktion(self, delta):
        with self.lock:
            if not self.auf_sendung or not self.instanz:
                raise ServerFehler(409, "Grafik ist nicht auf Sendung")
            r = self._api("POST", self._instanz_pfad("playAction"),
                          {"renderTarget": self._ziel(), "graphicInstanceId": self.instanz, "params": {"delta": delta}})
            self.schritt = r.get("currentStep")
            if self.schritt is None:      # über den letzten Schritt hinaus: Grafik ist ausgeblendet
                self.auf_sendung = False
        return self.zustand()

    def aus(self, sofort=False):
        with self.lock:
            if self.instanz and self.auf_sendung:
                self._api("POST", self._instanz_pfad("stopAction"),
                          {"renderTarget": self._ziel(), "graphicInstanceId": self.instanz,
                           "params": {"skipAnimation": sofort}})
            self.auf_sendung, self.schritt = False, None
        return self.zustand()

    def aktualisieren(self, nur_bei_aenderung=False):
        with self.lock:
            if not self.kanton:
                return self.zustand()
            self.daten, self.meta = self.daten_holen(self.kanton)
            neu = json.dumps(self.daten, sort_keys=True)
            if self.auf_sendung and self.instanz and (not nur_bei_aenderung or neu != self.zuletzt_gesendet):
                self._api("POST", self._instanz_pfad("updateAction"),
                          {"renderTarget": self._ziel(), "graphicInstanceId": self.instanz, "params": {"data": self.daten}})
                self.zuletzt_gesendet = neu
        return self.zustand()

    def leeren(self):
        with self.lock:
            self._api("PUT", self._instanz_pfad("clear"), {"renderTarget": self._ziel()})
            self.instanz, self.auf_sendung, self.schritt = None, False, None
        return self.zustand()

    def zustand(self):
        return {"kanton": self.kanton, "auf_sendung": self.auf_sendung, "schritt": self.schritt,
                "schritte_total": self.schritte(), "daten": self.daten, "meta": self.meta, "meldung": self.meldung,
                "renderer_verbunden": RENDERER.verbunden(), "jahr": ARGS.jahr, "sprache": ARGS.sprache}

    def auto_aktualisieren(self):
        """Hält Daten auf Sendung aktuell (z. B. neue Hochrechnung), nur bei Änderung."""
        while True:
            time.sleep(ARGS.intervall)
            try:
                if self.auf_sendung:
                    self.aktualisieren(nur_bei_aenderung=True)
            except ServerFehler as e:
                self.meldung = e.meldung


CONTROLLER = None


# =============================================================================
# 4. Controller Bauchbinden
# =============================================================================
AEMTER = {  # (weiblich, männlich)
    "nr": {"de": ("Nationalrätin", "Nationalrat"), "fr": ("conseillère nationale", "conseiller national"),
           "it": ("consigliera nazionale", "consigliere nazionale")},
    "sr": {"de": ("Ständerätin", "Ständerat"), "fr": ("conseillère aux États", "conseiller aux États"),
           "it": ("consigliera agli Stati", "consigliere agli Stati")},
}
NEU = {"de": ("neu gewählt", "neu gewählt"), "fr": ("nouvelle élue", "nouvel élu"), "it": ("neoeletta", "neoeletto")}
QUELLEN = ("grist", "nr", "sr")
SLOTS = 24          # Stream Deck XL: Reihen 1–3 = 24 Einträge pro Seite


class BauchbindenController(OgrafKlient):
    """Liste von Bauchbinden (Grist oder Gewählte aus den BFS-Daten), Auswahl, Ein/Aus, Auto-Aus."""

    GRAFIK = "wahlen2027-bauchbinde"

    def __init__(self):
        self.layer = ARGS.layer_bauchbinde
        self.lock = threading.RLock()
        self.quelle = "grist"
        self.kanton = None           # für Quelle nr/sr
        self.kategorie = ""          # Filter für Quelle grist
        self.liste = []
        self.index = None            # ausgewählter Eintrag (Cue)
        self.frei = None             # Freitext-Eintrag
        self.seite = 0               # Stream-Deck-Seite
        self.instanz = None
        self.auf_sendung = False
        self.eintrag_auf_sendung = None
        self.auto_aus = 0            # Sekunden, 0 = aus
        self.ein_seit = None
        self.meldung = ""

    # ---------- Liste ----------
    def _eintrag_aus_gewaehlten(self, r, rat):
        w = 0 if r.get("geschlecht") == "F" else 1
        sprache = ARGS.sprache
        kuerzel = f"{r.get('partei') or ''}/{r.get('kanton') or ''}".strip("/")
        if r.get("status") == "neu":
            zeile2 = f"{NEU[sprache][w]}, {kuerzel}"
        else:
            zeile2 = f"{AEMTER[rat][sprache][w]} {kuerzel}"
        return {"id": f"{rat}-{r.get('kanton')}-{r.get('name')}-{r.get('vorname')}",
                "zeile1": f"{r.get('vorname', '')} {r.get('name', '')}".strip(), "zeile2": zeile2,
                "kategorie": "Nationalrat" if rat == "nr" else "Ständerat",
                "info": f"{r.get('partei') or ''} · {r.get('status') or ''}"}

    def liste_laden(self):
        with self.lock:
            if self.quelle == "grist":
                a = wahlen_api("bauchbinden", kategorie=self.kategorie or None)
                liste = []
                for r in a.get("daten", []):
                    zeile2 = r.get("zeile2") or ""
                    if not zeile2 and (r.get("partei") or r.get("kanton")):
                        zeile2 = "/".join(x for x in (r.get("partei"), r.get("kanton")) if x)
                    liste.append({"id": f"grist-{r['id']}", "zeile1": r.get("zeile1") or "", "zeile2": zeile2,
                                  "kategorie": r.get("kategorie") or "", "info": r.get("sprache") or ""})
            else:
                if not self.kanton:
                    liste = []
                    self.meldung = "Kanton wählen"
                else:
                    a = wahlen_api(f"{self.quelle}/gewaehlte", kanton=self.kanton, jahr=ARGS.jahr, lang=ARGS.sprache)
                    liste = [self._eintrag_aus_gewaehlten(r, self.quelle) for r in a.get("daten", [])]
            liste = [e for e in liste if e["zeile1"]]
            alt_id = self.liste[self.index]["id"] if self.index is not None and self.index < len(self.liste) else None
            self.liste = liste
            ids = [e["id"] for e in liste]
            self.index = ids.index(alt_id) if alt_id in ids else (0 if liste else None)
            self.seite = min(self.seite, max(0, (len(liste) - 1) // SLOTS))
            if liste or self.quelle == "grist":
                self.meldung = "" if liste else "Keine freigegebenen Bauchbinden (Grist: Bauchbinden, «Freigegeben»)"
        return self.zustand()

    def quelle_setzen(self, quelle, kanton=None):
        if quelle not in QUELLEN:
            raise ServerFehler(400, f"Unbekannte Quelle: {quelle} (grist, nr, sr)")
        if kanton:
            kanton = kanton.upper()
            if kanton not in KANTONE:
                raise ServerFehler(400, f"Unbekannter Kanton: {kanton}")
        with self.lock:
            self.quelle = quelle
            if kanton:
                self.kanton = kanton
            self.index, self.seite, self.frei = None, 0, None
            return self.liste_laden()

    def kategorie_setzen(self, kategorie):
        with self.lock:
            self.kategorie = kategorie or ""
            return self.liste_laden()

    # ---------- Auswahl ----------
    def aktueller_eintrag(self):
        if self.frei:
            return self.frei
        if self.index is not None and 0 <= self.index < len(self.liste):
            return self.liste[self.index]
        return None

    def waehlen(self, index, sofort_ein=False):
        with self.lock:
            if not (0 <= index < len(self.liste)):
                raise ServerFehler(404, f"Kein Eintrag an Position {index + 1}")
            self.index, self.frei = index, None
            self.seite = index // SLOTS
            if sofort_ein or self.auf_sendung:
                return self.ein()
        return self.zustand()

    def slot(self, n, sofort_ein=False):
        return self.waehlen(self.seite * SLOTS + n - 1, sofort_ein)

    def bewegen(self, delta):
        with self.lock:
            if not self.liste:
                raise ServerFehler(409, "Liste ist leer")
            i = 0 if self.index is None else self.index + delta
            self.index = max(0, min(len(self.liste) - 1, i))
            self.frei = None
            self.seite = self.index // SLOTS
        return self.zustand()

    def seite_wechseln(self, delta):
        with self.lock:
            seiten = max(1, -(-len(self.liste) // SLOTS))
            self.seite = (self.seite + delta) % seiten
        return self.zustand()

    def freitext(self, zeile1, zeile2=""):
        zeile1, zeile2 = (zeile1 or "").strip(), (zeile2 or "").strip()
        if not zeile1:
            raise ServerFehler(400, "Zeile 1 fehlt")
        with self.lock:
            self.frei = {"id": "frei", "zeile1": zeile1, "zeile2": zeile2, "kategorie": "Freitext", "info": ""}
        return self.zustand()

    # ---------- Sendung ----------
    def _daten(self, e):
        return {"zeile1": e["zeile1"], "zeile2": e.get("zeile2") or ""}

    def ein(self):
        with self.lock:
            e = self.aktueller_eintrag()
            if not e:
                raise ServerFehler(409, "Keine Bauchbinde ausgewählt")
            if self.auf_sendung:
                if self.eintrag_auf_sendung and self.eintrag_auf_sendung["id"] == e["id"] \
                        and self._daten(self.eintrag_auf_sendung) == self._daten(e):
                    return self.zustand()
                self.aus()          # Wechsel: alte Bauchbinde aus, neue ein
            self._layer_uebernehmen()
            r = self._api("POST", self._instanz_pfad("load"),
                          {"renderTarget": self._ziel(), "graphicId": self.GRAFIK, "params": {"data": self._daten(e)}})
            self.instanz = r["graphicInstanceId"]
            self._api("POST", self._instanz_pfad("playAction"),
                      {"renderTarget": self._ziel(), "graphicInstanceId": self.instanz, "params": {"goto": 0}})
            self.auf_sendung, self.eintrag_auf_sendung, self.ein_seit = True, dict(e), time.time()
        return self.zustand()

    def umschalten(self):
        return self.aus() if self.auf_sendung else self.ein()

    def aus(self, sofort=False):
        with self.lock:
            if self.instanz and self.auf_sendung:
                self._api("POST", self._instanz_pfad("stopAction"),
                          {"renderTarget": self._ziel(), "graphicInstanceId": self.instanz,
                           "params": {"skipAnimation": sofort}})
            self.auf_sendung, self.eintrag_auf_sendung, self.ein_seit = False, None, None
        return self.zustand()

    def ein_und_weiter(self):
        """Ein, und die Auswahl rückt schon zum nächsten Eintrag vor (praktisch für Reihen von Gästen)."""
        with self.lock:
            z = self.ein()
            if self.frei is None and self.index is not None and self.index < len(self.liste) - 1:
                self.index += 1
                self.seite = self.index // SLOTS
                z = self.zustand()
        return z

    def auto_aus_setzen(self, sekunden):
        with self.lock:
            self.auto_aus = max(0, min(60, int(sekunden)))
        return self.zustand()

    def leeren(self):
        with self.lock:
            self._api("PUT", self._instanz_pfad("clear"), {"renderTarget": self._ziel()})
            self.instanz, self.auf_sendung, self.eintrag_auf_sendung, self.ein_seit = None, False, None, None
        return self.zustand()

    def zustand(self):
        seiten = max(1, -(-len(self.liste) // SLOTS))
        rest = None
        if self.auf_sendung and self.auto_aus and self.ein_seit:
            rest = max(0, round(self.auto_aus - (time.time() - self.ein_seit), 1))
        slots = self.liste[self.seite * SLOTS:(self.seite + 1) * SLOTS]
        return {"quelle": self.quelle, "kanton": self.kanton, "kategorie": self.kategorie,
                "liste": self.liste, "index": self.index, "frei": self.frei, "auswahl": self.aktueller_eintrag(),
                "auf_sendung": self.auf_sendung, "eintrag_auf_sendung": self.eintrag_auf_sendung,
                "auto_aus": self.auto_aus, "auto_aus_rest": rest,
                "seite": self.seite, "seiten": seiten,
                "slots": [{"slot": i + 1, "position": self.seite * SLOTS + i, "zeile1": e["zeile1"], "zeile2": e["zeile2"]}
                          for i, e in enumerate(slots)],
                "meldung": self.meldung, "renderer_verbunden": RENDERER.verbunden(),
                "jahr": ARGS.jahr, "sprache": ARGS.sprache, "layer": self.layer}

    def zeitgeber(self):
        """Auto-Aus und regelmässiges Nachladen der Liste (Grist-Änderungen)."""
        zuletzt = 0
        while True:
            time.sleep(0.25)
            try:
                if self.auf_sendung and self.auto_aus and self.ein_seit and time.time() - self.ein_seit >= self.auto_aus:
                    self.aus()
                if time.time() - zuletzt >= ARGS.intervall:
                    zuletzt = time.time()
                    self.liste_laden()
            except ServerFehler as e:
                self.meldung = e.meldung
            except Exception as e:   # Zeitgeber darf nie sterben
                self.meldung = str(e)


BAUCHBINDEN = None


# =============================================================================
# 5. Controller Hochrechnung Schweiz (mit Fortsetzen nach kurzfristigem Ausblenden)
# =============================================================================
def seiten_grenzen(anzahl, seiten, pro_seite=3):
    """Gleiche Seitenaufteilung wie graphic.mjs (_grenzen)."""
    g, i = [], 0
    for n in seiten:
        if i >= anzahl:
            break
        g.append((i, min(i + n, anzahl)))
        i += n
    while i < anzahl:
        g.append((i, min(i + pro_seite, anzahl)))
        i += pro_seite
    return g


class SchweizController(OgrafKlient):
    """Insert «Hochrechnung Schweiz». Beginnt mit der stärksten Partei. Wird mitten im Ablauf ausgeblendet,
    setzt die nächste Einblendung mit der Seite fort, die als Nächstes gekommen wäre."""

    GRAFIK = "wahlen2027-hochrechnung-schweiz"

    def __init__(self):
        self.layer = ARGS.layer
        self.lock = threading.RLock()
        self.daten = None
        self.meta = {}
        self.institut = ""
        self.seiten = [int(x) for x in (ARGS.seiten_schweiz or "").replace(" ", "").split(",") if x.isdigit()]
        self.instanz = None
        self.auf_sendung = False
        self.schritt = None
        self.fortsetzen = None      # {"schritt", "partei", "ansicht", "kennung"} – wo die nächste Einblendung beginnt
        self.meldung = ""
        self.zuletzt_gesendet = None

    # ---------- Daten ----------
    def daten_holen(self):
        a = wahlen_api("nr/schweiz-insert", jahr=ARGS.jahr, lang=ARGS.sprache, institut=self.institut or None)
        parteien = [{k: v for k, v in p.items() if v is not None and k in
                     ("kurz", "farbe", "sitze", "sitze_diff", "staerke", "staerke_diff", "staerke_diff_unsicher")} for p in a.get("daten", [])]
        for p in parteien:
            p["farbe"] = (p.get("farbe") or "#8a8a8a").lower()
        daten = {"titel": a.get("titel", ""), "untertitel": a.get("untertitel", ""), "kanton": "CH",
                 "mit_sitzen": bool(a.get("mit_sitzen")), "nachkommastellen": ARGS.nachkommastellen,
                 "pro_seite": 3, "seiten": list(self.seiten), "parteien": parteien}
        meta = {"modus": a.get("modus"), "institut": a.get("institut"), "hochrechnung_nr": a.get("hochrechnung_nr"),
                "zeitpunkt": a.get("zeitpunkt"), "wahl_abgeschlossen": a.get("wahl_abgeschlossen"), "stand": a.get("stand")}
        return daten, meta

    def _kennung(self, meta=None):
        m = meta if meta is not None else self.meta
        return f"{m.get('modus')}|{m.get('institut')}|{m.get('hochrechnung_nr')}"

    def _grenzen(self, daten=None):
        d = daten or self.daten
        return seiten_grenzen(len(d["parteien"]), d.get("seiten") or [], d.get("pro_seite", 3)) if d else []

    def _ansichten(self, daten=None):
        d = daten or self.daten
        return ["sitze", "prozent"] if d and d["mit_sitzen"] else ["prozent"]

    def schritte(self, daten=None):
        return len(self._grenzen(daten)) * len(self._ansichten(daten))

    def _seite_index(self, schritt):
        return schritt // len(self._ansichten())

    def _erster_schritt(self, seite_index):
        return seite_index * len(self._ansichten())

    def _schritt_info(self, schritt, daten=None):
        d = daten or self.daten
        a = self._ansichten(d)
        g = self._grenzen(d)
        seite = schritt // len(a)
        if not (0 <= seite < len(g)):
            return None
        return {"schritt": schritt, "seite": seite, "ansicht": a[schritt % len(a)],
                "partei": d["parteien"][g[seite][0]]["kurz"],
                "parteien": [p["kurz"] for p in d["parteien"][g[seite][0]:g[seite][1]]]}

    def _fortsetzen_merken(self, schritt):
        """Nach dem Ausblenden bei «schritt» beginnt die nächste Einblendung mit schritt+1 (am Ende: von vorne)."""
        n = (schritt + 1) if schritt is not None else 0
        if n >= self.schritte():
            n = 0
        info = self._schritt_info(n) if self.daten else None
        self.fortsetzen = {"schritt": n, "partei": info["partei"] if info else None,
                           "ansicht": info["ansicht"] if info else None, "kennung": self._kennung()}

    def _startschritt(self):
        """Startschritt für EIN, auch wenn sich die Daten inzwischen geändert haben."""
        f = self.fortsetzen
        if not f or f["schritt"] == 0:
            return 0
        if f["kennung"] != self._kennung():
            return 0                 # neue Hochrechnung (oder Resultat): wieder von vorne
        for s in range(self.schritte()):      # gleiche Seite (erste Partei) und Ansicht suchen
            i = self._schritt_info(s)
            if i and i["partei"] == f["partei"] and i["ansicht"] == f["ansicht"]:
                return s
        return f["schritt"] if f["schritt"] < self.schritte() else 0

    # ---------- Bedienung ----------
    def ein(self, ab_schritt=None):
        with self.lock:
            self.daten, self.meta = self.daten_holen()
            if not self.daten["parteien"]:
                raise ServerFehler(409, "Keine freigegebene Hochrechnung und kein Schlussresultat Schweiz")
            if self.auf_sendung:
                return self.zustand()
            start = self._startschritt() if ab_schritt is None else ab_schritt
            if not (0 <= start < self.schritte()):
                raise ServerFehler(400, f"Seite gibt es nicht ({start + 1})")
            self._layer_uebernehmen()
            r = self._api("POST", self._instanz_pfad("load"),
                          {"renderTarget": self._ziel(), "graphicId": self.GRAFIK, "params": {"data": self.daten}})
            self.instanz = r["graphicInstanceId"]
            r = self._api("POST", self._instanz_pfad("playAction"),
                          {"renderTarget": self._ziel(), "graphicInstanceId": self.instanz, "params": {"goto": start}})
            self.auf_sendung, self.schritt = True, r.get("currentStep", start)
            self.zuletzt_gesendet = json.dumps(self.daten, sort_keys=True)
            self.meldung = ""
        return self.zustand()

    def schritt_aktion(self, delta):
        with self.lock:
            if not self.auf_sendung or not self.instanz:
                raise ServerFehler(409, "Grafik ist nicht auf Sendung")
            r = self._api("POST", self._instanz_pfad("playAction"),
                          {"renderTarget": self._ziel(), "graphicInstanceId": self.instanz, "params": {"delta": delta}})
            self.schritt = r.get("currentStep")
            if self.schritt is None:      # durch: ausgeblendet, nächstes Mal von vorne
                self.auf_sendung = False
                self.fortsetzen = None
        return self.zustand()

    def seite(self, nummer):
        """Direkt zu Seite «nummer» (1-basiert): auf Sendung springen, sonst als nächster Start merken."""
        with self.lock:
            if not self.daten:
                self.daten, self.meta = self.daten_holen()
            s = self._erster_schritt(nummer - 1)
            if not (0 <= s < self.schritte()):
                raise ServerFehler(404, f"Seite {nummer} gibt es nicht")
            if self.auf_sendung and self.instanz:
                r = self._api("POST", self._instanz_pfad("playAction"),
                              {"renderTarget": self._ziel(), "graphicInstanceId": self.instanz, "params": {"goto": s}})
                self.schritt = r.get("currentStep", s)
            else:
                self._fortsetzen_merken(s - 1)
        return self.zustand()

    def von_vorne(self):
        with self.lock:
            self.fortsetzen = None
            if self.auf_sendung and self.instanz:
                r = self._api("POST", self._instanz_pfad("playAction"),
                              {"renderTarget": self._ziel(), "graphicInstanceId": self.instanz, "params": {"goto": 0}})
                self.schritt = r.get("currentStep", 0)
        return self.zustand()

    def aus(self, sofort=False):
        with self.lock:
            if self.instanz and self.auf_sendung:
                self._fortsetzen_merken(self.schritt)
                self._api("POST", self._instanz_pfad("stopAction"),
                          {"renderTarget": self._ziel(), "graphicInstanceId": self.instanz,
                           "params": {"skipAnimation": sofort}})
            self.auf_sendung, self.schritt = False, None
        return self.zustand()

    def leeren(self):
        with self.lock:
            if self.auf_sendung:
                self._fortsetzen_merken(self.schritt)
            self._api("PUT", self._instanz_pfad("clear"), {"renderTarget": self._ziel()})
            self.instanz, self.auf_sendung, self.schritt = None, False, None
        return self.zustand()

    def aktualisieren(self, nur_bei_aenderung=False):
        with self.lock:
            daten, meta = self.daten_holen()
            neu = json.dumps(daten, sort_keys=True)
            alt_kennung = self._kennung()
            self.daten, self.meta = daten, meta
            if self.auf_sendung and self.instanz and (not nur_bei_aenderung or neu != self.zuletzt_gesendet):
                r = self._api("POST", self._instanz_pfad("updateAction"),
                              {"renderTarget": self._ziel(), "graphicInstanceId": self.instanz, "params": {"data": daten}})
                self.zuletzt_gesendet = neu
                if self._kennung() != alt_kennung:
                    self.meldung = "Neue Hochrechnung auf Sendung übernommen"
            elif not self.auf_sendung and self.fortsetzen and self.fortsetzen["kennung"] != self._kennung():
                self.fortsetzen = None
                self.meldung = "Neue Hochrechnung: nächste Einblendung beginnt von vorne"
        return self.zustand()

    def seiten_setzen(self, text):
        with self.lock:
            self.seiten = [int(x) for x in (text or "").replace(" ", "").split(",") if x.isdigit() and 1 <= int(x) <= 3]
            if self.daten:
                self.daten["seiten"] = list(self.seiten)
        return self.aktualisieren()

    def institut_setzen(self, institut):
        with self.lock:
            self.institut = institut or ""
            self.fortsetzen = None
        return self.aktualisieren()

    def zustand(self):
        seitenliste = []
        if self.daten:
            for i, (a, b) in enumerate(self._grenzen()):
                seitenliste.append({"seite": i + 1, "parteien": [p["kurz"] for p in self.daten["parteien"][a:b]]})
        start = None
        if self.daten and not self.auf_sendung:
            try:
                si = self._schritt_info(self._startschritt())
                start = {"schritt": si["schritt"], "seite": si["seite"] + 1, "ansicht": si["ansicht"],
                         "parteien": si["parteien"]} if si else None
            except Exception:
                start = None
        return {"auf_sendung": self.auf_sendung, "schritt": self.schritt, "schritte_total": self.schritte(),
                "seite_aktuell": (self._seite_index(self.schritt) + 1) if self.schritt is not None else None,
                "naechster_start": start, "fortsetzen": self.fortsetzen,
                "seiten": seitenliste, "seiten_einstellung": ",".join(map(str, self.seiten)),
                "institut": self.institut, "daten": self.daten, "meta": self.meta, "meldung": self.meldung,
                "renderer_verbunden": RENDERER.verbunden(), "jahr": ARGS.jahr, "sprache": ARGS.sprache, "layer": self.layer}

    def auto_aktualisieren(self):
        while True:
            time.sleep(ARGS.intervall)
            try:
                self.aktualisieren(nur_bei_aenderung=True)
            except ServerFehler as e:
                self.meldung = e.meldung
            except Exception as e:
                self.meldung = str(e)


SCHWEIZ = None


class NationalController(SchweizController):
    """Videowand «Hochrechnung National»: ein Schritt pro Partei, Reihenfolge nach Stärke der letzten Wahl.
    Läuft auf dem Renderer «wand». Fortsetzen nach Ausblenden wie bei der Schweiz (mit der nächsten Partei)."""

    GRAFIK = "wahlen2027-hochrechnung-national"

    def __init__(self):
        super().__init__()
        self.renderer_id = "wand"
        self.layer = ARGS.layer_wand
        self.seiten = [int(x) for x in (ARGS.seiten_national or "").replace(" ", "").split(",") if x.isdigit()]

    def daten_holen(self):
        a = wahlen_api("nr/schweiz-insert", jahr=ARGS.jahr, lang=ARGS.sprache, institut=self.institut or None, sort="vorwahl")
        parteien = [{k: v for k, v in p.items() if v is not None and k in
                     ("kurz", "farbe", "staerke", "staerke_diff", "staerke_diff_unsicher")} for p in a.get("daten", [])]
        for p in parteien:
            p["farbe"] = (p.get("farbe") or "#8a8a8a").lower()
        titel = {"de": "Nationalrat", "fr": "Conseil national", "it": "Consiglio nazionale"}[ARGS.sprache]
        art = (a.get("titel") or "Hochrechnung").split(" ")[0]
        daten = {"titel": f"{art} {titel}", "flagge": True, "nachkommastellen": ARGS.nachkommastellen,
                 "pro_seite": 6, "seiten": list(self.seiten), "parteien": parteien}
        meta = {"modus": a.get("modus"), "institut": a.get("institut"), "hochrechnung_nr": a.get("hochrechnung_nr"),
                "zeitpunkt": a.get("zeitpunkt"), "wahl_abgeschlossen": a.get("wahl_abgeschlossen"), "stand": a.get("stand")}
        return daten, meta

    def _grenzen(self, daten=None):
        d = daten or self.daten
        return seiten_grenzen(len(d["parteien"]), d.get("seiten") or [], 6) if d else []

    def _ansichten(self, daten=None):
        return ["balken"]

    def schritte(self, daten=None):
        d = daten or self.daten
        return len(d["parteien"]) if d else 0

    def _seite_index(self, schritt):
        for i, (a, b) in enumerate(self._grenzen()):
            if a <= schritt < b:
                return i
        return 0

    def _erster_schritt(self, seite_index):
        g = self._grenzen()
        return g[seite_index][0] if 0 <= seite_index < len(g) else -1

    def _schritt_info(self, schritt, daten=None):
        d = daten or self.daten
        if not d or not (0 <= schritt < len(d["parteien"])):
            return None
        g = self._grenzen(d)
        seite = next((i for i, (a, b) in enumerate(g) if a <= schritt < b), 0)
        a, b = g[seite]
        return {"schritt": schritt, "seite": seite, "ansicht": "balken", "partei": d["parteien"][schritt]["kurz"],
                "parteien": [p["kurz"] for p in d["parteien"][a:b]]}

    def seiten_setzen(self, text):
        with self.lock:
            self.seiten = [int(x) for x in (text or "").replace(" ", "").split(",") if x.isdigit() and 1 <= int(x) <= 6]
            if self.daten:
                self.daten["seiten"] = list(self.seiten)
        return self.aktualisieren()

    def zustand(self):
        z = super().zustand()
        z["partei_aktuell"] = (self.daten["parteien"][self.schritt]["kurz"]
                               if self.auf_sendung and self.daten and self.schritt is not None
                               and self.schritt < len(self.daten["parteien"]) else None)
        z["renderer_verbunden"] = RENDERERS["wand"].verbunden()
        z["renderer"] = "wand"
        return z


class BeteiligungController(OgrafKlient):
    """Videowand «Wahlbeteiligung»: Ring mit dem Schweizer Wert (Hochrechnung > Resultat > Zwischenstand).
    Läuft auf dem Renderer «wand», teilt sich den Layer mit Videowand National (der andere blendet zuerst aus)."""

    GRAFIK = "wahlen2027-wahlbeteiligung"
    FEHLT = "Noch keine Wahlbeteiligung vorhanden"

    def _bereit(self):
        return self.daten.get("wert") is not None

    def __init__(self):
        self.renderer_id = "wand"
        self.layer = ARGS.layer_wand
        self.lock = threading.RLock()
        self.daten, self.meta = None, {}
        self.instanz = None
        self.auf_sendung = False
        self.meldung = ""
        self.zuletzt_gesendet = None

    def daten_holen(self):
        a = wahlen_api("beteiligung/schweiz", jahr=ARGS.jahr, lang=ARGS.sprache)
        z = (a.get("daten") or [{}])[0]
        wert = z.get("wert")
        titel = {"de": "Wahlbeteiligung", "fr": "Participation", "it": "Partecipazione"}[ARGS.sprache]
        daten = {"titel": titel, "flagge": True, "nachkommastellen": ARGS.nachkommastellen, "untertitel": ""}
        if wert is not None:
            daten["wert"] = wert
        meta = {"modus": a.get("modus"), "institut": a.get("institut"), "hochrechnung_nr": a.get("hochrechnung_nr"),
                "zeitpunkt": a.get("zeitpunkt"), "vorwahl": z.get("vorwahl"), "diff": z.get("diff"), "stand": a.get("stand")}
        return daten, meta

    def ein(self):
        with self.lock:
            self.daten, self.meta = self.daten_holen()
            if not self._bereit():
                raise ServerFehler(409, self.FEHLT)
            if self.auf_sendung:
                return self.zustand()
            self._layer_uebernehmen()
            r = self._api("POST", self._instanz_pfad("load"),
                          {"renderTarget": self._ziel(), "graphicId": self.GRAFIK, "params": {"data": self.daten}})
            self.instanz = r["graphicInstanceId"]
            self._api("POST", self._instanz_pfad("playAction"),
                      {"renderTarget": self._ziel(), "graphicInstanceId": self.instanz, "params": {"goto": 0}})
            self.auf_sendung = True
            self.zuletzt_gesendet = json.dumps(self.daten, sort_keys=True)
        return self.zustand()

    def aus(self, sofort=False):
        with self.lock:
            if self.instanz and self.auf_sendung:
                self._api("POST", self._instanz_pfad("stopAction"),
                          {"renderTarget": self._ziel(), "graphicInstanceId": self.instanz,
                           "params": {"skipAnimation": sofort}})
            self.auf_sendung = False
        return self.zustand()

    def aktualisieren(self, nur_bei_aenderung=False):
        with self.lock:
            self.daten, self.meta = self.daten_holen()
            neu = json.dumps(self.daten, sort_keys=True)
            if self.auf_sendung and self.instanz and (not nur_bei_aenderung or neu != self.zuletzt_gesendet):
                self._api("POST", self._instanz_pfad("updateAction"),
                          {"renderTarget": self._ziel(), "graphicInstanceId": self.instanz, "params": {"data": self.daten}})
                self.zuletzt_gesendet = neu
        return self.zustand()

    def leeren(self):
        with self.lock:
            self._api("PUT", self._instanz_pfad("clear"), {"renderTarget": self._ziel()})
            self.instanz, self.auf_sendung = None, False
        return self.zustand()

    def zustand(self):
        return {"auf_sendung": self.auf_sendung, "daten": self.daten, "meta": self.meta, "meldung": self.meldung,
                "renderer_verbunden": RENDERERS["wand"].verbunden(), "renderer": "wand", "jahr": ARGS.jahr}

    def auto_aktualisieren(self):
        while True:
            time.sleep(ARGS.intervall)
            try:
                if self.auf_sendung:
                    self.aktualisieren(nur_bei_aenderung=True)
            except ServerFehler as e:
                self.meldung = e.meldung


class AuszaehlungController(BeteiligungController):
    """Videowand «Auszählungsstand Nationalrat»: Schweizer Karte, Kantone nach Status (Resultat / Hochrechnung / keines).
    Gleiche Bedienung wie die Wahlbeteiligung (Renderer «wand», teilt den Layer)."""

    GRAFIK = "wahlen2027-auszaehlungsstand"
    FEHLT = "Noch keine Kantonsdaten vorhanden"
    TEXTE = {"de": ("Auszählungsstand Nationalrat", "Resultat", "Hochrechnung", "Kein Resultat"),
             "fr": ("État du dépouillement Conseil national", "Résultat", "Projection", "Pas de résultat"),
             "it": ("Stato dello spoglio Consiglio nazionale", "Risultato", "Proiezione", "Nessun risultato")}

    def _bereit(self):
        return bool(self.daten.get("kantone"))

    def daten_holen(self):
        a = wahlen_api("auszaehlung/nr", jahr=ARGS.jahr, lang=ARGS.sprache)
        titel, r, h, k = self.TEXTE[ARGS.sprache]
        kantone = [{"kanton": x["kanton"], "status": x["status"]} for x in a.get("daten", [])]
        daten = {"titel": titel, "flagge": True, "legende_resultat": r, "legende_hochrechnung": h,
                 "legende_keines": k, "kantone": kantone}
        meta = {"zaehler": a.get("zaehler"), "stand": a.get("stand")}
        return daten, meta


NATIONAL = None
BETEILIGUNG = None
AUSZAEHLUNG = None


def stream_deck_wert(name):
    """Kurze Textwerte für Stream-Deck-Tasten (Companion: Variablen, Beschriftung und Farb-Rückmeldung)."""
    k, c, b = CONTROLLER, SCHWEIZ, BAUCHBINDEN
    an = lambda x: "1" if x else "0"
    if name == "kt_kanton":
        return k.kanton or ""
    if name == "kt_onair":
        return an(k.auf_sendung)
    if name == "kt_onair_kanton":
        return (k.kanton or "") if k.auf_sendung else ""
    # Hochrechnung Schweiz (ch_…) und Videowand National (nat_…) haben dieselben Werte
    for vorsilbe, ctl in (("ch_", c), ("nat_", NATIONAL)):
        if not name.startswith(vorsilbe):
            continue
        kurz = name[len(vorsilbe):]
        if kurz == "onair":
            return an(ctl.auf_sendung)
        z = ctl.zustand()
        if kurz == "seite_onair":
            return str(z["seite_aktuell"]) if z["auf_sendung"] and z["seite_aktuell"] else ""
        if kurz == "seite_naechste":
            return str(z["naechster_start"]["seite"]) if not z["auf_sendung"] and z["naechster_start"] else ""
        if kurz == "anzeige":
            national = vorsilbe == "nat_"
            if z["auf_sendung"]:
                return f"ON AIR\n{z.get('partei_aktuell') or ''}" if national else f"ON AIR\nSeite {z['seite_aktuell']}"
            ns = z["naechster_start"]
            if not ns:
                return "BEREIT"
            if national and z["daten"]:
                return f"BEREIT\nab {z['daten']['parteien'][ns['schritt']]['kurz']}"
            return f"BEREIT\nab Seite {ns['seite']}"
        m = re.fullmatch(r"seite_(\d+)", kurz)
        if m:
            i = int(m.group(1)) - 1
            return " ".join(z["seiten"][i]["parteien"]) if 0 <= i < len(z["seiten"]) else ""
    if name == "az_onair":
        return an(AUSZAEHLUNG.auf_sendung)
    if name == "az_anzeige":
        zl = ((AUSZAEHLUNG.meta or {}).get("zaehler") or {})
        if AUSZAEHLUNG.auf_sendung:
            return f"ON AIR\n{zl.get('resultat', 0)} / {zl.get('hochrechnung', 0)} / {zl.get('keines', 0)}"
        return "BEREIT" if (AUSZAEHLUNG.daten or {}).get("kantone") else "KEINE DATEN"
    if name == "wb_onair":
        return an(BETEILIGUNG.auf_sendung)
    if name == "wb_anzeige":
        if BETEILIGUNG.auf_sendung:
            w = (BETEILIGUNG.daten or {}).get("wert")
            return "ON AIR\n" + (f"{w:.1f}%" if w is not None else "")
        w = (BETEILIGUNG.meta or {}).get("modus")
        return "BEREIT" if (BETEILIGUNG.daten or {}).get("wert") is not None else "KEIN WERT"
    if name == "bb_onair":
        return an(b.auf_sendung)
    if name == "bb_seite":
        return f"{b.seite + 1}/{max(1, -(-len(b.liste) // SLOTS))}"
    if name == "bb_auto":
        return f"{b.auto_aus} s" if b.auto_aus else "aus"
    if name == "bb_slot_auswahl":
        i = b.index
        return str(i - b.seite * SLOTS + 1) if (b.frei is None and i is not None and b.seite * SLOTS <= i < (b.seite + 1) * SLOTS) else ""
    if name == "bb_slot_onair":
        if not (b.auf_sendung and b.eintrag_auf_sendung):
            return ""
        for n, e in enumerate(b.liste[b.seite * SLOTS:(b.seite + 1) * SLOTS]):
            if e["id"] == b.eintrag_auf_sendung["id"]:
                return str(n + 1)
        return ""
    m = re.fullmatch(r"bb_slot_(\d+)", name)
    if m:
        i = b.seite * SLOTS + int(m.group(1)) - 1
        return b.liste[i]["zeile1"] if 0 <= i < len(b.liste) else ""
    raise ServerFehler(404, f"Unbekannter Wert: {name}")


# =============================================================================
# CasparCG-Wächter: CasparCG spielt die Renderer-Seiten im HTML-Producer und gibt sie per DeckLink aus
# (Key/Fill an den Mischer, Fill an die Videowand). Gesteuert wird weiterhin alles über diesen Server –
# an CasparCG geht nur «PLAY <Kanal-Layer> [HTML] <Renderer-Adresse>»: beim Start, nach einem Neustart
# von CasparCG und wenn die CasparCG-Seite nicht (mehr) verbunden ist.
# =============================================================================
class CasparWaechter:
    PRUEF_INTERVALL = 5        # s zwischen Lebenszeichen an CasparCG
    WARTEN_AUF_SEITE = 15      # s nach PLAY, bis die Seite verbunden sein muss
    MIN_ABSTAND_NEU = 30       # s zwischen zwei automatischen Neuladungen derselben Seite

    def __init__(self, adresse, ziele, url_basis):
        host, _, port = adresse.partition(":")
        self.host, self.port = host or "127.0.0.1", int(port or 5250)
        self.ziele = {rid: kl for rid, kl in ziele.items() if kl}    # renderer-id -> «1-10»
        self.url_basis = url_basis.rstrip("/")
        self.sock, self.puffer = None, b""
        self.lock = threading.Lock()
        self.verbunden, self.version, self.meldung = False, None, "startet …"
        self.letztes_play = {}     # renderer-id -> Zeitpunkt
        self.protokoll = []        # letzte Ereignisse für die Menü-Seite

    def _log(self, text):
        print(f"CasparCG: {text}")
        self.protokoll = (self.protokoll + [f"{time.strftime('%H:%M:%S')} {text}"])[-8:]

    # ---- AMCP (Zeilenprotokoll über TCP) ----
    def _zeile(self):
        while b"\r\n" not in self.puffer:
            teil = self.sock.recv(4096)
            if not teil:
                raise ConnectionError("Verbindung von CasparCG geschlossen")
            self.puffer += teil
        zeile, self.puffer = self.puffer.split(b"\r\n", 1)
        return zeile.decode("utf-8", "replace")

    def befehl(self, text):
        """Schickt einen AMCP-Befehl, gibt (Code, Zeilen) zurück. 201 = eine Datenzeile, 200 = bis Leerzeile."""
        with self.lock:
            if not self.sock:
                raise ConnectionError("nicht verbunden")
            self.sock.sendall((text + "\r\n").encode("utf-8"))
            erste = self._zeile()
            code = int(erste[:3]) if erste[:3].isdigit() else 0
            daten = []
            if code == 201:
                daten.append(self._zeile())
            elif code == 200:
                while True:
                    z = self._zeile()
                    if z == "":
                        break
                    daten.append(z)
            return code, [erste] + daten

    def _verbinden(self):
        s = socket.create_connection((self.host, self.port), timeout=5)
        s.settimeout(10)
        self.sock, self.puffer = s, b""
        code, z = self.befehl("VERSION")
        self.version = z[1] if code == 201 and len(z) > 1 else None
        self.verbunden = True
        self._log(f"verbunden mit {self.host}:{self.port}" + (f" (Version {self.version})" if self.version else ""))

    def _trennen(self, grund):
        if self.verbunden:
            self._log(f"Verbindung weg: {grund}")
        self.verbunden = False
        try:
            if self.sock:
                self.sock.close()
        except OSError:
            pass
        self.sock = None

    def url(self, rid):
        pfad = "/renderer" if rid == "haupt" else f"/renderer/{rid}"
        return f"{self.url_basis}{pfad}?quelle=casparcg"

    def seite_laden(self, rid, grund):
        kl = self.ziele[rid]
        code, z = self.befehl(f'PLAY {kl} [HTML] "{self.url(rid)}"')
        self.letztes_play[rid] = time.time()
        if code in (200, 201, 202):
            self._log(f"Kanal {kl}: Renderer «{rid}» geladen ({grund})")
        else:
            self._log(f"Kanal {kl}: PLAY abgelehnt – {z[0]}")
            self.meldung = f"PLAY auf {kl} abgelehnt: {z[0]}"

    def alle_neu_laden(self, grund="von Hand"):
        for rid in self.ziele:
            self.seite_laden(rid, grund)

    def schleife(self):
        while True:
            try:
                if not self.verbunden:
                    self._verbinden()
                    self.alle_neu_laden("Start bzw. CasparCG neu gestartet")
                    self.meldung = ""
                else:
                    self.befehl("VERSION")      # Lebenszeichen; bricht ab, wenn CasparCG weg ist
                jetzt = time.time()
                for rid in self.ziele:
                    if RENDERERS[rid].verbunden_mit("casparcg"):
                        continue
                    seit = jetzt - self.letztes_play.get(rid, 0)
                    if seit > max(self.WARTEN_AUF_SEITE, self.MIN_ABSTAND_NEU):
                        self.seite_laden(rid, "Seite war nicht verbunden")
                self.meldung = "" if all(RENDERERS[r].verbunden_mit("casparcg") for r in self.ziele) \
                    else "warte auf Renderer-Seite in CasparCG …"
            except (OSError, ConnectionError, ValueError) as e:
                self._trennen(e)
                self.meldung = f"CasparCG nicht erreichbar ({self.host}:{self.port})"
            time.sleep(self.PRUEF_INTERVALL)

    def zustand(self):
        return {"aktiv": True, "verbunden": self.verbunden, "version": self.version, "meldung": self.meldung,
                "adresse": f"{self.host}:{self.port}", "protokoll": self.protokoll,
                "kanaele": {rid: {"kanal": kl, "seite_verbunden": RENDERERS[rid].verbunden_mit("casparcg")}
                            for rid, kl in self.ziele.items()}}


CASPAR = None


def system_zustand():
    """Überblick für die Menü-Seite: Renderer, Daten-API, Grist-Abgleich, was auf Sendung ist."""
    api = {"erreichbar": False}
    try:
        a = wahlen_api("status", jahr=ARGS.jahr)
        api = {"erreichbar": True, "letzter_grist_abgleich": a.get("letzter_grist_abgleich"), "stand": a.get("stand")}
    except ServerFehler as e:
        api["fehler"] = e.meldung
    k, c, b = CONTROLLER, SCHWEIZ, BAUCHBINDEN
    return {
        "jahr": ARGS.jahr, "sprache": ARGS.sprache, "zeit": time.strftime("%H:%M:%S"),
        "renderer": {"verbunden": RENDERER.verbunden(), "anzahl": len(RENDERER.verbindungen)},
        "renderer_wand": {"verbunden": RENDERERS["wand"].verbunden(), "anzahl": len(RENDERERS["wand"].verbindungen)},
        "wahlen_api": api,
        "casparcg": CASPAR.zustand() if CASPAR else {"aktiv": False},
        "grafiken": sorted(grafiken()),
        "auf_sendung": {
            "kanton": {"an": k.auf_sendung, "text": k.kanton if k.auf_sendung else None, "layer": k.layer},
            "schweiz": {"an": c.auf_sendung, "text": (f"Seite {c._seite_index(c.schritt) + 1}"
                                                     if c.auf_sendung and c.schritt is not None else None), "layer": c.layer},
            "national": {"an": NATIONAL.auf_sendung, "text": (NATIONAL.zustand().get("partei_aktuell")
                                                               if NATIONAL.auf_sendung else None), "layer": NATIONAL.layer},
            "beteiligung": {"an": BETEILIGUNG.auf_sendung, "text": ((BETEILIGUNG.daten or {}).get("wert")
                            if BETEILIGUNG.auf_sendung else None), "layer": BETEILIGUNG.layer},
            "auszaehlung": {"an": AUSZAEHLUNG.auf_sendung, "text": None, "layer": AUSZAEHLUNG.layer},
            "bauchbinde": {"an": b.auf_sendung, "text": (b.eintrag_auf_sendung or {}).get("zeile1") if b.auf_sendung else None,
                           "layer": b.layer},
        },
    }


# =============================================================================
# HTTP
# =============================================================================
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "GrafikServer/1.0"

    def log_message(self, fmt, *a):
        if ARGS.log:
            sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % a))

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, HEAD, OPTIONS, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
        self.send_header("Access-Control-Max-Age", "3600")

    def _json(self, code, daten):
        body = json.dumps(daten, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _fehler(self, code, meldung):
        # Fehlerformat der OGraf Server API (RFC 7807)
        self._json(code, {"type": "about:blank", "title": meldung, "status": code})

    def _datei(self, pfad):
        typen = {".html": "text/html; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
                 ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
                 ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp",
                 ".woff2": "font/woff2", ".woff": "font/woff", ".otf": "font/otf", ".ttf": "font/ttf", ".css": "text/css"}
        try:
            with open(pfad, "rb") as f:
                body = f.read()
        except OSError:
            return self._fehler(404, "Datei nicht gefunden")
        self.send_response(200)
        self.send_header("Content-Type", typen.get(os.path.splitext(pfad)[1].lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n))
        except ValueError:
            raise ServerFehler(400, "Ungültiges JSON")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_PUT(self):
        self._route("PUT")

    def _route(self, methode):
        url = urllib.parse.urlsplit(self.path)
        pfad = url.path
        query = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query).items()}
        try:
            # --- oGraf-Server-API ---
            if pfad == API_PREFIX or pfad.startswith(API_PREFIX + "/"):
                body = self._body() if methode in ("POST", "PUT") else {}
                code, daten = ograf_api(methode, pfad[len(API_PREFIX):], query, body)
                return self._json(code, daten)
            # --- Renderer ---
            if pfad in ("/renderer", "/renderer/wand") and methode == "GET":
                return self._datei(os.path.join(HIER, "renderer.html"))
            if pfad == "/renderer/ereignisse" and methode == "GET":
                rid = query.get("renderer", "haupt")
                if rid not in RENDERERS:
                    return self._fehler(404, f"Renderer {rid} unbekannt")
                return self._sse(rid, (query.get("quelle") or "")[:30])
            if pfad.startswith("/renderer/antwort/") and methode == "POST":
                daten = self._body()
                for R in RENDERERS.values():
                    R.antwort(pfad.rsplit("/", 1)[1], daten)
                return self._json(200, {"ok": True})
            # --- Grafik-Dateien (Komponenten-Ordner) ---
            if pfad.startswith("/grafiken/") and methode == "GET":
                rel = urllib.parse.unquote(pfad[len("/grafiken/"):])
                ziel = os.path.realpath(os.path.join(ARGS.komponenten, rel))
                if not ziel.startswith(os.path.realpath(ARGS.komponenten) + os.sep):
                    return self._fehler(403, "Verboten")
                return self._datei(ziel)
            # --- Controller ---
            if pfad in ("/", "/menu", "/controller/menu") and methode == "GET":
                return self._datei(os.path.join(HIER, "menu.html"))
            if pfad == "/controller/api/system" and methode in ("GET", "POST"):
                return self._json(200, system_zustand())
            if pfad in ("/controller", "/controller/kanton") and methode == "GET":
                return self._datei(os.path.join(HIER, "controller.html"))
            if pfad == "/recherche" and methode == "GET":
                return self._datei(os.path.join(HIER, "recherche.html"))
            if pfad.startswith("/recherche/api/") and methode == "GET":
                teil = pfad[len("/recherche/api/"):].strip("/")
                if teil not in ("mitglieder", "parteistaerke", "optionen"):
                    raise ServerFehler(404, f"Unbekannte Recherche: {teil}")
                return self._json(200, wahlen_api("historie/" + teil, **{"jahr": ARGS.jahr, **query}))
            if pfad == "/controller/auszaehlung" and methode == "GET":
                return self._datei(os.path.join(HIER, "controller_auszaehlung.html"))
            if pfad == "/controller/beteiligung" and methode == "GET":
                return self._datei(os.path.join(HIER, "controller_beteiligung.html"))
            if pfad == "/controller/national" and methode == "GET":
                return self._datei(os.path.join(HIER, "controller_national.html"))
            if pfad in ("/sd/caspar/neu", "/controller/api/caspar/neu"):
                if not CASPAR:
                    raise ServerFehler(409, "CasparCG ist nicht eingerichtet (--casparcg)")
                CASPAR.alle_neu_laden("von Hand")
                return self._json(200, CASPAR.zustand())
            if pfad in ("/sd/caspar/status", "/controller/api/caspar/status"):
                return self._json(200, CASPAR.zustand() if CASPAR else {"aktiv": False})
            if pfad.startswith("/sd/az/") or pfad.startswith("/controller/api/az/"):
                rest = pfad[len("/sd/az/"):] if pfad.startswith("/sd/az/") else pfad[len("/controller/api/az/"):]
                return self._steuerung_wb(rest.strip("/"), AUSZAEHLUNG, "az")
            if pfad.startswith("/sd/wb/") or pfad.startswith("/controller/api/wb/"):
                rest = pfad[len("/sd/wb/"):] if pfad.startswith("/sd/wb/") else pfad[len("/controller/api/wb/"):]
                return self._steuerung_wb(rest.strip("/"))
            if pfad.startswith("/sd/nat/") or pfad.startswith("/controller/api/nat/"):
                rest = pfad[len("/sd/nat/"):] if pfad.startswith("/sd/nat/") else pfad[len("/controller/api/nat/"):]
                body = self._body() if methode == "POST" else {}
                return self._steuerung_ch(rest, {**query, **{k: str(v) for k, v in body.items()}}, NATIONAL, "nat")
            if pfad == "/controller/schweiz" and methode == "GET":
                return self._datei(os.path.join(HIER, "controller_schweiz.html"))
            if pfad.startswith("/sd/ch/") or pfad.startswith("/controller/api/ch/"):
                rest = pfad[len("/sd/ch/"):] if pfad.startswith("/sd/ch/") else pfad[len("/controller/api/ch/"):]
                body = self._body() if methode == "POST" else {}
                return self._steuerung_ch(rest, {**query, **{k: str(v) for k, v in body.items()}})
            if pfad == "/controller/bauchbinden" and methode == "GET":
                return self._datei(os.path.join(HIER, "controller_bauchbinden.html"))
            if pfad.startswith("/sd/wert/") and methode == "GET":
                return self._text(stream_deck_wert(pfad[len("/sd/wert/"):]))
            if pfad.startswith("/sd/bb/") or pfad.startswith("/controller/api/bb/"):
                rest = pfad[len("/sd/bb/"):] if pfad.startswith("/sd/bb/") else pfad[len("/controller/api/bb/"):]
                body = self._body() if methode == "POST" else {}
                return self._steuerung_bb(rest, {**query, **{k: str(v) for k, v in body.items()}})
            if pfad.startswith("/sd/") or pfad.startswith("/controller/api/"):
                return self._steuerung(pfad.split("/", 3)[-1] if pfad.startswith("/controller/api/") else pfad[4:], query)
            return self._fehler(404, "Nicht gefunden")
        except ServerFehler as e:
            return self._fehler(e.code, e.meldung)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _steuerung(self, befehl, query):
        """Gleiche Befehle für Web-Controller (/controller/api/...) und Stream Deck (/sd/...), GET oder POST."""
        c = CONTROLLER
        teile = befehl.strip("/").split("/")
        if teile[0] == "kanton" and len(teile) == 2:
            z = c.waehlen(teile[1])
        elif teile[0] == "ein":
            z = c.ein()
        elif teile[0] == "weiter":
            z = c.schritt_aktion(1)
        elif teile[0] == "zurueck":
            z = c.schritt_aktion(-1)
        elif teile[0] == "aus":
            z = c.aus(sofort=query.get("sofort") == "1")
        elif teile[0] == "neu":
            z = c.aktualisieren()
        elif teile[0] == "leeren":
            z = c.leeren()
        elif teile[0] in ("status", "zustand"):
            z = c.zustand()
        else:
            raise ServerFehler(404, f"Unbekannter Befehl: {befehl}")
        if teile[0] == "status" and query.get("format") == "text":
            # Kurzform für Stream-Deck-Anzeigen
            txt = f"{z['kanton'] or '-'} {'ON AIR' if z['auf_sendung'] else 'aus'}"
            body = txt.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            return self.wfile.write(body)
        return self._json(200, z)

    def _text(self, txt):
        body = txt.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _steuerung_ch(self, befehl, query, c=None, kuerzel="ch"):
        """Hochrechnung Schweiz (/controller/api/ch/..., /sd/ch/...) und Videowand National (…/nat/...)."""
        c = c or SCHWEIZ
        t = befehl.strip("/").split("/")
        b, arg = t[0], (t[1] if len(t) > 1 else None)
        if b == "ein":
            z = c.ein()
        elif b == "weiter":
            z = c.schritt_aktion(1)
        elif b == "zurueck":
            z = c.schritt_aktion(-1)
        elif b == "aus":
            z = c.aus(sofort=query.get("sofort") == "1")
        elif b == "vonvorne":
            z = c.von_vorne()
        elif b == "seite" and arg and arg.isdigit():
            z = c.seite(int(arg))
            if query.get("ein") == "1" and not z["auf_sendung"]:
                z = c.ein()
        elif b == "neu":
            z = c.aktualisieren()
        elif b == "leeren":
            z = c.leeren()
        elif b == "seiten":
            z = c.seiten_setzen(query.get("wert", arg or ""))
        elif b == "institut":
            z = c.institut_setzen(urllib.parse.unquote(arg or query.get("institut", "")))
        elif b in ("status", "zustand"):
            z = c.zustand()
        else:
            raise ServerFehler(404, f"Unbekannter Befehl: {kuerzel}/{befehl}")
        if b == "status" and query.get("format") == "text":
            if z["auf_sendung"]:
                return self._text(f"ON AIR\nSeite {z['seite_aktuell']}")
            n = z["naechster_start"]
            return self._text(f"bereit\nab Seite {n['seite']}" if n else "bereit")
        return self._json(200, z)

    def _steuerung_wb(self, b, c=None, kuerzel="wb"):
        c = c or BETEILIGUNG
        if b == "ein":
            z = c.ein()
        elif b == "aus":
            z = c.aus()
        elif b == "umschalten":
            z = c.aus() if c.auf_sendung else c.ein()
        elif b == "neu":
            z = c.aktualisieren()
        elif b == "leeren":
            z = c.leeren()
        elif b in ("status", "zustand"):
            z = c.zustand()
        else:
            raise ServerFehler(404, f"Unbekannter Befehl: {kuerzel}/{b}")
        return self._json(200, z)

    def _steuerung_bb(self, befehl, query):
        """Bauchbinden: gleiche Befehle für Web-Controller (/controller/api/bb/...) und Stream Deck (/sd/bb/...)."""
        c = BAUCHBINDEN
        t = befehl.strip("/").split("/")
        b, arg = t[0], (t[1] if len(t) > 1 else None)
        zahl = lambda x: int(x) if x is not None and x.lstrip("-").isdigit() else None
        if b == "ein":
            z = c.ein()
        elif b == "aus":
            z = c.aus(sofort=query.get("sofort") == "1")
        elif b == "umschalten":
            z = c.umschalten()
        elif b == "ein-weiter":
            z = c.ein_und_weiter()
        elif b == "naechste":
            z = c.bewegen(1)
        elif b == "vorherige":
            z = c.bewegen(-1)
        elif b == "slottext" and zahl(arg):
            # Beschriftung einer Stream-Deck-Taste (Companion: Variable aus HTTP-Antwort)
            i = c.seite * SLOTS + zahl(arg) - 1
            e = c.liste[i] if 0 <= i < len(c.liste) else None
            mark = "▶ " if e and c.index == i and not c.frei else ""
            return self._text(f"{mark}{e['zeile1']}" if e else "")
        elif b == "slot" and zahl(arg):
            z = c.slot(zahl(arg), sofort_ein=query.get("ein") == "1")
        elif b == "waehle" and zahl(arg) is not None:
            z = c.waehlen(zahl(arg), sofort_ein=query.get("ein") == "1")
        elif b == "seite" and arg in ("vor", "zurueck"):
            z = c.seite_wechseln(1 if arg == "vor" else -1)
        elif b == "quelle" and arg:
            z = c.quelle_setzen(arg, query.get("kanton") or (t[2] if len(t) > 2 else None))
        elif b == "kanton" and arg:
            z = c.quelle_setzen(c.quelle if c.quelle != "grist" else "nr", arg)
        elif b == "kategorie":
            z = c.kategorie_setzen(urllib.parse.unquote(arg or query.get("kategorie", "")))
        elif b == "frei":
            z = c.freitext(query.get("zeile1"), query.get("zeile2"))
            if query.get("ein") == "1":
                z = c.ein()
        elif b == "auto" and arg == "zyklus":
            stufen = [0, 5, 8, 12]
            z = c.auto_aus_setzen(stufen[(stufen.index(c.auto_aus) + 1) % len(stufen)] if c.auto_aus in stufen else 0)
        elif b == "auto" and zahl(arg) is not None:
            z = c.auto_aus_setzen(zahl(arg))
        elif b == "liste":
            z = c.liste_laden()
        elif b == "leeren":
            z = c.leeren()
        elif b in ("status", "zustand"):
            z = c.zustand()
        else:
            raise ServerFehler(404, f"Unbekannter Befehl: bb/{befehl}")
        if b == "status" and query.get("format") == "text":
            e = z["eintrag_auf_sendung"] if z["auf_sendung"] else z["auswahl"]
            return self._text(f"{'ON AIR' if z['auf_sendung'] else 'bereit'}\n{(e or {}).get('zeile1', '-')}")
        return self._json(200, z)

    def _sse(self, rid="haupt", quelle=""):
        R = RENDERERS[rid]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors()
        self.end_headers()
        vid, q = uuid.uuid4().hex, queue.Queue()
        with R.lock:
            R.verbindungen[vid] = q
            R.quellen[vid] = quelle
        print(f"Renderer {rid} verbunden{' (' + quelle + ')' if quelle else ''} ({len(R.verbindungen)})")
        # Aktuellen Stand nur an diese neue Seite schicken (Antworten darauf werden ignoriert)
        for b in R.wiederherstellen_befehle():
            q.put(b)
        try:
            self.wfile.write(b"retry: 1000\n\n")
            self.wfile.flush()
            while True:
                try:
                    befehl = q.get(timeout=15)
                    self.wfile.write(f"data: {json.dumps(befehl, ensure_ascii=False)}\n\n".encode("utf-8"))
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with R.lock:
                R.verbindungen.pop(vid, None)
                R.quellen.pop(vid, None)
            # Instanzen und Stand bleiben: verbindet die Seite neu, wird der Stand wiederhergestellt
            print(f"Renderer {rid} getrennt ({len(R.verbindungen)})")


def main():
    global ARGS, CONTROLLER, BAUCHBINDEN, SCHWEIZ, NATIONAL, BETEILIGUNG, AUSZAEHLUNG, CASPAR
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--komponenten", default=os.path.dirname(HIER), help="Ordner mit den oGraf-Grafiken")
    a.add_argument("--host", default="127.0.0.1", help="0.0.0.0 = im Netz erreichbar (Stream Deck an anderem Rechner)")
    a.add_argument("--casparcg", default="", help="CasparCG (AMCP) host:port, z. B. 127.0.0.1:5250 – leer = ohne CasparCG")
    a.add_argument("--caspar-haupt", default="1-10", help="CasparCG Kanal-Layer für den Hauptausgang (Key/Fill), leer = nicht")
    a.add_argument("--caspar-wand", default="2-10", help="CasparCG Kanal-Layer für die Videowand, leer = nicht")
    a.add_argument("--caspar-url", default="", help="Adresse, unter der CasparCG diesen Server erreicht (Standard http://127.0.0.1:<port>)")
    a.add_argument("--port", type=int, default=8795)
    a.add_argument("--wahlen-api", default="http://127.0.0.1:8790/api")
    a.add_argument("--ograf-api", default=None, help="oGraf-Server-API für den Controller (Standard: dieser Server)")
    a.add_argument("--renderer-id", default=None)
    a.add_argument("--layer", type=int, default=1, help="Layer für Hochrechnung Kanton")
    a.add_argument("--layer-bauchbinde", type=int, default=2, help="Layer für Bauchbinden")
    a.add_argument("--layer-wand", type=int, default=1, help="Layer der Videowand-Grafik auf dem Renderer «wand»")
    a.add_argument("--seiten-national", default="", help="Parteien je Seite Videowand National, z. B. 6,5 (leer: je 6)")
    a.add_argument("--seiten-schweiz", default="", help="Parteien je Seite Hochrechnung Schweiz, z. B. 3,3,2,3 (leer: je 3)")
    a.add_argument("--jahr", type=int, default=2027)
    a.add_argument("--sprache", default="de", choices=["de", "fr", "it"])
    a.add_argument("--nachkommastellen", type=int, default=1, choices=[0, 1])
    a.add_argument("--intervall", type=int, default=10, help="Sekunden zwischen automatischen Aktualisierungen auf Sendung")
    a.add_argument("--log", action="store_true")
    ARGS = a.parse_args()
    ARGS.komponenten = os.path.abspath(ARGS.komponenten)
    if ARGS.ograf_api is None:
        ARGS.ograf_api = f"http://127.0.0.1:{ARGS.port}{API_PREFIX}"
    CONTROLLER = Controller()
    threading.Thread(target=CONTROLLER.auto_aktualisieren, daemon=True).start()
    BAUCHBINDEN = BauchbindenController()
    try:
        BAUCHBINDEN.liste_laden()
    except ServerFehler as e:
        BAUCHBINDEN.meldung = e.meldung
    threading.Thread(target=BAUCHBINDEN.zeitgeber, daemon=True).start()
    SCHWEIZ = SchweizController()
    threading.Thread(target=SCHWEIZ.auto_aktualisieren, daemon=True).start()
    NATIONAL = NationalController()
    threading.Thread(target=NATIONAL.auto_aktualisieren, daemon=True).start()
    BETEILIGUNG = BeteiligungController()
    threading.Thread(target=BETEILIGUNG.auto_aktualisieren, daemon=True).start()
    AUSZAEHLUNG = AuszaehlungController()
    threading.Thread(target=AUSZAEHLUNG.auto_aktualisieren, daemon=True).start()
    if ARGS.casparcg:
        CASPAR = CasparWaechter(ARGS.casparcg, {"haupt": ARGS.caspar_haupt, "wand": ARGS.caspar_wand},
                                ARGS.caspar_url or f"http://127.0.0.1:{ARGS.port}")
        threading.Thread(target=CASPAR.schleife, daemon=True).start()
    for ctl in (SCHWEIZ, NATIONAL, BETEILIGUNG, AUSZAEHLUNG):   # Daten gleich holen, damit Stream-Deck-Beschriftungen sofort stehen
        try:
            ctl.aktualisieren()
        except ServerFehler:
            pass
    srv = GrafikHTTPServer((ARGS.host, ARGS.port), Handler)
    srv.daemon_threads = True
    basis = f"http://{'127.0.0.1' if ARGS.host in ('0.0.0.0', '') else ARGS.host}:{ARGS.port}"
    print(f"Grafik-Server Wahlen 2027  (Jahr {ARGS.jahr}, Sprache {ARGS.sprache})")
    print(f"  Renderer (OBS-Browserquelle 1920x1080): {basis}/renderer")
    print(f"  Menü (Start):                           {basis}/")
    print(f"  Controller Hochrechnung Kanton:         {basis}/controller")
    print(f"  Controller Hochrechnung Schweiz:        {basis}/controller/schweiz")
    print(f"  Controller Bauchbinden:                 {basis}/controller/bauchbinden")
    print(f"  Controller Videowand National:          {basis}/controller/national")
    print(f"  Wahlbeteiligung (Videowand):            {basis}/controller/national  (Bereich Wahlbeteiligung)")
    print(f"  Renderer Videowand (Vollbild):          {basis}/renderer/wand")
    print(f"  oGraf-Server-API:                       {basis}{API_PREFIX}/")
    print(f"  Grafiken: {', '.join(grafiken()) or '(keine gefunden)'}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")


if __name__ == "__main__":
    main()
