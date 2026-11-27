# CasparCG: SDI-Ausgabe an Kayenne und Videowand

CasparCG ist hier nur der «Browser mit SDI-Ausgang»: Sein HTML-Producer spielt die Renderer-Seiten des
Grafik-Servers ab und gibt sie über die DeckLink Duo 2 aus. Gesteuert wird alles wie bisher über
Stream Deck, Controller und Grafik-Server. An CasparCG geht nur ein einziger Befehl pro Kanal
(`PLAY 1-10 [HTML] http://127.0.0.1:8795/renderer?quelle=casparcg`), und den schickt der Grafik-Server selbst.

```
Laptop (Browser, Stream Deck/Companion) ──Netz──► oGraf-Rechner :8795  Grafik-Server
                                                        │
                        CasparCG Kanal 1 ◄──────────────┤ /renderer       ──► Duo 2 Key + Fill ──► Kayenne
                        CasparCG Kanal 2 ◄──────────────┘ /renderer/wand  ──► Duo 2 Fill       ──► Videowand
```

## Belegung der DeckLink Duo 2 (Variante A, empfohlen)

| Anschluss | Signal | Ziel |
|---|---|---|
| SDI 1 | Key (Kanal 1) | Kayenne, Key-Eingang |
| SDI 2 | Fill (Kanal 1) | Kayenne, Fill-Eingang |
| SDI 3 | (Key Kanal 2, nicht benötigt) | – |
| SDI 4 | Fill (Kanal 2) | Videowand |
| REF   | Studio-Referenz (Black Burst oder Tri-Level) | **unbedingt anschliessen** |

Im Paarbetrieb liegt gemäss CasparCG-Dokumentation der Fill auf dem höheren und der Key auf dem tieferen
Anschluss eines Paars. **Beim ersten Test prüfen**: eine Bauchbinde einblenden und auf beiden Leitungen
nachsehen – Key = weisse Fläche auf Schwarz, Fill = die farbige Grafik.

### Desktop Video Setup (einmalig)
1. Blackmagic **Desktop Video** installieren (Treiber, unter Linux das `.deb` von Blackmagic).
2. *Desktop Video Setup* öffnen → DeckLink Duo 2 → Profil mit **Anschlusspaaren** wählen
   (zwei Geräte mit je zwei Anschlüssen). Danach den Rechner neu starten.
3. Bei beiden Geräten als Ausgang 1080i50 einstellen und den Referenzeingang aktivieren.


## Einstellungen am Kayenne

| Was | Einstellung | Warum |
|---|---|---|
| Format | 1080i50 (EBU 1080i/25) | muss dem CasparCG-Kanal entsprechen (`1080i5000`) |
| Key-Typ | Linear Key mit separatem Key-Signal (Key/Fill-Paar) | |
| **Shaped / Unshaped** | **Shaped** (Fill ist bereits mit Alpha verrechnet, «premultiplied») | sonst dunkle oder helle Säume an halbdurchsichtigen Kanten, besonders beim Ein-/Ausblenden |
| Clip / Gain | Standard (kein Zusatz-Clip) | sonst werden weiche Kanten hart |
| Timing | Eingänge im Referenztakt; CasparCG verzögert um wenige Frames | für Grafiken unkritisch |

Prüfen mit einer Grafik, die weich ein- und ausblendet (z. B. Bauchbinde): Saum dunkel → auf «Shaped»
stellen; Grafik zu durchsichtig/blass → «Unshaped» war richtig. Der Begriff heisst je nach Software-Stand
auch «Premultiplied»/«Additive».

## CasparCG installieren (Linux Mint)
- CasparCG Server von https://github.com/CasparCG/server/releases (Ubuntu-Paket passend zu Mint 22 = Ubuntu 24.04).
- Das Startskript `Wahlen 2027 starten.sh` findet CasparCG selbst, startet es mit dieser `casparcg.config`
  (Arbeitsordner `~/.local/state/Wahlen2027/casparcg/`) und hält es am Laufen. Der Grafik-Server verbindet sich
  dann von selbst; im Menü erscheint die Lampe **CasparCG (SDI)**.

## Wenn etwas hängt
- Menü → **CasparCG (SDI) › neu laden** oder Stream-Deck-Taste mit `http://<rechner>:8795/sd/caspar/neu`:
  lädt die Renderer-Seiten in CasparCG neu. Was auf Sendung war, erscheint danach wieder.
- Stürzt CasparCG ab, startet das Startskript es neu, und der Grafik-Server lädt die Seiten automatisch.
- Protokolle: `~/.local/state/Wahlen2027/casparcg.log` und `grafik.log`.
