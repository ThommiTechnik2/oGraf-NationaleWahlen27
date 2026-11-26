# Grist-Importdaten Wahlen (Stand: Nationalratswahlen 2023)

Zweck: Testdaten und Schema-Vorlage für das Projekt Nationale Wahlen 2027.
Die echten Daten 2027 kommen aus dem Resultatdienst, die Schnittstelle wird Anfang 2027 definiert.

Quelle dieser Testdaten: öffentliche Wahlgrafik-Daten von SRF (Stand 04.02.2024, Endresultat).
Nur zur internen Entwicklung und für Grafik-Tests gedacht. Keine Porträts oder Bilder enthalten.

## Tabellen (Import in dieser Reihenfolge)

| Datei | Grist-Tabelle | Inhalt | Zeilen |
|---|---|---|---|
| kantone.csv | Kantone | Kürzel, Name, NR-Sitze, SR-Sitze | 26 |
| parteien.csv | Parteien | Kürzel, Name, Farbe, Links-rechts-Position, Sitze und Wähleranteile NR/SR mit Veränderung | 14 |
| nr_waehleranteil_kanton.csv | NR_Wähleranteil | Partei × Kanton (inkl. «CH» = Schweiz gesamt) | 212 |
| sr_sitze_kanton.csv | SR_Sitze | Partei × Kanton, Sitze im Ständerat | 124 |
| gewaehlte_2023.csv | Gewählte | 200 Nationalräte und 46 Ständeräte | 246 |

## Verknüpfungen in Grist

- Gewählte.partei → Parteien.kuerzel (Reference)
- Gewählte.kanton → Kantone.kuerzel (Reference)
- NR_Wähleranteil.partei / SR_Sitze.partei → Parteien.kuerzel
- NR_Wähleranteil.kanton / SR_Sitze.kanton → Kantone.kuerzel (Kanton «CH» = Gesamtschweiz, in Kantone ergänzen oder separat behandeln)

## Hinweise

- `rat`: NR = Nationalrat, SR = Ständerat. Elf Personen stehen in beiden Räten als gewählt
  (Salzmann, Wasserfallen, Moser, Maillard, Broulis, Binder-Keller, Regazzi, Poggia, F. Roth, Gössi, Hurni).
  Die Quelle sagt nicht, welches Mandat sie angenommen haben. Das muss für Grafiken separat geführt werden.
- `neu`: 1 = neu gewählt im Rat.
- `stimmen`: bei stillen Wahlen (OW, AI im Ständerat) leer.
- In `Gewählte.partei` kommen Kürzel vor, die nicht in `Parteien` stehen (Basta, LDP, ALG).
  Sie sind Unterparteien; in der Quelle gehören sie zu einer Mutterpartei (parentParty).
  Für 2027 im Schema eine Spalte `mutterpartei` vorsehen.
- `parteien.links_rechts`: Position auf der Skala 0 (links) bis 300 (rechts), wie von der Quelle verwendet.
- Sitzverteilung der Kantone gilt für 2023. Für 2027 kann sie sich ändern und muss aktualisiert werden.
- Nicht enthalten, aber in der Quelle vorhanden: Website, smartvote-Link, politische Ämter, Berufsangaben aller 6112 Kandidierenden.
