# Gemeinsame Dateien aller Grafiken

Hier – und nur hier – werden Schriften und Wappen gepflegt.

| Ordner | Inhalt | geht in |
|---|---|---|
| `fonts/` | SRG SSR Type als WOFF2 und `fonts.json` (Datei → Gewicht/Stil) | jede Grafik unter `fonts/` |
| `wappen/` | Kantonswappen als SVG (`ZH.svg` … `JU.svg`, `CH.svg`) | Grafiken mit Wappen (Hochrechnung Kanton, Hochrechnung Schweiz) |
| `wappen/quelle/` | Originale aus Illustrator (`*_QUAD.ai`) | bleibt hier |

**Verteilen:** passiert bei jedem Start automatisch (Startskript). Von Hand:
```bash
python3 verteilen.py
```

Jede oGraf-Grafik muss laut EBU-Richtlinie ein vollständiges Paket sein. Deshalb werden die Dateien
kopiert und nicht verknüpft. Verknüpfungen (Symlinks) synchronisiert OneDrive ausserdem nicht zuverlässig.

**Neue Schrift oder neues Wappen:** Datei hier ablegen, bei Schriften in `fonts.json` eintragen,
dann `python3 verteilen.py` oder neu starten.

**Wappen aus Illustrator neu umwandeln** (z. B. nach einer Korrektur; `pdftocairo` gehört zu Poppler,
auf dem Mac `brew install poppler`, unter Linux vorinstalliert):
```bash
cd wappen
for f in quelle/*_QUAD.ai; do k=$(basename "$f" _QUAD.ai); pdftocairo -svg "$f" "$k.svg"; done
```
