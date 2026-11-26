# Wahlen 2027 – Grafik-Anlage: Kaltstart

Diese Anleitung bringt die ganze Anlage vom ausgeschalteten Mac bis zur vorführbaren Grafik.
Sie ist so geschrieben, dass sie auch jemand ohne Vorwissen abarbeiten kann.

> **Kurzfassung:** Im Ordner «Wahlen 2027» doppelklicken auf **`Wahlen 2027 starten.command`** → Wahljahr wählen →
> das Menü öffnet sich im Browser. In OBS die Browserquelle einmal aktualisieren. Fertig. (Details: Teil B.)

---

## So hängt alles zusammen

```
  Grist (Redaktion)            BFS (Resultate, ab Wahltag)
        │  grist_sync.py              │  wahlen_db.py
        ▼                             ▼
  ┌──────────────────────────────────────────┐
  │  wahlen.sqlite  (Daten/Datenbank)        │
  └──────────────────────────────────────────┘
        │  wahlen_api.py   → http://127.0.0.1:8790/api
        ▼
  ┌──────────────────────────────────────────┐
  │  grafik_server.py  → http://127.0.0.1:8795│
  │   • Menü und Controller (Browser)        │
  │   • Stream Deck  (/sd/…)                 │
  │   • oGraf-Server-API                     │
  │   • Renderer-Seite für OBS               │
  └──────────────────────────────────────────┘
        │
        ▼
  OBS: Browserquelle „Grafik“ (1920×1080, transparent)
```

Es laufen **drei Programme in drei Terminal-Fenstern**: Daten-API, Grist-Abgleich, Grafik-Server.
Dazu Grist (in OrbStack/Docker) und OBS. Die Fenster müssen offen bleiben, solange gesendet wird.

---

## A. Einmalig vorbereiten (nur auf einem neuen Mac)

Abhaken, dann muss das nie wieder gemacht werden.

1. **Projektordner lokal verfügbar.** Im Finder `OneDrive-SRGSSR › 01 - Beruflich › Claude › oGraf › Wahlen 2027`
   rechts anklicken → **«Immer auf diesem Gerät behalten»**. Sonst fehlen Dateien, wenn das Netz weg ist.
2. **Python 3.** Terminal öffnen und eingeben:
   ```bash
   python3 --version
   ```
   Es muss `Python 3.9` oder neuer erscheinen. Falls nicht: `xcode-select --install` ausführen und bestätigen.
   Weitere Pakete braucht es nicht.
3. **Grist** läuft in **OrbStack** (Docker). OrbStack installiert, der Grist-Container ist angelegt und erreichbar unter
   `http://localhost:8484`. Das Dokument heisst **«Nationale Wahlen 2027»**.
4. **Grist-API-Schlüssel** – in Grist oben rechts Profil → **API** → Schlüssel erzeugen/kopieren. Dann im Terminal
   (den Schlüssel statt `…` einfügen):
   ```bash
   echo "…" > ~/.grist_api_key
   chmod 600 ~/.grist_api_key
   ```
   ⚠️ Der Schlüssel gehört **nur** in diese Datei – nie in den Projektordner, nie in einen Chat oder eine Mail.
5. **Datenbank entpackt.** Im Ordner `Daten/Datenbank` muss `wahlen.sqlite` liegen. Fehlt sie:
   ```bash
   cd ~/Library/CloudStorage/OneDrive-SRGSSR/"01 - Beruflich"/Claude/oGraf/"Wahlen 2027"/Daten/Datenbank
   unzip wahlen.sqlite.zip
   python3 wahlen_db.py views wahlen.sqlite
   ```
6. **Grist-Tabellen anlegen** (ändert keine Daten, darf jederzeit wiederholt werden):
   ```bash
   python3 grist_sync.py setup
   ```
   Legt auch die Tabelle **Hochrechnung_Beteiligung** an. Dort pro Hochrechnung Institut, Nummer, Zeitpunkt,
   Beteiligung, ± und «Freigegeben» erfassen.
