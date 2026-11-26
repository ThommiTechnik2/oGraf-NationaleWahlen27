#!/usr/bin/env python3
"""
Gemeinsame Dateien in alle oGraf-Grafiken verteilen.

  Komponenten/_gemeinsam/fonts/   → <grafik>/fonts/    (in jede Grafik)
  Komponenten/_gemeinsam/wappen/  → <grafik>/wappen/   (nur in Grafiken, die Wappen anzeigen)

Jede oGraf-Grafik muss ein eigenständiges Paket sein (EBU OGraf), deshalb Kopien statt Verknüpfungen.
Kopiert wird nur, was fehlt oder sich geändert hat. Nichts wird gelöscht.

Die Startskripte rufen das bei jedem Start auf. Von Hand:
  python3 verteilen.py           # mit Ausgabe
  python3 verteilen.py --still   # nur Fehler und Änderungen melden
"""
import filecmp, os, shutil, sys

HIER = os.path.dirname(os.path.abspath(__file__))
KOMPONENTEN = os.path.dirname(HIER)
SCHRIFT_ENDUNGEN = (".woff2", ".woff", ".otf", ".ttf")
WAPPEN_ENDUNGEN = (".svg", ".png")


def grafiken():
    for name in sorted(os.listdir(KOMPONENTEN)):
        pfad = os.path.join(KOMPONENTEN, name)
        if name.startswith(("_", ".")) or not os.path.isdir(pfad):
            continue
        if any(f.endswith(".ograf.json") and not f.startswith(".") for f in os.listdir(pfad)):
            yield name, pfad


def zeigt_wappen(pfad):
    datei = os.path.join(pfad, "graphic.mjs")
    try:
        return "./wappen/" in open(datei, encoding="utf-8").read()
    except OSError:
        return False


def kopieren(quelle, ziel_ordner, endungen, extra=()):
    if not os.path.isdir(quelle):
        return 0
    os.makedirs(ziel_ordner, exist_ok=True)
    neu = 0
    for f in sorted(os.listdir(quelle)):
        q = os.path.join(quelle, f)
        if f.startswith(".") or not os.path.isfile(q) or not (f.lower().endswith(endungen) or f in extra):
            continue
        z = os.path.join(ziel_ordner, f)
        if os.path.exists(z) and filecmp.cmp(q, z, shallow=False):
            continue
        shutil.copyfile(q, z)
        neu += 1
    return neu


def main():
    still = "--still" in sys.argv
    fonts = os.path.join(HIER, "fonts")
    wappen = os.path.join(HIER, "wappen")
    summe = 0
    for name, pfad in grafiken():
        n = kopieren(fonts, os.path.join(pfad, "fonts"), SCHRIFT_ENDUNGEN, extra=("fonts.json",))
        w = kopieren(wappen, os.path.join(pfad, "wappen"), WAPPEN_ENDUNGEN) if zeigt_wappen(pfad) else 0
        summe += n + w
        if n or w or not still:
            teile = [f"{n} Schriftdatei(en)" if n else "", f"{w} Wappen" if w else ""]
            print(f"  {name}: " + (", ".join(t for t in teile if t) + " aktualisiert" if n or w else "aktuell"))
    if summe or not still:
        print(f"Gemeinsame Dateien verteilt ({summe} kopiert).")


if __name__ == "__main__":
    main()
