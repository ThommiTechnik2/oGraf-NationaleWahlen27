"""Test historie_laden.py ohne Internet: Parlament und BFS werden nachgebildet."""
import json, os, sqlite3, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import historie_laden as h

DB = sys.argv[1]
ms = lambda d: "/Date(%d)/" % int((__import__("datetime").datetime.fromisoformat(d) - __import__("datetime").datetime(1970, 1, 1)).total_seconds() * 1000)
PERSONEN = [
    ("a1", 1, "Georg", "Wander", "m", "BE", "NR", "BGB", "1943-12-06", "1946-02-01", "1890-01-01"),
    ("a2", 2, "Cécile", "Bühlmann", "f", "LU", "NR", "GPS", "1991-11-25", "2005-11-27", "1949-05-31"),
    ("a3", 3, "Michael", "Töngi", "m", "LU", "NR", "GRÜNE", "2019-12-02", None, "1967-01-01"),
    ("a4", 4, "Elisabeth", "Kopp", "f", "ZH", "NR", "FDP", "1979-11-26", "1984-10-02", "1936-12-16"),
    ("a5", 5, "Ida", "Glanzmann", "f", "LU", "NR", "M-E", "2006-03-06", "2023-12-03", "1958-09-26"),
] + [(f"x{i}", 100 + i, "Test", f"Person{i}", "m", "ZH", "NR", "SP", "1999-12-06", "2003-11-30", "1960-01-01") for i in range(1500)]

def holen_mock(url, versuche=3):
    if "parlament" in url:
        q = dict(x.split("=", 1) for x in url.split("?", 1)[1].split("&"))
        skip, top = int(q["%24skip"]), int(q["%24top"])
        teil = [dict(zip(["ID", "PersonNumber", "FirstName", "LastName", "GenderAsString", "CantonAbbreviation",
                          "CouncilAbbreviation", "PartyAbbreviation"], p[:8]),
                     PartyName=p[7], ParlGroupAbbreviation=None, DateJoining=ms(p[8]),
                     DateLeaving=ms(p[9]) if p[9] else None, DateOfBirth=ms(p[10]), DateOfDeath=None)
                for p in PERSONEN[skip:skip + top]]
        return json.dumps({"d": {"results": teil}}).encode()
    raise RuntimeError("kein Netz")

PX = ('CHARSET="ANSI";\nCODEPAGE="iso-8859-1";\nLANGUAGE="de";\nLANGUAGES="de","fr";\n'
      'STUB="Jahr","Kanton";\nHEADING="Partei","Ergebnis";\n'
      'VALUES("Jahr")="1971","2023";\nVALUES[fr]("Année")="1971","2023";\n'
      'VALUES("Kanton")="Schweiz","- Zürich","- Luzern";\n'
      'VALUES("Partei")="FDP","CVP","GPS";\n'
      'VALUES("Ergebnis")="Parteistimmen","Parteistärke in %";\n'
      'DATA=\n'
      '1 21.8 2 20.3 3 "..."\n'   # 1971 CH
      '1 20.0 2 15.0 3 "-"\n'     # 1971 ZH
      '1 25.0 2 50.0 3 ...\n'     # 1971 LU
      '1 14.3 2 0 3 9.8\n'        # 2023 CH
      '1 13.0 2 5 3 10\n'
      '1 16.0 2 25 3 11;\n').encode("latin-1")
open("/tmp/hist/t.px", "wb").write(PX)

h.holen = holen_mock
db = h.oeffnen(DB)
h.lade_parlament(db); db.commit()
h.lade_bfs(db, "/tmp/hist/t.px"); db.commit()
h.lade_familien(db); db.commit()
f = []
def pruefe(n, ist, soll):
    print(("OK   " if ist == soll else "FEHL ") + n, ist)
    if ist != soll: f.append(n)
pruefe("Amtszeiten", db.execute("SELECT COUNT(*) FROM hist_mitglied").fetchone()[0], len(PERSONEN))
pruefe("Datum", db.execute("SELECT eintritt, austritt FROM hist_mitglied WHERE id='a1'").fetchone(), ("1943-12-06", "1946-02-01"))
pruefe("noch im Amt", db.execute("SELECT austritt FROM hist_mitglied WHERE id='a3'").fetchone()[0], None)
pruefe("BFS Werte", db.execute("SELECT COUNT(*) FROM hist_partei_staerke").fetchone()[0], 15)
pruefe("FDP CH 1971", db.execute("SELECT staerke FROM hist_partei_staerke WHERE wahl_jahr=1971 AND kanton_nummer=0 AND partei='FDP'").fetchone()[0], 21.8)
pruefe("LU erkannt", db.execute("SELECT staerke FROM hist_partei_staerke WHERE wahl_jahr=2023 AND kanton_nummer=3 AND partei='CVP'").fetchone()[0], 25.0)
pruefe("Familie BGB", db.execute("SELECT familie FROM partei_familie WHERE schluessel='bgb'").fetchone()[0], "SVP")
print("ALLES OK" if not f else f"FEHLER {f}")
sys.exit(1 if f else 0)
