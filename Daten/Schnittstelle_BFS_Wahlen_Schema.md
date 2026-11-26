# BFS-Resultatdienst Wahlen: Schnittstelle und Grist-Schema (Vorlage aus 2023)

Basis: Dokumentation des BFS zu den Eidg. Wahlen 2023 (bfspoku.github.io/wd-poku) und der Datensatz
«Eidgenössische Wahlen 2023» auf opendata.swiss. Für 2027 ist zu prüfen, ob Dateinamen, Felder und
Zeitpunkte gleich bleiben. Dieses Dokument ist eine Arbeitsvorlage, keine Zusage des BFS.

## 1. Ablauf der Datenabholung (Prinzip des BFS)

1. Ressourcen-URLs über die CKAN-API von opendata.swiss holen (`package_show?id=<datensatz>`).
   - Test: `https://ckan.ogdch-abnahme.clients.liip.ch/api/3/action/package_show?id=eidg-wahlen-2023`
   - Produktion: `https://ckan.opendata.swiss/api/3/action/package_show?id=eidg-wahlen-2023`
2. Pro Ressource eine HEAD-Anfrage auf die Datei-URL, `Last-Modified` bzw. `ETag` vergleichen.
3. Nur herunterladen, wenn die Datei neuer ist.

Wichtig:
- Keine fest einprogrammierten Datei-URLs. Bei einem Serverausfall schaltet das BFS auf einen Fallback-Server und passt die URLs in der API an.
- Dateien werden gross (Kandidierende 2023 im Test ca. 3 MB). Nicht zu oft prüfen, sonst bremst das System.
- Produktion: Listen und Kandidaturen vor dem Wahlsonntag, Resultate ab Sonntag 12:00 Uhr (MEZ).
- Test-Umgebung mit Testdaten vor dem Wahlsonntag, Beispieldateien auf GitHub (bfspoku/wd-poku, Testdata1 bis 3):
  leer / Zwischenstand (LU fertig, BL teilweise) / Endstand.
- Referenz-Code vom BFS: github.com/bfspoku/ogd-demo (Python).

## 2. Dateien (Nationalrat 2023) und Aufbau

Alle Dateien: `sd-t-17.02-NRW2023-<name>.json`, jeweils mit `timestamp`, `wahljahr`, `spatial_reference` und einem Block `stand`.

| Datei | Ebenen | Inhalt |
|---|---|---|
| parteien | CH, Kantone, Gemeinden | Parteiresultate: Stimmen, Parteistärke %, fiktive Wählende, Sitze, Kandidaturen, Frauen/Männer, Rang, Vergleich zur letzten Wahl |
| kandidierende | Kantone, Gemeinden | Kandidierende mit Liste, Listenplatz, Beruf, Wohnort, Status, Stimmen, `flag_gewaehlt` |
| wahlbeteiligung | CH, Kantone, Gemeinden | Wahlberechtigte, Wahlzettel (eingelegt, leer, ungültig, gültig), Beteiligung %, Vergleich zur letzten Wahl |
| listen (Kantone) | Kantone | Listen mit Listenverbindungen, Stimmen, Stärke, Sitzen (Details noch nicht gelesen) |
| listen-gde | Gemeinden | Stimmen pro Liste und Gemeinde, vor 12:00 am Wahlsonntag komplett leer (0 KB) |
| zeitreihen | CH, Kantone | Parteien, Frauenanteil und Wahlbeteiligung ab 1991 (Details noch nicht gelesen) |
| SR-Kandidierende | Kantone | Ständerat, erster und zweiter Wahlgang (Details noch nicht gelesen) |
| metadaten | | Codetabellen: Parteien (`partei_id`), Kandidatenstatus und weitere (Inhalt noch nicht gelesen) |

### Block `stand` (in jeder Resultatdatei)
- `wahl_abgeschlossen` (bool): alle Kantone haben geliefert und bestätigt
- `kantone_total` (26), `kantone_abgeschlossen`
- `gemeinden_total`, `gemeinden_abgeschlossen`
- `Stand_kantone[]`: `kanton_nummer`, `kanton_abgeschlossen`, `gemeinden_total`, `gemeinden_abgeschlossen`

### Parteien (alle Ebenen)
Schlüssel: `partei_id` (+ `kanton_nummer` bzw. `gemeinde_nummer`).
Felder: `stimmen_partei`, `partei_staerke`, `partei_rang`, `flag_staerkste_partei`, `fiktive_waehlende`,
`anzahl_listen`, `anzahl_kandidierende(_f/_m)`, `anzahl_gewaehlte(_f/_m)` und je Kennzahl
`letzte_wahl_*` und `differenz_*`.

