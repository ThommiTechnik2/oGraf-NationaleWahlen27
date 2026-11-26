#!/usr/bin/env python3
"""
Historie für die Recherche laden (einmal vor der Wahl, braucht Internet):

  1. Ratsmitglieder seit 1848 von den Parlamentsdiensten (ws.parlament.ch, OData «MemberCouncilHistory»)
  2. Parteistärke Nationalrat seit 1971 vom BFS (PX-Datei px-x-1702020000_104, Schweiz und Kantone)
  3. Parteifamilien aus parteifamilie.csv (welche Kürzel zusammengehören)

Aufruf (im Ordner Daten/Datenbank):
  python3 historie_laden.py                    # alles
  python3 historie_laden.py --nur parlament    # nur Ratsmitglieder
  python3 historie_laden.py --nur bfs --px-datei ~/Downloads/px-x-1702020000_104.px   # BFS-Datei von Hand geladen
  python3 historie_laden.py --nur familien     # nur parteifamilie.csv neu einlesen (nach Änderungen)

Nur Python-Standardbibliothek (läuft mit dem Python 3.9 des Mac).
"""
import argparse, csv, datetime as dt, json, os, re, shutil, sqlite3, ssl, subprocess, sys, urllib.error, urllib.parse, urllib.request

HIER = os.path.dirname(os.path.abspath(__file__))
ODATA = "https://ws.parlament.ch/odata.svc/MemberCouncilHistory"
PX_URLS = [
    "https://www.pxweb.bfs.admin.ch/DownloadFile.aspx?file=px-x-1702020000_104",
    "https://www.pxweb.bfs.admin.ch/pxweb/de/px-x-1702020000_104/px-x-1702020000_104/px-x-1702020000_104.px",
]
FELDER = ["ID", "PersonNumber", "FirstName", "LastName", "GenderAsString", "CantonAbbreviation", "CouncilAbbreviation",
          "PartyAbbreviation", "PartyName", "ParlGroupAbbreviation", "DateJoining", "DateLeaving", "DateOfBirth", "DateOfDeath"]

KANTONE = {  # BFS-Nummer: Namen, wie sie in BFS-Tabellen vorkommen können
    0: ["schweiz", "suisse", "total"], 1: ["zürich", "zurich"], 2: ["bern", "berne"], 3: ["luzern", "lucerne"],
    4: ["uri"], 5: ["schwyz"], 6: ["obwalden"], 7: ["nidwalden"], 8: ["glarus", "glaris"], 9: ["zug", "zoug"],
    10: ["freiburg", "fribourg"], 11: ["solothurn", "soleure"], 12: ["basel-stadt", "bâle-ville"],
    13: ["basel-landschaft", "bâle-campagne"], 14: ["schaffhausen", "schaffhouse"],
    15: ["appenzell ausserrhoden", "appenzell a.rh.", "appenzell rhodes-extérieures"],
    16: ["appenzell innerrhoden", "appenzell i.rh.", "appenzell rhodes-intérieures"],
    17: ["st. gallen", "st.gallen", "saint-gall"], 18: ["graubünden", "grisons", "grigioni"], 19: ["aargau", "argovie"],
    20: ["thurgau", "thurgovie"], 21: ["tessin", "ticino"], 22: ["waadt", "vaud"], 23: ["wallis", "valais"],
    24: ["neuenburg", "neuchâtel"], 25: ["genf", "genève"], 26: ["jura"],
}


def schluessel(k):
    return re.sub(r"[\s.]", "", (k or "").lower())


