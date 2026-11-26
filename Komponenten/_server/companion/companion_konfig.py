#!/usr/bin/env python3
"""
Erzeugt die Bitfocus-Companion-Konfiguration für das Stream Deck XL (Wahlen 2027).

    python3 companion_konfig.py [--host 127.0.0.1] [--port 8795] [--aus Wahlen2027.companionconfig]

Inhalt: 3 Seiten (Hochrechnung Kanton, Hochrechnung Schweiz, Bauchbinden), eine Verbindung «Generic HTTP»,
Benutzervariablen und ein Trigger, der jede Sekunde den Zustand vom Grafik-Server holt (Beschriftung und
Farben der Tasten). Exportformat Version 9 – Companion 5.x wandelt es beim Import selbst ins aktuelle Format um.

Die drei Seiten müssen in Companion auf drei AUFEINANDERFOLGENDE Seiten importiert werden
(die Wechseltasten springen relativ: eine Seite vor / zurück).
"""
import argparse
import json
import secrets

VERBINDUNG = "wahlen2027http"

FARBE = {
    "text": 0xFFFFFF, "kanton": 0x1F2A36, "befehl": 0x2B3037, "ein": 0x2F5D3E, "aus": 0x6B2430,
    "leeren": 0x3D3D3D, "nav": 0x3A3F47, "anzeige": 0x101215, "leer": 0x000000,
    "gewaehlt": 0x2A78BE, "onair": 0xD0213C, "naechste": 0x8A5A12,
}

KANTONE = ["ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG", "FR", "SO", "BS", "BL", "SH", "AR", "AI",
           "SG", "GR", "AG", "TG", "TI", "VD", "VS", "NE", "GE", "JU"]


def nid():
    return secrets.token_urlsafe(15)[:21]


