# Wahlen-API (`wahlen_api.py`)

Kleiner HTTP-Server, der die Ansichten der Wahlen-Datenbank als JSON ausliefert. Nur lesend, nur Python-Standardbibliothek.
Die oGraf-Komponenten fragen nur diese API ab, nie die Datenbank oder Grist direkt.

## Start

    python3 wahlen_api.py --db wahlen.sqlite --jahr 2027                 # nur auf diesem Rechner
    python3 wahlen_api.py --db wahlen.sqlite --jahr 2027 --host 0.0.0.0  # im Produktionsnetz erreichbar

Standard-Port 8790. `GET /api` listet alle Routen.

## Routen

Gemeinsame Parameter: `jahr` (Standard `--jahr`), `lang=de|fr|it` (Parteinamen), `kanton=ZH` oder `kanton=1`.

| Route | Inhalt | Zusätzliche Parameter |
|---|---|---|
| `/api/status` | Fortschritt pro Kanton (x von y Sitzen, Gemeinden gemeldet) | |
| `/api/nr/parteien` | Parteien Nationalrat, Schweiz oder Kanton, mit Veränderung | `kanton`, `min_sitze`, `min_staerke` |
| `/api/nr/teilresultat` | Parteistärke aus bereits gemeldeten Gemeinden | `kanton` (Pflicht) |
| `/api/nr/kantone` | Sitze pro Kanton mit Veränderung, Majorz/Proporz, Fortschritt | |
| `/api/nr/gewaehlte` | Gewählte mit bisherig/neu, Beruf, Wohnort | `kanton`, `partei` (BFS-Nr.), `status`, `geschlecht` |
| `/api/nr/abgewaehlte` | Nicht wiedergewählte Bisherige (nur abgeschlossene Kantone) | `kanton` |
| `/api/sr/gewaehlte` | Gewählte Ständerat (inkl. Korrekturen) | `kanton` |
| `/api/sr/parteien` | Ständeratssitze pro Partei mit Veränderung | |
| `/api/sr/stand` | Wahlgänge, stille Wahlen, zweiter Wahlgang nötig | |
| `/api/nr/schweiz-insert` | Fertige Daten für die Grafik „Hochrechnung Schweiz“: Hochrechnung → Resultat, Parteistärke absteigend, Übrige am Schluss | `quelle=auto|hochrechnung|resultat`, `institut`, `sort=aktuell|vorwahl` (Reihenfolge nach Stärke der letzten Wahl, für die Videowand), `sitze=1`, `min_staerke` (0.5, nur Resultat), `max_parteien` (15) |
| `/api/nr/kanton-insert` | Fertige Daten für die Grafik „Hochrechnung Kanton“: Hochrechnung → Resultat → Zwischenstand (automatisch), Titel/Untertitel in de/fr/it | `kanton` (Pflicht), `quelle=auto|hochrechnung|resultat|zwischenstand`, `min_staerke` (2.0), `max_parteien` (9) |
| `/api/hochrechnung` | Neueste freigegebene Hochrechnung Schweiz pro Institut (Kantons-Hochrechnungen: siehe `/api/nr/kanton-insert`) | `rat=NR|SR`, `institut` |
| `/api/bauchbinden` | Freigegebene Bauchbinden | `kategorie`, `id` |
| `/api/historie/mitglieder` | Recherche: Ratsmitglieder seit 1848, eine Zeile pro Amtszeit (Parlamentsdienste) | `name`, `partei` (Familie oder Kürzel), `kanton`, `rat=NR|SR`, `geschlecht=f|m`, `von`, `bis`, `im_amt=1`, `sort=eintritt|austritt|name|dauer|alter|kanton|partei`, `richtung=auf|ab`, `limit` |
| `/api/historie/parteistaerke` | Recherche: Parteistärke Nationalrat seit 1971 (BFS) plus laufende Wahl (Resultat oder Hochrechnung), mit Rang innerhalb der Reihe (`rang_tief`, `rang_hoch`, `wahlen_in_reihe`) | `partei`, `kanton=CH|alle|Kürzel`, `von`, `bis`, `gruppiert=familie|partei`, `sort=jahr|staerke|partei|kanton`, `richtung` |
| `/api/historie/optionen` | Recherche: Auswahllisten (Parteifamilien, Kantone) und Stand der geladenen Daten | – |
| `/api/auszaehlung/nr` | Auszählungsstand Nationalrat für die Karte: pro Kanton `status` = `resultat` (Kanton abgeschlossen) → `hochrechnung` (freigegebene Kantons-Hochrechnung in Grist) → `keines`; dazu `zaehler` für die Legende | – |
| `/api/beteiligung/schweiz` | Ein Wert für die Grafik «Wahlbeteiligung»: Hochrechnung (Grist *Hochrechnung_Beteiligung*) → Schlussresultat → Zwischenstand, mit Vergleich zur letzten Wahl | `quelle=auto|hochrechnung|resultat|zwischenstand`, `institut` |
| `/api/beteiligung` | Wahlbeteiligung CH (im Zwischenstand: alle Kantone) oder Kanton | `kanton` |