7. **OBS:** eine Browserquelle anlegen (siehe Schritt B6).
8. **Stream Deck XL** (optional): Bitfocus Companion installiert, Tasten nach `Komponenten/README.md` belegt.
9. **Historie für die Recherche laden** (braucht Internet, dauert etwa eine Minute; einmal vor der Wahl, gern im
   Sommer 2027 noch einmal, damit die neuesten Ratsmitglieder drin sind):
   ```bash
   cd ~/Library/CloudStorage/OneDrive-SRGSSR/"01 - Beruflich"/Claude/oGraf/"Wahlen 2027"/Daten/Datenbank
   python3 historie_laden.py
   ```
   Lädt die Ratsmitglieder seit 1848 (Parlamentsdienste) und die Parteistärke seit 1971 (BFS) in `wahlen.sqlite`.
   Klappt der BFS-Download nicht, zeigt das Skript, wie man die Datei von Hand holt. Welche Kürzel zur selben
   Partei gehören (BGB → SVP, CVP/BDP → Mitte …), steht in `parteifamilie.csv`. Nach einer Änderung dort:
   `python3 historie_laden.py --nur familien`.

   **Fehler «CERTIFICATE_VERIFY_FAILED»:** Python vertraut den Zertifikaten der Webseiten nicht (typisch im
   Firmennetz, das HTTPS prüft). Das Skript nimmt dann von selbst die Zertifikate aus dem macOS-Schlüsselbund.
   Reicht das nicht, eine der beiden Lösungen:
   - Python von python.org installiert? Im Finder `Programme › Python 3.x` → **«Install Certificates.command»**
     doppelklicken, dann das Skript nochmals starten.
   - Firmen-Zertifikat von der IT als `.pem` geben lassen, dann:
     `python3 historie_laden.py --ca-datei ~/Downloads/firmen-root.pem`

   Die Zertifikatsprüfung **nie** abschalten.

---

## B. Kaltstart

### Schnellstart mit dem Startskript (empfohlen)

1. **OBS** starten.
2. Im Finder im Ordner «Wahlen 2027» doppelklicken auf **`Wahlen 2027 starten.command`**.
   - Beim allerersten Mal fragt macOS evtl. nach: Rechtsklick auf die Datei → **Öffnen** → **Öffnen**.
   - Meldet macOS «keine Berechtigung»: einmal im Terminal
     `chmod +x ~/Library/CloudStorage/OneDrive-SRGSSR/"01 - Beruflich"/Claude/oGraf/"Wahlen 2027"/*.command`
3. Es erscheint die Frage nach dem Wahljahr: **2023 (Probe)** für Proben und Präsentationen, **2027 (Wahltag)** am Wahltag.
   (Ohne Antwort nach 20 Sekunden: 2023.)
4. Das Skript prüft alles der Reihe nach (✔ grün, ! gelb, ✘ rot), startet bei Bedarf Grist in OrbStack,
   dann Daten-API, Grist-Abgleich und Grafik-Server, und öffnet das **Menü** im Browser.
5. In OBS Rechtsklick auf die Browserquelle «Grafik» → **Aktualisieren** (Einrichten der Quelle: B6).
6. Im Menü müssen die Lämpchen grün sein (Videowand nur, wenn sie angeschlossen ist) → **Funktionsprobe B8**.

Das Terminal-Fenster des Skripts **offen lassen** – es zeigt laufend die Meldungen aller Teile.
Stürzt ein Teil ab, startet das Skript ihn nach 3 Sekunden von selbst neu.
**Beenden:** im Fenster **Ctrl+C** oder Fenster schliessen. Ist das Fenster schon weg und läuft noch etwas:
**`Wahlen 2027 stoppen.command`** doppelklicken.

Protokolle: `~/Library/Logs/Wahlen2027/` (eine Datei pro Teil). Einstellungen (Seitenaufteilung Schweiz,
Abgleich-Intervall, Ports) stehen oben im Startskript.

### Manuell, Schritt für Schritt (falls das Skript nicht geht)

> **Wahljahr:** Bis zum Wahltag gibt es nur Daten von **2023**. Für Proben und Präsentationen deshalb überall
> `--jahr 2023` anhängen. Am Wahltag 2027 einfach weglassen.

Alle Befehle beginnen im Projektordner. Damit man den langen Pfad nicht jedes Mal tippen muss, kann man ihn
in jedem neuen Terminal-Fenster zuerst so setzen:

```bash
W=~/Library/CloudStorage/OneDrive-SRGSSR/"01 - Beruflich"/Claude/oGraf/"Wahlen 2027"
```

### B1. Grist starten
1. **OrbStack** öffnen (Programme). Warten, bis der Grist-Container grün läuft (falls nicht: ▶ beim Container).
2. Im Browser `http://localhost:8484` öffnen → Dokument «Nationale Wahlen 2027» muss erscheinen.

✅ Prüfen: Das Dokument öffnet sich und zeigt u. a. die Tabellen *Parteien*, *Hochrechnungen*, *Bauchbinden*.

### B2. Terminal 1 – Daten-API
Terminal öffnen (Programme › Dienstprogramme › Terminal):
```bash
W=~/Library/CloudStorage/OneDrive-SRGSSR/"01 - Beruflich"/Claude/oGraf/"Wahlen 2027"
cd "$W/Daten/Datenbank"
python3 wahlen_api.py --jahr 2023
```
✅ Prüfen: Es erscheint eine Zeile mit `http://127.0.0.1:8790/api`. Im Browser
`http://127.0.0.1:8790/api/status` öffnen → es erscheinen Daten (JSON-Text), keine Fehlermeldung.

### B3. Terminal 2 – Grist-Abgleich
Neues Terminal-Fenster (**Cmd+N**):
```bash
W=~/Library/CloudStorage/OneDrive-SRGSSR/"01 - Beruflich"/Claude/oGraf/"Wahlen 2027"
cd "$W/Daten/Datenbank"
python3 grist_sync.py loop --intervall 10 --jahr 2023
```
✅ Prüfen: Alle 10 Sekunden erscheint eine Zeile `… Abgleich`. Keine Zeile mit «Grist-Fehler».

Was in Grist freigegeben wird (Häkchen **Freigegeben**), ist damit nach höchstens etwa 20 Sekunden in den Controllern.

### B4. Terminal 3 – Grafik-Server
Neues Terminal-Fenster (**Cmd+N**):
```bash
W=~/Library/CloudStorage/OneDrive-SRGSSR/"01 - Beruflich"/Claude/oGraf/"Wahlen 2027"
cd "$W/Komponenten/_server"
python3 grafik_server.py --jahr 2023 --seiten-schweiz 3,3,2,3
```
✅ Prüfen: Es erscheinen die Adressen (Menü, Controller, Renderer) und
`Grafiken: wahlen2027-bauchbinde, wahlen2027-hochrechnung-kanton, wahlen2027-hochrechnung-schweiz`.

### B5. Menü öffnen
Im Browser: **`http://127.0.0.1:8795/`**

✅ Prüfen – vier Lämpchen oben:

| Lämpchen | Soll | Wenn nicht |
|---|---|---|
| Renderer (OBS) | grün nach Schritt B6 | OBS-Quelle aktualisieren |
| Daten-API | grün | Terminal 1 prüfen |
| Grist-Abgleich | grün («vor x s») | Terminal 2 prüfen |
| Grafiken | grün, 3 Stück | Terminal 3 neu starten |

### B6. OBS
1. OBS starten, Szene mit der Browserquelle **«Grafik»** wählen. Falls sie noch nicht existiert:
   Quelle hinzufügen → **Browser** → Einstellungen:
   - URL: `http://127.0.0.1:8795/renderer`
   - Breite **1920**, Höhe **1080**
   - «Seite neu laden, wenn Szene aktiv wird»: **aus**
   - Benutzerdefiniertes CSS: leer lassen
   - Quelle zuoberst in der Szene (über der Kamera).
2. Rechtsklick auf die Quelle → **Aktualisieren**.

✅ Prüfen: Im Menü ist das Lämpchen «Renderer» grün («1 Seite(n) verbunden»).

3. **Videowand** (Hochrechnung National, Vollbild): eigener Ausgang **`http://127.0.0.1:8795/renderer/wand`**.
   Je nach Aufbau: auf dem Rechner, der die Wand bespielt, im Browser im Vollbild öffnen – oder in OBS eine eigene
   Szene «Videowand» mit einer zweiten Browserquelle (1920×1080) und diese per Vollbild-Projektor auf die Wand legen.
   ✅ Im Menü wird das Lämpchen «Renderer Videowand» grün.

