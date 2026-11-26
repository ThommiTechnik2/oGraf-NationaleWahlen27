# Komponenten – Grafiken Wahlen 2027

Alle Grafiken sind **EBU-oGraf-v1-Grafiken** (Manifest `*.ograf.json` + Web Component).
Sie laufen in jedem oGraf-fähigen Renderer. Zum Arbeiten ohne Fremdsoftware gibt es
hier einen eigenen kleinen Grafik-Server mit Renderer (für OBS) und Web-Controller
(Browser + Stream Deck XL).

```
Komponenten/
├── bauchbinde/                 oGraf-Grafik „Bauchbinde“ (Layer 2)
│   ├── bauchbinde.ograf.json
│   ├── graphic.mjs
│   ├── thumbnails/1920x1080.png
│   └── fonts/    ← SRF-Schrift auch hier ablegen
├── hochrechnung-national/      oGraf-Grafik „Hochrechnung National (Videowand)“ – Vollbild, Renderer «wand»
├── hochrechnung-schweiz/       oGraf-Grafik „Hochrechnung Schweiz (Insert)“ (Layer 1)
│   ├── hochrechnung-schweiz.ograf.json
│   ├── graphic.mjs             gleicher Code wie hochrechnung-kanton, nur die Lage (VERSATZ) ist anders
│   ├── wappen/CH.svg           Schweizer Kreuz
│   └── fonts/
├── hochrechnung-kanton/        oGraf-Grafik „Hochrechnung Kanton (Insert)“ (Layer 1)
│   ├── hochrechnung-kanton.ograf.json
│   ├── graphic.mjs
│   ├── thumbnails/1920x1080.png
│   ├── fonts/    ← SRF-Schrift hier ablegen (siehe fonts/LIESMICH.md)
│   └── wappen/   ← Kantonswappen ZH.svg … JU.svg (siehe wappen/LIESMICH.md)
└── _server/
    ├── grafik_server.py        oGraf-Server-API + Renderer + Controller (Port 8795)
    ├── renderer.html           Browserquelle für OBS
    ├── menu.html               Startseite: Zustand aller Teile, Links zu den Controllern
    ├── controller.html         Web-Controller Hochrechnung Kanton (26 Kantone + Befehle)
    ├── controller_schweiz.html Web-Controller Hochrechnung Schweiz
    ├── controller_bauchbinden.html  Web-Controller Bauchbinden
    ├── companion/              Companion-Konfiguration (Stream Deck XL) und Generator
    └── test/                   End-to-End-Tests (Playwright)
```

## Starten

Zwei Terminal-Fenster:

```bash
# 1. Daten-API (aus Daten/Datenbank)
cd ".../Wahlen 2027/Daten/Datenbank"
python3 wahlen_api.py                 # Port 8790; zum Testen mit 2023: --jahr 2023

# 2. Grafik-Server (aus Komponenten/_server)
cd ".../Wahlen 2027/Komponenten/_server"
python3 grafik_server.py              # Port 8795; zum Testen mit 2023: --jahr 2023
```

| Was | Adresse |
|---|---|
| **OBS Browserquelle** (1920×1080, Hintergrund transparent) | `http://127.0.0.1:8795/renderer` |
| Renderer mit Raster zum Ausrichten | `http://127.0.0.1:8795/renderer?test=1` |
| **Menü (Startseite, Zustand, Links zu allen Controllern)** | `http://127.0.0.1:8795/` |
| **Web-Controller Hochrechnung Kanton** | `http://127.0.0.1:8795/controller` |
| **Web-Controller Hochrechnung Schweiz** | `http://127.0.0.1:8795/controller/schweiz` |
| **Videowand (Vollbild, eigener Ausgang)** | `http://127.0.0.1:8795/renderer/wand` |
| **Web-Controller Videowand National** | `http://127.0.0.1:8795/controller/national` |
| **Web-Controller Bauchbinden** | `http://127.0.0.1:8795/controller/bauchbinden` |
| oGraf-Server-API | `http://127.0.0.1:8795/ograf/v1/` |

In OBS bei der Browserquelle „Seite neu laden, wenn Szene aktiv wird“ **aus** lassen.