def oeffnen(pfad):
    if not os.path.exists(pfad):
        sys.exit(f"Datenbank nicht gefunden: {pfad}\n(Zuerst «python3 wahlen_db.py init» bzw. das Startskript ausführen.)")
    db = sqlite3.connect(pfad, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(open(os.path.join(HIER, "schema.sql"), encoding="utf-8").read())
    return db


CA_DATEI = None          # --ca-datei
_KONTEXT = None          # wird beim ersten Zertifikatsfehler auf den macOS-Schlüsselbund umgestellt
SCHLUESSELBUENDE = ["/System/Library/Keychains/SystemRootCertificates.keychain", "/Library/Keychains/System.keychain",
                    os.path.expanduser("~/Library/Keychains/login.keychain-db")]


def kontext_schluesselbund():
    """SSL-Kontext mit den Zertifikaten aus dem macOS-Schlüsselbund (inkl. Firmen-Zertifikat der SRG, falls
    das Netz HTTPS prüft). Die Prüfung bleibt eingeschaltet – nur die Liste vertrauenswürdiger Stellen ändert sich."""
    if not shutil.which("security"):
        return None
    pem = ""
    for kb in SCHLUESSELBUENDE:
        if os.path.exists(kb):
            r = subprocess.run(["security", "find-certificate", "-a", "-p", kb], capture_output=True, text=True)
            pem += r.stdout
    ctx = ssl.create_default_context()
    anzahl = 0
    for block in re.findall(r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", pem, re.S):
        try:
            ctx.load_verify_locations(cadata=block)
            anzahl += 1
        except (ssl.SSLError, ValueError):
            pass
    if not anzahl:
        return None
    print(f"  (Zertifikate aus dem macOS-Schlüsselbund verwendet: {anzahl})")
    return ctx


def kontext():
    global _KONTEXT
    if _KONTEXT is None:
        datei = CA_DATEI or os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
        _KONTEXT = ssl.create_default_context(cafile=os.path.expanduser(datei)) if datei else ssl.create_default_context()
    return _KONTEXT


def zertifikatsfehler(e):
    grund = getattr(e, "reason", e)
    return isinstance(grund, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(e)


def holen(url, versuche=3):
    global _KONTEXT
    letzter, schluesselbund_versucht = None, False
    for _ in range(versuche):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Wahlen2027-Recherche/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60, context=kontext()) as r:
                return r.read()
        except Exception as e:
            letzter = e
            if zertifikatsfehler(e) and not schluesselbund_versucht:
                schluesselbund_versucht = True
                ctx = kontext_schluesselbund()
                if ctx is not None:
                    _KONTEXT = ctx
                    continue
            if zertifikatsfehler(e):
                break
    if zertifikatsfehler(letzter):
        raise RuntimeError(f"{url}: Zertifikat nicht vertrauenswürdig ({letzter}).\n"
                           "    Abhilfe siehe README A9 (Zertifikate) oder: --ca-datei <Firmen-Zertifikat.pem>")
    raise RuntimeError(f"{url}: {letzter}")


def odata_datum(v):
    """«/Date(-822787200000)/» → «1943-12-06»"""
    if not v:
        return None
    m = re.search(r"-?\d+", v)
    if not m:
        return None
    return (dt.datetime(1970, 1, 1) + dt.timedelta(milliseconds=int(m.group()))).date().isoformat()


def protokoll(db, quelle, zeilen, hinweis=""):
    db.execute("INSERT OR REPLACE INTO hist_quelle VALUES (?,?,?,?)",
               (quelle, dt.datetime.now().isoformat(timespec="seconds"), zeilen, hinweis))


# ---------------------------------------------------------------- Parlament
def lade_parlament(db):
    print("Ratsmitglieder (ws.parlament.ch) …")
    zeilen, skip, seite = [], 0, 1000
    while True:
        q = urllib.parse.urlencode({"$filter": "Language eq 'DE'", "$select": ",".join(FELDER),
                                    "$top": seite, "$skip": skip, "$format": "json", "$orderby": "ID"})
        d = json.loads(holen(f"{ODATA}?{q}"))["d"]
        teil = d["results"] if isinstance(d, dict) else d
        zeilen += teil
        print(f"  {len(zeilen)} Amtszeiten", end="\r", flush=True)
        if len(teil) < seite:
            break
        skip += seite
    print()
    if not zeilen:
        raise RuntimeError("Parlament: keine Daten erhalten")
    db.execute("DELETE FROM hist_mitglied")
    db.executemany("INSERT OR REPLACE INTO hist_mitglied VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [(
        z["ID"], z.get("PersonNumber"), z.get("FirstName"), z.get("LastName"), (z.get("GenderAsString") or "").lower() or None,
        z.get("CantonAbbreviation"), z.get("CouncilAbbreviation"), z.get("PartyAbbreviation"), z.get("PartyName"),
        z.get("ParlGroupAbbreviation"), odata_datum(z.get("DateJoining")), odata_datum(z.get("DateLeaving")),
        odata_datum(z.get("DateOfBirth")), odata_datum(z.get("DateOfDeath"))) for z in zeilen])
    protokoll(db, "parlament", len(zeilen), "ws.parlament.ch MemberCouncilHistory")
    print(f"  {len(zeilen)} Amtszeiten gespeichert")


