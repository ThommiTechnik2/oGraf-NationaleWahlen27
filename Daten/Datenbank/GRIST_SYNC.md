# Grist-Abgleich (`grist_sync.py`)

Verbindet die Redaktion in Grist mit der Wahlen-Datenbank. Nur Python-Standardbibliothek.

## Datenfluss

| Richtung | Grist-Tabelle | Inhalt |
|---|---|---|
| Grist → SQLite | `Parteien` | Anzeigename DE/FR/IT, Farbe, Reihenfolge, Links-rechts |
| Grist → SQLite | `Hochrechnungen` | Institut, Nr., Zeitpunkt, Partei, Wähleranteil, ±, Sitze, Freigegeben |
| Grist → SQLite | `Bauchbinden` | Zeile 1/2, Kategorie, Sprache, Partei, Kanton, Freigegeben |
| Grist → SQLite | `SR_Korrekturen` | Nachträge Ständerat (z. B. Neuwahl SH 2025) |
| SQLite → Grist | `Parteien` | nur die BFS-Spalten (`bfs_…`), Redaktionsspalten bleiben unberührt |
| SQLite → Grist | `Resultat_Partei_CH`, `Resultat_Partei_Kanton`, `Resultat_Kantone`, `Resultat_NR_Gewaehlte`, `Resultat_SR_Gewaehlte` | Resultate zur Ansicht, werden bei jedem Abgleich überschrieben |

Regeln:
- Hochrechnungen und Bauchbinden erscheinen in den Grafik-Ansichten nur mit Häkchen «Freigegeben».
- Von mehreren Hochrechnungen eines Instituts gilt die freigegebene mit der höchsten Nummer.
- Die Resultat-Tabellen in Grist nicht von Hand ändern: der nächste Abgleich überschreibt sie.
- Parteien werden über die BFS-Nummer (`partei_id`) zugeordnet. Zeilen mit unbekannter Nummer werden ignoriert.

## Einrichten

1. In Grist ein leeres Dokument anlegen. Die Dokument-ID steht in der URL (`/doc/<ID>` bzw. nach dem Teamnamen).
2. In Grist unter Profil → API einen Schlüssel erzeugen und **nur** in eine Datei schreiben, z. B. `~/.grist_api_key`
   (`chmod 600`). Alternativ Umgebungsvariable `GRIST_API_KEY`.
3. `grist_config.beispiel.json` nach `grist_config.json` kopieren und `api_url`, `doc_id` anpassen.
   Bei Grist mit Teams lautet `api_url` ggf. `https://<host>/o/<team>/api`.
4. Tabellen anlegen lassen (ändert nur fehlende Tabellen und Spalten, keine Daten):

       python3 grist_sync.py setup

5. Erster Abgleich (füllt die Parteiliste und die Resultate 2023 zum Testen):

       python3 grist_sync.py sync --jahr 2023

## Betrieb am Wahlabend

    python3 grist_sync.py loop --intervall 30

läuft parallel zum BFS-Import. Fehler (z. B. Grist kurz nicht erreichbar) werden in `sync_log` protokolliert,
der Abgleich läuft beim nächsten Durchgang weiter. Die Datenbank bleibt dabei für die Grafiken lesbar (WAL-Modus).

## Getestet

`test/test_sync.sh` startet einen Nachbau der Grist-API (`test/mock_grist.py`, nach der offiziellen API-Dokumentation)
und prüft: Tabellen anlegen (zweiter Lauf ändert nichts), Redaktionsfarbe und Anzeigenamen kommen in SQLite an,
BFS-Kurznamen bleiben erhalten, nur freigegebene Hochrechnungen zählen, SR-Korrektur ersetzt eine gewählte Person,
Resultate landen vollständig in Grist, Redaktionsspalten überstehen den Push, wiederholter Abgleich erzeugt keine Duplikate.

**Noch nicht getestet:** gegen euer echtes Grist. Der erste Lauf von `setup` und `sync --jahr 2023` ist der Test dafür.