### B7. Stream Deck (optional)
Companion starten. Die Tasten rufen nur Adressen auf (`http://127.0.0.1:8795/sd/…`), es gibt nichts weiter
einzurichten. Belegung: `Komponenten/README.md`.

### B8. Funktionsprobe (2 Minuten)
Im Menü nacheinander öffnen und in OBS (Vorschau) kontrollieren:

1. **Bauchbinden** → einen Eintrag wählen → **EIN** → Bauchbinde unten links → **AUS**.
2. **Hochrechnung Schweiz** → **EIN** → Insert unten rechts → **WEITER** → **AUS**.
   Die Taste EIN zeigt jetzt «ab Seite 3» – so soll es sein (Fortsetzen).
3. **Hochrechnung Kanton** → **BS** → **EIN** → **WEITER** bis die Grafik von selbst ausblendet.
4. **Videowand National** → **EIN** (SVP-Balken wächst) → **WEITER** … → **AUS**. Auf dem Wand-Ausgang kontrollieren.
   **Wahlbeteiligung** (Menü → Kachel «Wahlbeteiligung», Stream Deck Seite Videowand: WB EIN / WB AUS) → **EIN**: der Ring läuft auf,
   der Wert erscheint im roten Teil. Nimmt automatisch Hochrechnung, sonst Schlussresultat, sonst Zwischenstand der eingelegten Stimmen.
   Teilt sich den Layer mit Videowand National: Das jeweils andere blendet beim Umschalten selber aus.
   **Auszählungsstand** (Menü → Kachel «Auszählungsstand», Stream Deck Seite Videowand unterste Reihe: KARTE EIN / KARTE AUS) → **EIN**:
   Schweizer Karte, Kantone mit Resultat dunkelrot, mit freigegebener Kantons-Hochrechnung rosa, sonst grau. Färbt sich während der Sendung
   selbst um, sobald ein Kanton abgeschlossen ist. Teilt sich die Wand ebenfalls mit National und Wahlbeteiligung.

Alles gesehen? → **Die Anlage ist bereit.**

---

## C. Präsentation (Vorschlag für den Ablauf)

Vorbereitung: In Grist die Demo-Daten aus `Daten/Demo/` importieren (falls noch nicht geschehen):
oben links **Neu** (Add New) → **Aus Datei importieren** (Import from file) → `hochrechnung_schweiz_2023_demo.csv` →
im Import-Dialog als Ziel die bestehende Tabelle *Hochrechnungen* wählen (nicht «Neue Tabelle»),
Spalten-Zuordnung prüfen → Importieren. Ebenso
`bauchbinden_demo.csv` in *Bauchbinden*. (Das ist die erste SRF-Hochrechnung 2023 von 16 Uhr. Die Spalte
«± Prozentpunkte» ist angenommen – damit erscheint «±» bei Veränderungen im Fehlerbereich wie im Original.)

1. **Menü** zeigen – alles auf einen Blick, alles grün.
2. **Bauchbinde** «Lukas Golder» ein und aus – Animation wie SRF 2023.
3. **Hochrechnung Schweiz**: EIN, WEITER (Seite 2), dann **AUS** («Regie muss kurzfristig raus»).
   Danach wieder **EIN** → geht mit Seite 3 (EVP, EDU) weiter, nicht von vorne.
4. **Kanton BS** einblenden, während die Schweiz steht → die Schweiz blendet vorher sauber aus.
5. **Videowand**: Partei für Partei wachsen lassen wie SRF um 16 Uhr; nach GLP beginnt Seite 2.
6. **Live aus Grist**: In Grist eine neue Bauchbinde anlegen und «Freigegeben» anhaken → nach etwa 20 Sekunden ist
   sie im Bauchbinden-Controller.
7. **Gewählte**: Im Bauchbinden-Controller «Gewählte Nationalrat» → Kanton wählen → alle Gewählten 2023 mit
   «Nationalrätin SP/BS» bzw. «neu gewählt, …» sind sofort verfügbar.
8. Stream Deck: dieselben Abläufe auf den Tasten.

---

## D. Herunterfahren