Soll das Stream Deck oder ein zweiter Rechner zugreifen: `--host 0.0.0.0` und statt
`127.0.0.1` die IP des Grafikrechners verwenden.

Wichtige Optionen von `grafik_server.py`:

| Option | Standard | Bedeutung |
|---|---|---|
| `--jahr` | 2027 | Wahljahr für die Daten |
| `--sprache` | de | de / fr / it (Titel) |
| `--nachkommastellen` | 1 | Prozentwerte mit 0 oder 1 Stelle |
| `--intervall` | 10 | Sekunden; auf Sendung werden neue Daten automatisch nachgeführt (nur bei Änderung) |
| `--layer` | 1 | Ebene der Hochrechnung Kanton |
| `--seiten-schweiz` | – | Parteien je Seite Hochrechnung Schweiz, z. B. `3,3,2,3` (leer: je 3; auch im Controller änderbar) |
| `--layer-bauchbinde` | 2 | Ebene der Bauchbinden (beide Grafiken können gleichzeitig stehen) |
| `--ograf-api` | – | Anderen oGraf-Server steuern (z. B. SuperFly ograf-server) statt des eigenen |

## Ablauf Hochrechnung Kanton

1. Kanton wählen → Vorschau der Daten im Controller.
2. **EIN** → Boxen fahren von rechts ein, Titel blendet ein (Sitze, Seite 1).
3. **WEITER** → Sitze ⇒ Prozent ⇒ nächste Seite (max. 3 Parteien pro Seite) …
   nach dem letzten Schritt blendet die Grafik selbst aus.
4. **ZURÜCK** → einen Schritt zurück. **AUS** → ausblenden.
5. Anderer Kanton während EIN → wird direkt gewechselt (aus, dann ein).
6. Daten werden bei jeder Kantonswahl und bei EIN frisch geholt, auf Sendung alle `--intervall` s nachgeführt.
   Von Hand: `/sd/neu` (im Web-Controller und auf dem Stream Deck nicht mehr als Taste).
7. **LEEREN** → Ebene hart leeren (Notfall, ohne Animation).

Datenquelle, automatisch gewählt (`/api/nr/kanton-insert`):
freigegebene **Hochrechnung** aus Grist (Tabelle Hochrechnungen, Spalte *Kanton*) →
sonst **Resultat**, wenn der Kanton abgeschlossen ist → sonst **Zwischenstand** (nur Prozent).

Tastatur im Web-Controller: Enter = EIN, Leertaste = WEITER, ← = ZURÜCK, Esc = AUS.

## Stream Deck XL mit Companion

Konfiguration für **Bitfocus Companion 5.x**: `_server/companion/Wahlen2027.companionconfig` – der Export aus
Companion mit dem aktuellen Stand (Anleitung: `_server/companion/LIESMICH.md`). **Seite 1 «Menu»** führt zu
Kanton (2), Schweiz (3), Bauchbinden (4) und Videowand (5); jede dieser Seiten hat eine Taste **MENU** zurück. Beschriftung und
Farben kommen live vom Server (gewählt blau, auf Sendung rot, nächster Start orange). Die Web-Controller haben
dieselbe Belegung; MENU führt dort zur Menü-Seite im Browser.

Für die Beschriftung liefert der Server kurze Textwerte: `/sd/wert/<name>`, z. B. `kt_kanton`, `kt_onair`,
`ch_anzeige`, `ch_seite_3`, `bb_slot_5`, `bb_slot_onair` (Liste in `_server/companion/companion_konfig.py`).

## Stream Deck XL (8 × 4 Tasten) – Seite Hochrechnung Kanton

Belegung wie im Web-Controller (BFS-Reihenfolge):

| | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| **Reihe 1** | ZH | BE | LU | UR | SZ | OW | NW | GL |
| **Reihe 2** | ZG | FR | SO | BS | BL | SH | AR | AI |
| **Reihe 3** | SG | GR | AG | TG | TI | VD | VS | NE |
| **Reihe 4** | GE | JU | EIN | WEITER | ZURÜCK | AUS | MENU | LEEREN |