## Antwort

```json
{
  "jahr": 2027,
  "stand": {"vorhanden": true, "abgeschlossen": false, "kantone_abgeschlossen": 1, "kantone_total": 26,
            "gemeinden_abgeschlossen": 112, "gemeinden_total": 2218,
            "bfs_zeitstempel": "...", "importiert_um": "..."},
  "anzahl": 15,
  "daten": [{"partei_id": 4, "partei": "SVP", "farbe": "#4B8A3E", "sitze": 62, "sitze_vorwahl": 53,
             "sitze_veraenderung": 9, "partei_staerke": 27.93, "staerke_veraenderung": 2.33, ...}]
}
```

- `stand.abgeschlossen = false` heisst Zwischenstand: die Grafik sollte das anzeigen.
- Parteien sind sortiert nach `reihenfolge` aus Grist, sonst nach Sitzen und Stärke.
- `farbe` und `partei` (Anzeigename) kommen aus Grist, sonst BFS-Kurzname und keine Farbe.
- Fehler: HTTP 400 (falscher Parameter), 404 (unbekannte Route), 503 (Datenbank gerade nicht lesbar), jeweils `{"fehler": "..."}`.
- CORS ist offen (`Access-Control-Allow-Origin: *`), damit die Grafiken aus OBS (Browser-Quelle) abfragen können.
- ETag: wer `If-None-Match` mitschickt, bekommt bei unveränderten Daten `304` ohne Inhalt.

## Beispiel für eine oGraf-Komponente

```js
const API = "http://127.0.0.1:8790/api";
let etag = null;

async function laden() {
  const r = await fetch(`${API}/nr/parteien?lang=de&min_sitze=1`, { headers: etag ? { "If-None-Match": etag } : {} });
  if (r.status === 304) return;            // nichts Neues
  if (!r.ok) return;                        // alten Stand stehen lassen
  etag = r.headers.get("ETag");
  const { stand, daten } = await r.json();
  zeichnen(daten, stand.abgeschlossen ? "Endresultat" : "Zwischenstand");
}
setInterval(laden, 10000);
laden();
```

## Getestet

`test/test_api.py` prüft gegen die echten Daten 2023 und gegen den BFS-Teststand als simuliertes 2027:
Sitze und Reihenfolge, Französisch, Kanton per Kürzel und Nummer, Gewählte, Ständerat, Beteiligung, Fehlerfälle
(unbekannter Kanton, Route, Jahr, versuchte SQL-Einschleusung), ETag/304, Zwischenstand (x von y Sitzen,
Teilresultat, Abgewählte nur aus abgeschlossenen Kantonen, Beteiligung ohne CH-Wert).

    python3 test/test_api.py wahlen.sqlite