# ---------------------------------------------------------------- BFS PX
def px_lesen(roh):
    """Minimaler PC-Axis-Leser: gibt (dimensionen, werte_je_dimension, daten) zurück."""
    kopf = roh[:4000].decode("latin-1")
    m = re.search(r'CODEPAGE\s*=\s*"([^"]+)"', kopf)
    text = roh.decode((m.group(1) if m else "iso-8859-1").lower().replace("windows-", "cp"), errors="replace")
    teil = text.split("DATA=", 1)
    if len(teil) != 2:
        raise RuntimeError("PX-Datei ohne DATA-Teil")
    kopfteil, datenteil = teil

    eintraege = {}
    for m in re.finditer(r'([A-Z\-]+)(\[[^\]]*\])?(\("([^"]*)"\))?\s*=\s*((?:"[^"]*"|[^;"])*);', kopfteil):
        name, sprache, _, dim, wert = m.groups()
        if sprache:
            continue   # nur Hauptsprache
        eintraege[(name, dim)] = re.findall(r'"([^"]*)"', wert) or [wert.strip()]

    stub = eintraege.get(("STUB", None), [])
    heading = eintraege.get(("HEADING", None), [])
    dims = stub + heading
    werte = {d: eintraege[("VALUES", d)] for d in dims}
    zahlen = []
    for t in re.findall(r'"[^"]*"|[^\s;]+', datenteil.split(";")[0]):
        t = t.strip('"')
        try:
            zahlen.append(float(t))
        except ValueError:
            zahlen.append(None)   # «...», «-» usw.
    erwartet = 1
    for d in dims:
        erwartet *= len(werte[d])
    if len(zahlen) != erwartet:
        raise RuntimeError(f"PX: {len(zahlen)} Werte, erwartet {erwartet}")
    return dims, werte, zahlen


def kanton_nr(name):
    n = name.strip().lstrip("-. ").lower()
    n = n.split(" / ")[0].strip()
    for nr, namen in KANTONE.items():
        if n in namen:
            return nr
    for nr, namen in KANTONE.items():   # z. B. «Kanton Zürich»
        if any(re.search(r"\b" + re.escape(x) + r"$", n) for x in namen):
            return nr
    return None


def lade_bfs(db, px_datei=None):
    print("Parteistärke Nationalrat seit 1971 (BFS) …")
    if px_datei:
        roh = open(os.path.expanduser(px_datei), "rb").read()
        quelle = os.path.basename(px_datei)
    else:
        roh, quelle, fehler = None, None, []
        for u in PX_URLS:
            try:
                roh = holen(u)
                if b"DATA=" in roh:
                    quelle = u
                    break
                fehler.append(f"{u}: keine PX-Datei")
                roh = None
            except Exception as e:
                fehler.append(str(e))
        if roh is None:
            raise RuntimeError("BFS-Datei nicht ladbar:\n    " + "\n    ".join(fehler) +
                               "\n  → Im Browser herunterladen: bfs.admin.ch, Suche «px-x-1702020000_104», «Download PX»,"
                               "\n    dann: python3 historie_laden.py --nur bfs --px-datei <Pfad zur Datei>")
    dims, werte, zahlen = px_lesen(roh)

    def finde(*worte):
        for d in dims:
            if any(w in d.lower() for w in worte):
                return d
        return None
    d_jahr, d_kt, d_partei = finde("jahr", "année"), finde("kanton", "canton"), finde("partei", "parti")
    if not (d_jahr and d_kt and d_partei):
        raise RuntimeError(f"PX: Dimensionen nicht erkannt: {dims}")
    d_mass = [d for d in dims if d not in (d_jahr, d_kt, d_partei)]
    mass_index = {}
    for d in d_mass:
        i = next((i for i, v in enumerate(werte[d]) if "stärke" in v.lower() or "force" in v.lower()), None)
        if i is None:
            if len(werte[d]) == 1:
                i = 0
            else:
                raise RuntimeError(f"PX: Parteistärke in «{d}» nicht gefunden: {werte[d]}")
        mass_index[d] = i

    unbekannt, zeilen = set(), []
    groessen = [len(werte[d]) for d in dims]
    schritte = [1] * len(dims)
    for i in range(len(dims) - 2, -1, -1):
        schritte[i] = schritte[i + 1] * groessen[i + 1]
    ij, ik, ip = dims.index(d_jahr), dims.index(d_kt), dims.index(d_partei)
    for a, jahr in enumerate(werte[d_jahr]):
        if not jahr.strip()[:4].isdigit():
            continue
        for b, kt in enumerate(werte[d_kt]):
            nr = kanton_nr(kt)
            if nr is None:
                unbekannt.add(kt)
                continue
            for c, partei in enumerate(werte[d_partei]):
                if partei.strip().lower() in ("total", "parteien - total", "alle parteien"):
                    continue
                pos = [0] * len(dims)
                pos[ij], pos[ik], pos[ip] = a, b, c
                for d, i in mass_index.items():
                    pos[dims.index(d)] = i
                v = zahlen[sum(p * s for p, s in zip(pos, schritte))]
                if v is not None:
                    zeilen.append((int(jahr.strip()[:4]), nr, partei.strip(), round(v, 3)))
    if unbekannt:
        print("  Hinweis, nicht zugeordnete Gebiete (übersprungen):", ", ".join(sorted(unbekannt)))
    if not zeilen:
        raise RuntimeError("BFS: keine Werte gefunden")
    db.execute("DELETE FROM hist_partei_staerke")
    db.executemany("INSERT OR REPLACE INTO hist_partei_staerke VALUES (?,?,?,?)", zeilen)
    jahre = sorted({z[0] for z in zeilen})
    protokoll(db, "bfs", len(zeilen), f"{quelle}; {jahre[0]}–{jahre[-1]}")
    print(f"  {len(zeilen)} Werte gespeichert ({jahre[0]}–{jahre[-1]}, {len({z[2] for z in zeilen})} Parteien)")