1. In OBS die Grafik ausblenden (oder im Controller **LEEREN**).
2. Mit Startskript: im Skript-Fenster **Ctrl+C** (oder `Wahlen 2027 stoppen.command`).
   Manuell gestartet: in jedem der drei Terminal-Fenster **Ctrl+C** drücken, dann Fenster schliessen.
3. OBS beenden. OrbStack kann laufen bleiben.

---

## E. Wenn etwas nicht geht

| Problem | Ursache | Lösung |
|---|---|---|
| Browser: «Safari kann die Seite nicht öffnen» | Das zuständige Programm läuft nicht | 8790 → Terminal 1, 8795 → Terminal 3 starten |
| OBS zeigt nichts | Renderer nicht verbunden oder Quelle alt | Menü: Lämpchen Renderer? Rechtsklick Quelle → Aktualisieren. Grafik erscheint wieder im aktuellen Zustand |
| Neue Bauchbinde/Hochrechnung fehlt im Controller | Grist-Abgleich läuft nicht oder «Freigegeben» fehlt | Terminal 2 prüfen; Häkchen in Grist; im Controller «Liste neu laden» bzw. DATEN NEU |
| Terminal: `Address already in use` / Startskript: «Port … belegt» | Programm läuft schon (z. B. in einem anderen Fenster) | `Wahlen 2027 stoppen.command`, dann neu starten. Notfalls: `lsof -i :8795` (bzw. `:8790`), dann `kill <PID>` |
| Startskript: «Grist nicht erreichbar» | OrbStack/Grist-Container startet nicht | OrbStack öffnen, Container von Hand starten (▶). Die Grafiken laufen auch ohne Grist weiter, nur ohne neue Redaktionsdaten |
| Grafik-Server neu gestartet (Absturz), OBS zeigt noch eine alte Grafik | Der neue Server weiss nichts von der alten | Im Controller **LEEREN**, dann normal weiter |
| Terminal 2: `Grist-Fehler: 401` / `403` | API-Schlüssel fehlt oder falsch | Schritt A4 wiederholen |
| Terminal 2: `Grist-Fehler: … Connection refused` | Grist läuft nicht | Schritt B1 |
| Controller: «Keine Daten» / leere Tabellen | Falsches Wahljahr | Terminal 1 und 3 mit `--jahr 2023` starten (bis zum Wahltag) |
| Controller Schweiz zeigt «Resultat Schweiz» statt «Hochrechnung» | In Grist ist keine Hochrechnung Schweiz freigegeben | Demo-Hochrechnung importieren (Teil C) |
| Controller Schweiz: «Keine freigegebene Hochrechnung und kein Schlussresultat» | Am Wahltag vor der ersten Hochrechnung normal | Hochrechnung in Grist erfassen und freigeben |
| Schrift sieht anders aus als SRF | SRF-Schrift noch nicht abgelegt | Dateien in `fonts/` jeder Grafik legen (siehe dort `LIESMICH.md`) |
| Terminal 3 zeigt `ConnectionResetError` | Ältere Version des Servers | Aktuelle `grafik_server.py` verwenden (meldet das nicht mehr) – harmlos |

Wenn gar nichts mehr geht: alles mit Ctrl+C beenden und bei **B2** neu beginnen. Die Datenbank bleibt dabei erhalten.

---

## F. Adressen und Ports

| Was | Adresse |
|---|---|
| **Menü (Start)** | `http://127.0.0.1:8795/` |
| Hochrechnung Kanton | `http://127.0.0.1:8795/controller` |
| Hochrechnung Schweiz | `http://127.0.0.1:8795/controller/schweiz` |
| Bauchbinden | `http://127.0.0.1:8795/controller/bauchbinden` |
| OBS-Browserquelle | `http://127.0.0.1:8795/renderer` |
| Videowand (Vollbild) | `http://127.0.0.1:8795/renderer/wand` |
| Controller Videowand National | `http://127.0.0.1:8795/controller/national` |
| Controller Wahlbeteiligung | `http://127.0.0.1:8795/controller/beteiligung` |
| Controller Auszählungsstand | `http://127.0.0.1:8795/controller/auszaehlung` |
| Recherche (Moderation) | `http://127.0.0.1:8795/recherche` |
| oGraf-Server-API | `http://127.0.0.1:8795/ograf/v1/` |
| Daten-API | `http://127.0.0.1:8790/api` |
| Grist | `http://localhost:8484` |