### Kandidierende (Kantonsebene)
Schlüssel: `kanton_nummer` + `liste_nummer_bfs` + `kandidat_nummer`.
Felder: `liste_nummer_kanton`, `liste_bezeichnung`, `kandidat_listenplatz_1/_2`, `name`, `vorname`,
`geschlecht` (F/M), `geburtsdatum`, `geburtsjahr`, `wohnort_gemeinde_nummer`, `wohnort`, `beruf`,
`kandidat_status_id` (2 = bisherig, sonst null), `kandidat_partei_id`, `stimmen_kandidat`, `flag_gewaehlt`.

## 3. Stolpersteine für Grafiken

- `flag_gewaehlt` wird erst gesetzt, wenn der Kanton bestätigt ist (`kanton_abgeschlossen`).
  Grafiken «gewählt» nur für abgeschlossene Kantone zeigen.
- Teilresultate: Kantone liefern gemeindeweise. Beteiligung und Parteistärken auf Gemeindeebene laufen laufend ein.
  Hochrechnungen werden in der Dokumentation nicht erwähnt (vermutlich kommen sie von den Instituten, prüfen).
- `level_ch` in Parteien und Wahlbeteiligung wird erst gefüllt, wenn die Wahl abgeschlossen ist.
  Schweizer Zwischenstände müssen wir selbst aus den Kantonsdaten summieren.
- Parteien, die 2023 nicht mehr antreten, stehen trotzdem in der Datei (für Vergleiche).
- Mitte-Vergleich: Die Vorwahl-Werte (`letzte_wahl_*`) kombinieren CVP und BDP unter `partei_id` 34 (Mitte).
  Die frühere CVP trägt die ID 2. Für Vergleiche mit der Wahl 2023 ist das bereits eingerechnet.
- Gemeindenummern: Bei gemeinsamer Urne gibt es für einzelne Gemeinden kein eigenes Resultat.
  Auslandschweizer haben in manchen Kantonen eigene Pseudo-Gemeinden: Nummer = `19` + Kantonsnummer (2-stellig) + `0`
  (z. B. AI = 19160). Wohnort-Gemeinde `9950` = Ausland.
- Dokumentationshinweis zu prüfen: Im Block `level_gemeinden` der Kandidierenden sind `name` und `vorname`
  in der Doku vertauscht beschrieben. Mit echten Daten gegenprüfen.
- Dateistruktur leer vs. gefüllt: Die Datei listen-gde ist vor 12:00 komplett leer, kandidierende hat keine
  leere Gemeindestruktur. Das Einlesen muss mit fehlenden Blöcken umgehen können.
- Ständerat 2023: Stand nach den Wahlgängen 2023, die Neuwahl in Schaffhausen vom 29.06.2025 ist nicht berücksichtigt.

## 4. Vorschlag Grist-Tabellen

Stammdaten:
- Kantone: `kanton_nummer` (PK), Kürzel, Name (DE/FR/IT), NR-Sitze, SR-Sitze
- Gemeinden: `gemeinde_nummer` (PK, inkl. Sondernummern), Name, `kanton_nummer`
- Parteien: `partei_id` (PK), Kürzel DE/FR/IT/EN, Farbe, Links-rechts-Position, Mutterpartei
- Listen: `kanton_nummer` + `liste_nummer_bfs` (PK), Bezeichnung, Listenverbindung, Unterlistenverbindung

Laufende Resultate (werden bei jedem Update überschrieben oder versioniert):
- Stand: Zeitstempel, `wahl_abgeschlossen`, Zähler; plus Stand_Kantone (26 Zeilen)
- Ergebnis_Partei_CH, Ergebnis_Partei_Kanton, Ergebnis_Partei_Gemeinde
- Kandidierende (Schlüssel wie oben) mit Stimmen und `flag_gewaehlt`
- Wahlbeteiligung_CH, _Kanton, _Gemeinde

Test-/Redaktionsdaten:
- Hochrechnung: Institut, Zeitpunkt, Partei, Prognosewert (kommt nicht aus dem BFS)

## 5. Offene Punkte

- Ob und wie sich Dateinamen und Felder für 2027 ändern (z. B. `NRW2027`, neue Datensatz-ID). Anfang 2027 abgleichen.
- Beschreibung der Dateien listen, zeitreihen, SR-Kandidierende und metadaten noch lesen.
- Datensatz-Lizenz/Nutzungsbedingungen auf opendata.swiss prüfen (Namensnennung der Quelle).