# ---------------------------------------------------------------- Parteifamilien
def lade_familien(db):
    pfad = os.path.join(HIER, "parteifamilie.csv")
    with open(pfad, encoding="utf-8-sig", newline="") as f:
        zeilen = [(schluessel(r["kuerzel"]), r["kuerzel"].strip(), r["familie"].strip())
                  for r in csv.DictReader(f) if (r.get("kuerzel") or "").strip() and (r.get("familie") or "").strip()]
    db.execute("DELETE FROM partei_familie")
    db.executemany("INSERT OR REPLACE INTO partei_familie VALUES (?,?,?)", zeilen)
    protokoll(db, "familien", len(zeilen), "parteifamilie.csv")
    print(f"Parteifamilien: {len(zeilen)} Kürzel")
    bekannt = {z[0] for z in zeilen}
    for tabelle, spalte in (("hist_mitglied", "partei"), ("hist_partei_staerke", "partei")):
        offen = [(k, n) for k, n in db.execute(f"SELECT {spalte}, COUNT(*) FROM {tabelle} GROUP BY 1 ORDER BY 2 DESC")
                 if k and schluessel(k) not in bekannt]
        if offen:
            print(f"  Ohne Familie in {tabelle} (gelten als eigene Familie): " +
                  ", ".join(f"{k} ({n})" for k, n in offen[:40]) + (" …" if len(offen) > 40 else ""))


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--db", default=os.path.join(HIER, "wahlen.sqlite"))
    a.add_argument("--nur", choices=["parlament", "bfs", "familien"])
    a.add_argument("--px-datei", help="BFS-PX-Datei von Hand heruntergeladen")
    a.add_argument("--ca-datei", help="Zertifikatsdatei (PEM), z. B. das Firmen-Root-Zertifikat, falls die automatische Erkennung nicht reicht")
    args = a.parse_args()
    global CA_DATEI
    CA_DATEI = args.ca_datei
    db = oeffnen(args.db)
    fehler = []
    for teil, fn in (("parlament", lambda: lade_parlament(db)), ("bfs", lambda: lade_bfs(db, args.px_datei))):
        if args.nur in (None, teil):
            try:
                fn()
                db.commit()
            except Exception as e:
                db.rollback()
                fehler.append(f"{teil}: {e}")
                print(f"  FEHLER {teil}: {e}")
    lade_familien(db)
    db.commit()
    db.close()
    if fehler:
        sys.exit("\nNicht alles geladen:\n  " + "\n  ".join(fehler))
    print("\nFertig. Die Recherche-Seite zeigt die neuen Daten sofort (kein Neustart nötig).")


if __name__ == "__main__":
    main()