Soll ein zweiter Rechner (z. B. Stream Deck an einem anderen Mac) zugreifen: Grafik-Server mit `--host 0.0.0.0`
starten und statt `127.0.0.1` die IP dieses Macs verwenden.

---

## G. Ordner

| Ordner | Inhalt |
|---|---|
| `Wahlen 2027 starten.command`, `Wahlen 2027 stoppen.command` | Startskript und Notaus |
| `Wahlen 2027 starten.sh`, `Wahlen 2027 stoppen.sh` | dasselbe für Linux Mint (siehe Abschnitt H) |
| `Komponenten/` | oGraf-Grafiken und Grafik-Server – Details und Stream-Deck-Belegung in `Komponenten/README.md` |
| `Komponenten/_gemeinsam/` | **Schriften und Wappen – nur hier pflegen.** Werden beim Start in alle Grafiken kopiert (`verteilen.py`, siehe `LIESMICH.md` dort) |
| `Daten/Datenbank/` | Datenbank, Daten-API, Grist-Abgleich – Details in `README.md`, `API.md`, `GRIST_SYNC.md` |
| `Daten/Demo/` | Demo-Daten für Grist (Hochrechnung Schweiz 2023, Bauchbinden) |
| `Daten/` | Grunddaten 2023 als CSV, BFS-Schnittstelle (`Schnittstelle_BFS_Wahlen_Schema.md`), BFS-Testdaten |

---

## H. Betrieb auf Linux cachyOS

Die ganze Anlage läuft auch unter Linux Mint (getestet mit dem Startskript unter Linux, Python 3.10 oder neuer).
Für Linux gibt es `Wahlen 2027 starten.sh` und `Wahlen 2027 stoppen.sh`; sie tun dasselbe wie die Mac-Skripte.

**Einmalig einrichten**

1. **Projektordner kopieren.** OneDrive hat keinen offiziellen Linux-Client: den Ordner `Wahlen 2027` per USB-Stick
   oder Netzwerk z. B. nach `~/Wahlen 2027` kopieren. Achtung: Änderungen auf dem Linux-Rechner gehen dann
   nicht automatisch zurück in OneDrive.
2. **Skripte ausführbar machen** (Kopieren verliert das oft):
   ```bash
   cd ~/"Wahlen 2027"
   chmod +x "Wahlen 2027 starten.sh" "Wahlen 2027 stoppen.sh"
   ```
3. **Docker für Grist:**
   ```bash
   sudo apt install docker.io
   sudo usermod -aG docker $USER      # danach einmal ab- und wieder anmelden
   docker run -d --name grist --restart unless-stopped -p 8484:8484 -v ~/grist-daten:/persist gristlabs/grist
   ```
   Dann `http://localhost:8484` öffnen und die Datei `Nationale Wahlen 2027.grist` aus dem Projektordner
   importieren (Dokument heisst wieder «Nationale Wahlen 2027»). Danach Grist-API-Schlüssel wie in A4 nach
   `~/.grist_api_key` und `grist_config.json` prüfen (Dokument-ID ändert sich beim Import).
4. **OBS** mit Browserquelle: aus dem offiziellen PPA (`sudo add-apt-repository ppa:obsproject/obs-studio`,
   dann `sudo apt install obs-studio`) oder als Flatpak. Die OBS-Version aus dem normalen Mint-Paketarchiv hat
   teils **keine** Browserquelle.
5. **Historie für die Recherche** wie in A9 (`python3 historie_laden.py`). Unter Linux kommt der
   Zertifikatsfehler normalerweise nicht vor.

**Starten:** im Dateimanager auf `Wahlen 2027 starten.sh` doppelklicken → «Ausführen» (das Skript öffnet sich
selbst in einem Terminalfenster) oder im Terminal `./"Wahlen 2027 starten.sh"`. Die Abfrage des Wahljahrs
kommt als Fenster; mit `./"Wahlen 2027 starten.sh" 2027` entfällt sie. Beenden mit Ctrl+C oder Fenster
schliessen, Notaus mit `Wahlen 2027 stoppen.sh`. Protokolle: `~/.local/state/Wahlen2027/`.