class Bau:
    def __init__(self, basis):
        self.basis = basis
        self.variablen = {}

    # ---------- Bausteine ----------
    def get(self, pfad, variable=""):
        return {"id": nid(), "definitionId": "get", "connectionId": VERBINDUNG, "type": "action", "children": {},
                "options": {"url": f"{self.basis}{pfad}", "header": "", "jsonResultDataVariable": variable,
                            "result_stringify": True, "statusCodeVariable": ""}}

    def seite(self, richtung):
        return {"id": nid(), "definitionId": "inc_page" if richtung > 0 else "dec_page", "connectionId": "internal",
                "type": "action", "children": {},
                "options": {"controller": "self", "controller_from_variable": False, "controller_variable": ""}}

    def wenn(self, variable, wert, farbe):
        return {"id": nid(), "definitionId": "variable_value", "connectionId": "internal", "type": "feedback",
                "children": {}, "isInverted": False,
                "options": {"variable": f"custom:{variable}", "op": "eq", "value": str(wert)},
                "style": {"bgcolor": FARBE[farbe], "color": FARBE["text"]}}

    def var(self, name, beschreibung, standard=""):
        if name not in self.variablen:
            self.variablen[name] = {"description": beschreibung, "defaultValue": standard,
                                    "persistCurrentValue": False, "sortOrder": len(self.variablen)}
        return f"$(custom:{name})"

    def taste(self, text, aktionen=(), farbe="befehl", groesse="auto", rueckmeldung=()):
        return {
            "type": "button",
            "style": {"text": text, "textExpression": False, "size": groesse, "png64": None,
                      "alignment": "center:center", "pngalignment": "center:center",
                      "color": FARBE["text"], "bgcolor": FARBE[farbe], "show_topbar": False},
            "options": {"stepProgression": "auto", "stepExpression": "", "rotaryActions": False},
            "feedbacks": list(rueckmeldung),
            "steps": {"0": {"action_sets": {"down": list(aktionen), "up": []}, "options": {"runWhileHeld": []}}},
            "localVariables": [],
        }

    @staticmethod
    def seite_aus_tasten(nummer, name, tasten):
        """tasten: Liste von 32 Einträgen (Reihe für Reihe, 8 pro Reihe), None = leer."""
        controls = {}
        for i, t in enumerate(tasten):
            if t is None:
                continue
            reihe, spalte = divmod(i, 8)
            controls.setdefault(str(reihe), {})[str(spalte)] = t
        return {"id": nid(), "name": name, "controls": controls,
                "gridSize": {"minColumn": 0, "maxColumn": 7, "minRow": 0, "maxRow": 3}}

    # ---------- Seiten ----------
    def seite_kanton(self):
        sel = self.var("kt_kanton", "Kanton: gewählt")
        _ = sel
        self.var("kt_onair_kanton", "Kanton: auf Sendung (Kürzel)")
        self.var("kt_onair", "Kanton: auf Sendung 1/0", "0")
        t = []
        for kt in KANTONE:
            t.append(self.taste(kt, [self.get(f"/sd/kanton/{kt}")], "kanton", "24",
                                [self.wenn("kt_kanton", kt, "gewaehlt"), self.wenn("kt_onair_kanton", kt, "onair")]))
        t.append(self.taste("EIN", [self.get("/sd/ein")], "ein", "18", [self.wenn("kt_onair", 1, "onair")]))
        t.append(self.taste("WEITER", [self.get("/sd/weiter")], groesse="14"))
        t.append(self.taste("ZURÜCK", [self.get("/sd/zurueck")], groesse="14"))
        t.append(self.taste("AUS", [self.get("/sd/aus")], "aus", "18"))
        t.append(self.taste("SCHWEIZ ▶", [self.seite(+1)], "nav", "14"))
        t.append(self.taste("LEEREN", [self.get("/sd/leeren")], "leeren", "14"))
        return self.seite_aus_tasten(1, "Wahlen Kanton", t)

    def seite_schweiz(self):
        self.var("ch_onair", "Schweiz: auf Sendung 1/0", "0")
        self.var("ch_seite_onair", "Schweiz: Seite auf Sendung")
        self.var("ch_seite_naechste", "Schweiz: nächste Startseite")
        anzeige = self.var("ch_anzeige", "Schweiz: Anzeige", "BEREIT")
        t = [
            self.taste("EIN", [self.get("/sd/ch/ein")], "ein", "18", [self.wenn("ch_onair", 1, "onair")]),
            self.taste("WEITER", [self.get("/sd/ch/weiter")], groesse="14"),
            self.taste("ZURÜCK", [self.get("/sd/ch/zurueck")], groesse="14"),
            self.taste("AUS", [self.get("/sd/ch/aus")], "aus", "18"),
            self.taste("VON\\nVORNE", [self.get("/sd/ch/vonvorne")], groesse="14"),
            self.taste("DATEN\\nNEU", [self.get("/sd/ch/neu")], groesse="14"),
            self.taste("LEEREN", [self.get("/sd/ch/leeren")], "leeren", "14"),
            self.taste(anzeige, [], "anzeige", "14", [self.wenn("ch_onair", 1, "onair")]),
        ]
        for n in range(1, 9):
            parteien = self.var(f"ch_seite_{n}", f"Schweiz: Parteien Seite {n}")
            t.append(self.taste(f"SEITE {n}\\n{parteien}", [self.get(f"/sd/ch/seite/{n}")], groesse="auto",
                                rueckmeldung=[self.wenn("ch_seite_naechste", n, "naechste"),
                                              self.wenn("ch_seite_onair", n, "onair")]))
        t += [None] * 8
        t += [self.taste("◀ KANTON", [self.seite(-1)], "nav", "14")] + [None] * 6 + \
             [self.taste("BAUCH-\\nBINDEN ▶", [self.seite(+1)], "nav", "14")]
        return self.seite_aus_tasten(2, "Wahlen Schweiz", t)

    def seite_bauchbinden(self):
        self.var("bb_onair", "Bauchbinde: auf Sendung 1/0", "0")
        self.var("bb_slot_auswahl", "Bauchbinde: gewählte Taste")
        self.var("bb_slot_onair", "Bauchbinde: Taste auf Sendung")
        seite = self.var("bb_seite", "Bauchbinde: Listenseite", "1/1")
        auto = self.var("bb_auto", "Bauchbinde: Auto-Aus", "aus")
        t = []
        for n in range(1, 25):
            name = self.var(f"bb_slot_{n}", f"Bauchbinde: Name Taste {n}")
            t.append(self.taste(name, [self.get(f"/sd/bb/slot/{n}")], "kanton", "auto",
                                [self.wenn("bb_slot_auswahl", n, "gewaehlt"), self.wenn("bb_slot_onair", n, "onair")]))
        t += [
            self.taste("◀ SCHWEIZ", [self.seite(-1)], "nav", "14"),
            self.taste(f"SEITE ▶\\n{seite}", [self.get("/sd/bb/seite/vor")], groesse="14"),
            self.taste("▲ VORH.", [self.get("/sd/bb/vorherige")], groesse="14"),
            self.taste("▼ NÄCHSTE", [self.get("/sd/bb/naechste")], groesse="14"),
            self.taste("EIN", [self.get("/sd/bb/ein")], "ein", "18", [self.wenn("bb_onair", 1, "onair")]),
            self.taste("AUS", [self.get("/sd/bb/aus")], "aus", "18"),
            self.taste(f"AUTO-AUS\\n{auto}", [self.get("/sd/bb/auto/zyklus")], groesse="14"),
            self.taste("LEEREN", [self.get("/sd/bb/leeren")], "leeren", "14"),
        ]
        return self.seite_aus_tasten(3, "Wahlen Bauchbinden", t)

    def trigger(self):
        aktionen = [self.get(f"/sd/wert/{name}", name) for name in self.variablen]
        return {
            "type": "trigger",
            "options": {"name": "Wahlen 2027: Zustand holen (jede Sekunde)", "enabled": True, "sortOrder": 0},
            "actions": aktionen,
            "condition": [],
            "events": [{"id": nid(), "type": "interval", "enabled": True, "options": {"seconds": 1}}],
            "localVariables": [],
        }


def erzeugen(host, port):
    b = Bau(f"http://{host}:{port}")
    seiten = {"1": b.seite_kanton(), "2": b.seite_schweiz(), "3": b.seite_bauchbinden()}
    return {
        "version": 9,
        "type": "full",
        "companionBuild": "wahlen2027-generator",
        "pages": seiten,
        "triggers": {nid(): b.trigger()},
        "custom_variables": b.variablen,
        "customVariablesCollections": [],
        "instances": {
            VERBINDUNG: {
                "label": "Wahlen2027",
                "instance_type": "generic-http",
                "config": {"prefix": "", "proxyAddress": "", "rejectUnauthorized": True,
                           "insecureHTTPParser": False, "authType": "none"},
                "isFirstInit": False,
                "lastUpgradeIndex": -1,
                "updatePolicy": "stable",
                "enabled": True,
                "sortOrder": 0,
            }
        },
        "connectionCollections": [],
    }


if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--host", default="127.0.0.1", help="Adresse des Grafik-Servers aus Sicht von Companion")
    a.add_argument("--port", type=int, default=8795)
    a.add_argument("--aus", default="Wahlen2027_generiert.companionconfig",
                   help="Achtung: Wahlen2027.companionconfig ist der Export aus Companion – nicht überschreiben")
    args = a.parse_args()
    with open(args.aus, "w", encoding="utf-8") as f:
        json.dump(erzeugen(args.host, args.port), f, ensure_ascii=False, indent=1)
    print(f"geschrieben: {args.aus}")
