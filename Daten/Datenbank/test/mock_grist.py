"""Minimaler Nachbau der Grist-REST-API (nur die Endpunkte, die grist_sync.py nutzt). Nur für Tests."""
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KEY = "testschluessel"
DOCS = {}   # doc_id -> {tabelle: {"columns": {id: fields}, "rows": {rowid: fields}, "next": int}}
LOCK = threading.Lock()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _antwort(self, code, daten=None):
        body = json.dumps(daten).encode() if daten is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"null")

    def _route(self, methode):
        if self.headers.get("Authorization") != f"Bearer {KEY}":
            return self._antwort(401, {"error": "Unauthorized"})
        pfad = self.path.split("?")[0]
        m = re.fullmatch(r"/api/docs/([^/]+)/tables(?:/([^/]+)(?:/(records|columns)(/delete)?)?)?", pfad)
        if not m:
            return self._antwort(404, {"error": "Not found"})
        doc, tab, art, dele = m.groups()
        with LOCK:
            d = DOCS.setdefault(doc, {})
            if tab is None:
                if methode == "GET":
                    return self._antwort(200, {"tables": [{"id": t, "fields": {}} for t in d]})
                if methode == "POST":
                    for t in self._body()["tables"]:
                        if not re.fullmatch(r"[A-Z][A-Za-z0-9_]*", t["id"]):
                            return self._antwort(400, {"error": f"bad table id {t['id']}"})
                        d[t["id"]] = {"columns": {c["id"]: c.get("fields", {}) for c in t["columns"]}, "rows": {}, "next": 1}
                    return self._antwort(200, {"tables": [{"id": t} for t in d]})
            if tab not in d:
                return self._antwort(404, {"error": f"table {tab} not found"})
            t = d[tab]
            if art == "columns":
                if methode == "GET":
                    return self._antwort(200, {"columns": [{"id": c, "fields": f} for c, f in t["columns"].items()]})
                if methode == "POST":
                    for c in self._body()["columns"]:
                        t["columns"][c["id"]] = c.get("fields", {})
                    return self._antwort(200, {"columns": []})
            if art == "records":
                if dele and methode == "POST":
                    for rid in self._body():
                        t["rows"].pop(rid, None)
                    return self._antwort(200)
                if methode == "GET":
                    return self._antwort(200, {"records": [{"id": i, "fields": {c: f.get(c) for c in t["columns"]}}
                                                           for i, f in sorted(t["rows"].items())]})
                body = self._body()
                for rec in body["records"]:
                    for c in list(rec.get("fields", {})) + list(rec.get("require", {})):
                        if c not in t["columns"]:
                            return self._antwort(400, {"error": f"Invalid column {c}"})
                if methode == "POST":
                    ids = []
                    for rec in body["records"]:
                        i = t["next"]; t["next"] += 1
                        t["rows"][i] = dict(rec.get("fields", {})); ids.append({"id": i})
                    return self._antwort(200, {"records": ids})
                if methode == "PATCH":
                    for rec in body["records"]:
                        t["rows"][rec["id"]].update(rec["fields"])
                    return self._antwort(200)
                if methode == "PUT":
                    for rec in body["records"]:
                        req = rec.get("require", {})
                        treffer = [i for i, f in t["rows"].items() if all(f.get(k) == v for k, v in req.items())]
                        if treffer:
                            for i in treffer:
                                t["rows"][i].update(rec.get("fields", {}))
                        else:
                            i = t["next"]; t["next"] += 1
                            t["rows"][i] = {**req, **rec.get("fields", {})}
                    return self._antwort(200)
        return self._antwort(405, {"error": "method"})

    def do_GET(self): self._route("GET")
    def do_POST(self): self._route("POST")
    def do_PUT(self): self._route("PUT")
    def do_PATCH(self): self._route("PATCH")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8484
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
