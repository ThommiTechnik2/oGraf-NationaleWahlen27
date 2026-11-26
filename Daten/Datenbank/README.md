# Wahlen-Datenbank (Nationalrat und Ständerat, mehrere Wahljahre)

Eine SQLite-Datei (`wahlen.sqlite`) mit den echten BFS-Daten 2023 als Basis.
2027 wird am Wahlabend in dieselben Tabellen geladen. Jede Resultattabelle hat die Spalte `wahl_jahr`,
Veränderungen rechnen die Ansichten (`v_…`) automatisch gegen die Vorwahl (Tabelle `wahl`: 2027 → 2023).

## Inhalt

| Datei | Zweck |
|---|---|
| `wahlen.sqlite.zip` | Datenbank mit den Daten 2023 und den Soll-Sitzen 2027 (entpackt ca. 38 MB) |
| `schema.sql` | Tabellen |
| `views.sql` | Ansichten für die Grafiken |
| `wahlen_db.py` | Import und Pflege (Python 3, keine Zusatzpakete) |
| `grist_sync.py`, `GRIST_SYNC.md`, `grist_config.beispiel.json` | Abgleich mit Grist (Redaktion ↔ Datenbank) |
| `wahlen_api.py`, `API.md` | JSON-Endpunkt für die oGraf-Grafiken |
| `test/` | Tests für Grist-Abgleich und API |
| `sitze_nationalrat_2023_2027.csv` | Soll-Sitze 2027 (berechnet, noch nicht gegen Verordnung geprüft) |

## Datenstand 2023 (geprüft)

Quelle: BFS, opendata.swiss «Eidgenössische Wahlen 2023», Dateistand 24.04.2024 (definitive Werte).

- Nationalrat: 200 Sitze, Parteistärken 100,0 %, 5929 Kandidierende, 200 Gewählte (152 bisherig), 638 Listen,
  2143 Gemeinden, Wahlbeteiligung 46,66 %
- Ständerat: erster und zweiter Wahlgang, 46 Gewählte (Mitte 15, FDP 11, SP 9, SVP 6, GRÜNE 3, GLP 1, MCR 1)
- Summen Gemeinden = Kanton für Kandidaten-, Partei- und Listenstimmen: 0 Abweichungen
- Abgleich mit den SRF-Gewählten 2023: identisch (einzige Differenz: Schreibweise «De Montmollin»)

## Tabellen

Stammdaten: `wahl`, `kanton`, `partei`, `kandidat_status`, `gemeinde` (pro Jahr), `kanton_sitze` (Soll-Sitze pro Jahr).
Nationalrat: `nr_stand`, `nr_stand_kanton`, `nr_liste`, `nr_liste_gemeinde`, `nr_kandidat`, `nr_kandidat_gemeinde`,
`nr_partei_ch`, `nr_partei_kanton`, `nr_partei_gemeinde`, `nr_beteiligung`, `nr_zeitreihe_partei`, `nr_zeitreihe_beteiligung`.
Ständerat: `sr_stand_kanton`, `sr_kandidat`, `sr_korrektur` (redaktionelle Nachträge).
Redaktion (aus Grist): `hochrechnung`, `bauchbinde`, Anzeigenamen in `partei`.
Protokoll: `import_log`, `sync_log`.

Redaktionelle Felder, die ein Import nie überschreibt: `partei.farbe`, `partei.reihenfolge`, `partei.links_rechts`, `kanton.name_de`.

## Ansichten für die Grafiken

| Ansicht | Für |
|---|---|
| `v_sitze_kanton` | Soll-Sitze pro Kanton mit Veränderung, Majorz/Proporz |
| `v_kanton_fortschritt` | «x von y Sitzen vergeben», Gemeinden gemeldet |
| `v_partei_ch` | Sitze und Parteistärke Schweiz mit Veränderung |
| `v_partei_kanton` | dasselbe pro Kanton, mit Flag «Kanton abgeschlossen» |
| `v_partei_kanton_teilresultat` | Parteistärke aus bereits gemeldeten Gemeinden (nicht abgeschlossene Kantone) |
| `v_nr_gewaehlte` | Gewählte mit bisherig/neu, Partei, Beruf, Wohnort |
| `v_nr_abgewaehlte` | Bisherige, die nicht wiedergewählt wurden (nur abgeschlossene Kantone) |
| `v_sr_gewaehlte`, `v_sr_partei` | Ständerat, inkl. Korrekturen |
| `v_beteiligung_kanton` | Wahlbeteiligung mit Veränderung |
| `v_hochrechnung_aktuell` | neueste freigegebene Hochrechnung pro Institut, mit Veränderung zur Vorwahl |
| `v_bauchbinde` | freigegebene Bauchbinden |

Beispiel: `SELECT kurz_de, sitze, sitze_veraenderung, partei_staerke, staerke_veraenderung FROM v_partei_ch WHERE wahl_jahr = 2027;`

## Bedienung

    python3 wahlen_db.py init wahlen.sqlite
    python3 wahlen_db.py import-nr wahlen.sqlite <ordner mit NRW-Dateien>
    python3 wahlen_db.py import-sr wahlen.sqlite <ordner mit SRW-Dateien>
    python3 wahlen_db.py sitze-aus-resultat wahlen.sqlite --jahr 2023
    python3 wahlen_db.py sitze wahlen.sqlite sitze_nationalrat_2023_2027.csv --jahr 2027 [--geprueft]
    python3 wahlen_db.py korrektur-sr wahlen.sqlite --jahr 2023 --kanton 14 --name … --vorname … --gewaehlt 0|1 --grund "…"

Ein Import ersetzt alle Zeilen seines Wahljahres in einer Transaktion. Die Datenbank läuft im WAL-Modus,
Grafiken können also lesen, während importiert wird. Mit `--jahr 2027` lassen sich Testdaten als 2027 laden
(getestet mit BFS-Teststand 2: Luzern abgeschlossen, Basel-Landschaft 28/86 Gemeinden).

## Offen

- Soll-Sitze 2027 gegen den Verordnungstext prüfen, dann mit `--geprueft` neu laden.
- Ständerat Schaffhausen: Neuwahl vom 29.06.2025 (SP-Sitz an FDP) ist in den BFS-Daten nicht enthalten.
  Mit `korrektur-sr` nachtragen (Stocker gewählt = 0, neue Person gewählt = 1), sobald der Name bestätigt ist.
- Parteifarben, Anzeigenamen und Reihenfolge in Grist pflegen (Tabelle `Parteien`), siehe GRIST_SYNC.md.
- Live-Abholung über die CKAN-API mit HEAD-Prüfung (Muster: `package_show.json`) ist noch nicht eingebaut.
- Parteinamen im BFS: «GRÜNE», «MCR» (= MCG). Für Grafiken ggf. eigene Anzeigenamen in Grist führen.