Jede Taste ist ein einfacher HTTP-GET – in **Bitfocus Companion** mit dem Modul
„Generic: HTTP“ (Aktion *GET*), im Elgato-Programm mit einem „Website/API“-Plugin:

| Taste | URL |
|---|---|
| Kanton (Beispiel BS) | `http://127.0.0.1:8795/sd/kanton/BS` |
| EIN | `http://127.0.0.1:8795/sd/ein` |
| WEITER | `http://127.0.0.1:8795/sd/weiter` |
| ZURÜCK | `http://127.0.0.1:8795/sd/zurueck` |
| AUS | `http://127.0.0.1:8795/sd/aus` |
| (Daten neu, ohne Taste) | `http://127.0.0.1:8795/sd/neu` |
| LEEREN | `http://127.0.0.1:8795/sd/leeren` |
| Status als Text (für Tasten-Feedback) | `http://127.0.0.1:8795/sd/status?format=text` |
| Status als JSON | `http://127.0.0.1:8795/sd/zustand` |

## Hochrechnung Schweiz

Gleicher Aufbau wie die Kantons-Hochrechnung, mit Schweizer Kreuz, nur Parteistärke (ein Schritt pro Seite).
Reihenfolge: stärkste Partei zuerst, dann absteigend, «Übrige» immer am Schluss.

Daten (`/api/nr/schweiz-insert`): neueste freigegebene Hochrechnung Schweiz aus Grist (Tabelle *Hochrechnungen*,
Spalte *Kanton* leer oder 0); gibt es mehrere Institute, die neueste – oder fest per Feld *Institut* im Controller.
Ist die Wahl abgeschlossen und keine Hochrechnung freigegeben: das Schlussresultat.

**Fortsetzen nach kurzfristigem Ausblenden:** Wird mitten im Ablauf ausgeblendet (AUS, auch AUS sofort oder LEEREN),
beginnt die nächste Einblendung mit der Seite, die als Nächstes gekommen wäre. Der Controller zeigt das orange an
(Taste EIN: «ab Seite 3»). Wieder von vorne geht es
- nach der letzten Seite (WEITER am Schluss blendet aus),
- wenn auf der letzten Seite ausgeblendet wurde,
- sobald eine neue Hochrechnung (Nummer, Institut) oder das Resultat kommt,
- mit **VON VORNE**.

Ändert sich die Reihenfolge durch neue Zahlen derselben Hochrechnung, wird die vorgemerkte Seite über ihre
erste Partei wiedergefunden. Neue Zahlen werden auf Sendung automatisch nachgeführt.

Hochrechnung Kanton und Schweiz stehen am selben Platz (Layer 1): Wird die eine eingeblendet, blendet die
andere vorher aus – die Schweiz merkt sich dabei ihre Seite.

### Stream Deck XL – Seite Hochrechnung Schweiz

| | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| **Reihe 1** | EIN | WEITER | ZURÜCK | AUS | VON VORNE | DATEN NEU | LEEREN | Anzeige |
| **Reihe 2** | SEITE 1 | SEITE 2 | … | | | | | SEITE 8 |
| **Reihe 3** | frei | | | | | | | |
| **Reihe 4** | ◀ KANTON | | | | | | | MENU |

| Taste | URL (GET) |
|---|---|
| EIN / WEITER / ZURÜCK | `http://127.0.0.1:8795/sd/ch/ein`, `/sd/ch/weiter`, `/sd/ch/zurueck` |
| AUS / AUS sofort | `/sd/ch/aus`, `/sd/ch/aus?sofort=1` |
| VON VORNE | `/sd/ch/vonvorne` |
| SEITE n (auf Sendung springen, sonst vormerken) | `/sd/ch/seite/<n>` – mit `?ein=1` gleich einblenden |
| DATEN NEU / LEEREN | `/sd/ch/neu`, `/sd/ch/leeren` |
| Anzeige (Text: «ON AIR / Seite 2» bzw. «bereit / ab Seite 3») | `/sd/ch/status?format=text` |
| Seitenaufteilung | `/sd/ch/seiten?wert=3,3,2,3` |

## Videowand: Hochrechnung National

