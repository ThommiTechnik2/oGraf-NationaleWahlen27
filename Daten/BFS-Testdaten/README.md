# BFS-Testdaten Nationalratswahlen (aufbereitet)

Quelle: BFS, Testdaten für die Eidg. Wahlen 2023 (GitHub bfspoku/wd-poku, Testdata1–3, Stand 12.06.2023).
Inhalt: Dummy-Resultate auf Basis der Wahl **2019** (Feld `wahl_jahr` = 2019). Nur für Struktur- und Grafiktests,
nicht als echte Resultate verwenden.

## Die drei Stände

| Ordner | Situation | Was drin ist |
|---|---|---|
| Stand1 | Vor 12:00, leer | Stammdaten, Listen, 4667 Kandidierende ohne Stimmen; alle Resultate leer |
| Stand2 | Zwischenstand | Luzern abgeschlossen (9 Sitze, 9 Gewählte), 112 Gemeinden mit Resultaten; auf Kantonsebene nur Luzern |
| Stand3 | Endstand | Alle 26 Kantone, 200 Sitze, 2218 Gemeinden, Beteiligung 45,12 % |

Jeder Ordner enthält `wahlen.sqlite` (alle Tabellen) und CSV-Dateien für Grist.
Die Tabelle `Kandidierende_Gemeinde` (Endstand 776'509 Zeilen) gibt es nur in SQLite.

## Tabellen

Stammdaten (in Grist einmal importieren, am besten aus Stand3):
- `Parteien` – partei_id, Kurz- und Langnamen DE/FR/IT/EN, Parteigruppe, politisches Lager;
  leere Spalten `farbe` und `reihenfolge` zum Pflegen in Grist
- `Kantone`, `Gemeinden`, `Kandidat_Status`, `Listen`, `Listenverbindungen`

Laufende Resultate (werden bei jedem Update ersetzt):
- `Stand`, `Stand_Kantone`
- `Ergebnis_Partei_CH`, `Ergebnis_Partei_Kanton`, `Ergebnis_Partei_Gemeinde`
- `Wahlbeteiligung_CH`, `Wahlbeteiligung_Kanton`, `Wahlbeteiligung_Gemeinde`
- `Kandidierende` (Kantonsebene, mit Stimmen und `flag_gewaehlt`)

Zeitreihen:
- `Zeitreihe_Partei_CH`, `Zeitreihe_Partei_Kanton`, `Zeitreihe_Beteiligung_Frauen_CH`, `Zeitreihe_Beteiligung_Frauen_Kanton` (ab 1991)

## Geprüft (alle drei Stände bestanden)

- Endstand: 200 Sitze (Parteien CH, Parteien Kantone, Listen, Kandidierende), Parteistärken = 100,0 %
- Summe Gemeinden = Kantonswert für Parteistimmen und Kandidatenstimmen (0 Abweichungen)
- Alle Partei-IDs der Resultate existieren in den Stammdaten

## Erkenntnisse für den Live-Betrieb

- Dateien beginnen mit UTF-8-BOM: beim Einlesen `utf-8-sig` verwenden.
- Feldnamen weichen von der Doku ab: `wahl_jahr` (Doku: `wahljahr`), `stand_kantone` (Doku: `Stand_kantone`).
- Metadaten: Der Kantonsblock heisst in Stand1 `kantone`, in Stand2/3 `stand_kantone`.
  `kanton_abgeschlossen` ist dort Text («true»/«false»), in den Resultatdateien ein echter Boolean.
- `flag_staerkste_partei` ist 1/0, `flag_gewaehlt` true/false: beide normalisiert auf 1/0.
- Geburtsdatum kommt als TT.MM.JJJJ, wird nach JJJJ-MM-TT umgewandelt.
- Gemeindenamen haben teils Leerzeichen am Ende (z. B. «Aeugst am Albis »): werden getrimmt.
- Zwischenstand: Kantonswerte erscheinen erst, wenn der Kanton abgeschlossen ist. Gemeinden laufen vorher ein.
  Eine Grafik «Stand Kanton BL» müsste also aus den Gemeinden summiert und klar als Teilresultat markiert werden.
- Gemeinden mit Auslandschweizer-Sondernummer (19xx0) kommen in diesen Testdaten nicht vor.
- Dateigrössen Endstand: Kandidierende 220 MB, Parteien 8,6 MB. Import in SQLite dauert ca. 6 Sekunden.

## Import-Skript

`Import/bfs_import.py` – wandelt einen Ordner mit BFS-JSON-Dateien in SQLite + CSV um:

    python3 bfs_import.py <ordner_mit_json> <ausgabeordner> --stand <name>

`Import/check.py` – Plausibilitätsprüfungen auf einer `wahlen.sqlite`:

    python3 check.py <ausgabeordner>/wahlen.sqlite

Das Skript ist die Grundlage für den Live-Import 2027. Noch nicht eingebaut: Abholung über die
CKAN-API mit HEAD-Prüfung, Ständerat, Listen pro Gemeinde (listen-gde).