Vollbild-Grafik für die Studio-Videowand (wie SRF 2023 um 16 Uhr): Titel «Hochrechnung Nationalrat» mit Schweizer
Kreuz, darunter die Parteien als Balken, **Partei für Partei** – jeder WEITER lässt den nächsten Balken wachsen,
die neueste Partei ist grösser beschriftet. Nach 6 Parteien leert der nächste Schritt die Fläche und beginnt
Seite 2 (EVP, EDU, PdA/Sol., Lega, Übrige …). Alle Balken im selben Massstab wie die stärkste Partei.

- **Eigener Ausgang:** Renderer **`/renderer/wand`** (Renderer-Id «wand»). Die Seite im Vollbild auf dem
  Wand-Zuspieler öffnen, als zweite OBS-Browserquelle in einer eigenen Szene (Vollbild-Projektor auf die Wand),
  oder auf einem eigenen Rechner. Der Hauptausgang `/renderer` zeigt die Grafik nicht.
- **Reihenfolge** nach Stärke der letzten Wahl (wie SRF: SVP, SP, FDP, Mitte, Grüne, GLP …), Übrige am Schluss –
  die Parteien springen also nicht, wenn sich die Zahlen ändern.
- **Fortsetzen** nach Ausblenden wie bei der Schweiz, aber mit der nächsten *Partei*.
- **Daten:** dieselben wie die Hochrechnung Schweiz (`/api/nr/schweiz-insert?sort=vorwahl`).
- Seitenaufteilung: `--seiten-national 6,5` bzw. im Controller.

Stream Deck: `/sd/nat/ein`, `/sd/nat/weiter`, `/sd/nat/zurueck`, `/sd/nat/aus`, `/sd/nat/vonvorne`,
`/sd/nat/seite/<n>`, `/sd/nat/leeren`, `/sd/nat/status?format=text`. Companion: Seite 5 «Wahlen Videowand».

### «±» statt Vorzeichen (Fehlerbereich)

In den SRF-Grafiken 2023 steht bei kleinen Veränderungen «±0.4%» statt «+0.4%». Das passt genau dazu, dass die
Veränderung kleiner ist als der Fehlerbereich der Hochrechnung. Die Grafiken machen das jetzt auch – aber nur,
wenn in Grist bei der Hochrechnung die Spalte **«± Prozentpunkte»** ausgefüllt ist. Ohne Angabe: normales Vorzeichen.
Gilt für die Inserts Kanton/Schweiz und die Videowand.

## Bauchbinden

**Quellen** (oben rechts im Controller umschaltbar):

| Quelle | Inhalt |
|---|---|
| Grist | Tabelle *Bauchbinden*, nur Zeilen mit «Freigegeben». Filter nach Kategorie. Ist Zeile 2 leer, aber Partei/Kanton gesetzt, steht dort z. B. «SVP/ZH». |
| Gewählte Nationalrat | Aus den BFS-Daten, pro Kanton: «Nationalrätin SP/BS» bzw. «neu gewählt, SVP/BE» |
| Gewählte Ständerat | ebenso, «Ständerätin SP/BS» |
| Freitext | Feld unten rechts, für Spontanes |

Die Liste lädt sich alle `--intervall` Sekunden neu – in Grist freigegebene Zeilen erscheinen also von selbst
(nach `grist_sync.py pull` bzw. mit laufendem `grist_sync.py loop`).

**Bedienung:** Eintrag wählen → **EIN**. Ist eine Bauchbinde auf Sendung und man wählt einen anderen Eintrag,
wird direkt gewechselt (alte aus, neue ein). **AUTO-AUS** schaltet durch aus → 5 s → 8 s → 12 s.
Tastatur: Enter = EIN, Esc = AUS, ↑/↓ = Auswahl, Leertaste = EIN und gleich den nächsten Eintrag wählen
(für Gästerunden). Doppelklick in der Liste = sofort EIN.

Ohne Zeile 2 steht die rote Box allein auf der Grundlinie. Sehr lange Texte werden schmaler gesetzt
(Box höchstens 1720 px breit).

### Stream Deck XL – Seite Bauchbinden

| | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| **Reihe 1–3** | Eintrag 1 | 2 | … | | | | | 8 / 16 / 24 |
| **Reihe 4** | SEITE ▶ | ▲ VORH. | ▼ NÄCHSTE | EIN | AUS | AUTO-AUS | MENU | LEEREN |

| Taste | URL (GET) |
|---|---|
| Eintrag n der aktuellen Seite wählen | `http://127.0.0.1:8795/sd/bb/slot/<n>` (n = 1–24) |
| … wählen und sofort EIN | `http://127.0.0.1:8795/sd/bb/slot/<n>?ein=1` |
| Beschriftung für Taste n (Text) | `http://127.0.0.1:8795/sd/bb/slottext/<n>` |
| Seite vor / zurück | `/sd/bb/seite/vor`, `/sd/bb/seite/zurueck` |
| Auswahl vor / zurück | `/sd/bb/naechste`, `/sd/bb/vorherige` |
| EIN / AUS / EIN-AUS umschalten | `/sd/bb/ein`, `/sd/bb/aus`, `/sd/bb/umschalten` |
| EIN und nächsten wählen | `/sd/bb/ein-weiter` |
| Auto-Aus durchschalten / fest | `/sd/bb/auto/zyklus`, `/sd/bb/auto/8` (0 = aus) |
| Quelle | `/sd/bb/quelle/grist`, `/sd/bb/quelle/nr/BS`, `/sd/bb/quelle/sr/BS` |
| Liste neu laden | `/sd/bb/liste` |
| Leeren (hart) | `/sd/bb/leeren` |
| Status (Text: ON AIR / bereit + Name) | `/sd/bb/status?format=text` |

In Companion lässt sich die Beschriftung der 24 Tasten mit `slottext/<n>` als Variable holen
(Modul „Generic: HTTP“, Feedback/Variable per GET) – so stehen die Namen auf den Tasten.

## oGraf-Konformität

- Beide Manifeste gegen das offizielle EBU-Schema geprüft (0 Fehler); Datenfelder als GDD-Typen
  (Kantonsauswahl als `select`, Farben als `color-rrggbb`).
- Hochrechnung Schweiz: `stepCount: -1`; das Fortsetzen macht der Controller mit `playAction {goto: n}` –
  die Grafik selbst bleibt zustandslos und funktioniert so mit jedem oGraf-Controller.
- Bauchbinde: `stepCount: 1` – playAction blendet ein, ein weiterer playAction oder stopAction blendet aus,
  updateAction tauscht den Text auch auf Sendung (Boxen passen ihre Breite an).
- Web Component mit `load`, `dispose`, `playAction` (goto/delta, `skipAnimation`),
  `stopAction`, `updateAction`, `customAction`; alle Aufrufe werden in eine Warteschlange
  gestellt und liefern `{statusCode}` zurück.
- `stepCount: -1` (Anzahl Schritte hängt von den Parteien ab), Echtzeit-Rendering.
- Der eigene Server implementiert die Teile der oGraf-Server-API, die der Controller
  braucht (load, playAction, stopAction, updateAction, customActions, clear).

Getestet mit dem eigenen Server und Chrome als Renderer. Mit dem SuperFly-Referenzserver
(ograf-server) wurde noch **nicht** getestet.

## Noch offen

- SRF-Schrift → `hochrechnung-kanton/fonts/`, `hochrechnung-schweiz/fonts/` und `bauchbinde/fonts/` (bis dahin Ersatzschrift).
- Kantonswappen → `hochrechnung-kanton/wappen/` (fehlen sie, bleibt der Platz leer).
- Touch-Oberfläche für die Moderation (später).

## Test

```bash
cd _server/test
python3 test_kette.py <db.sqlite> 2023 <ausgabeordner> [hintergrund.png]
python3 test_bauchbinde.py <db.sqlite> 2023 <ausgabeordner> [hintergrund.png]
python3 test_schweiz.py <kopie-der-db-mit-hochrechnung.sqlite> 2023 <ausgabeordner> [hintergrund.png]
```
Startet API und Grafik-Server, steuert alles über `/sd/...` und speichert Bilder pro Schritt.
