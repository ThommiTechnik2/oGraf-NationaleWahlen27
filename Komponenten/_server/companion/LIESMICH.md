# Companion-Konfiguration – Stream Deck XL

> **Massgebend ist `Wahlen2027.companionconfig`** – der Export aus Companion 5.1.3 mit dem aktuellen Stand der
> Bedienung: **Seite 1 «Menu»** (Tasten zu Kanton, Schweiz, Bauchbinden, Videowand) und die Seiten 2–5, jede mit einer
> Taste **MENU** zurück. Diese Datei nicht überschreiben; nach Änderungen in Companion wieder hierhin exportieren.
>
> `companion_konfig.py` war der Generator für die erste Version (ohne Menü). Er schreibt jetzt nach
> `Wahlen2027_generiert.companionconfig` und wird nur noch als Vorlage gebraucht. Neue Seiten werden in den
> Companion-Export eingefügt, damit nichts von der Bedienung verloren geht.
>
> 22.11.2026: Seite 5 «Wahlen Videowand» und die Menü-Taste VIDEOWAND eingefügt (12 Variablen `nat_…` und die
> passenden Abfragen im Trigger). Der Stand davor liegt als `Wahlen2027_vor_Videowand.companionconfig` daneben.

Läuft Companion einmal auf einem anderen Rechner als der Grafik-Server: in Companion bei den Tasten bzw. im Trigger
`127.0.0.1` durch die IP des Grafik-Rechners ersetzen (oder Bescheid geben, dann passe ich den Export an).

## Inhalt

| Seite | Tasten |
|---|---|
| **Menu** (1) | BAUCHBINDEN, KANTON, SCHWEIZ, VIDEOWAND – springt auf die jeweilige Seite |
| **Wahlen Kanton** (2) | 26 Kantone (blau = gewählt, rot = auf Sendung), EIN, WEITER, ZURÜCK, AUS, MENU, LEEREN |
| **Wahlen Schweiz** (3) | EIN, WEITER, ZURÜCK, AUS, VON VORNE, DATEN NEU, LEEREN, Anzeige · SEITE 1–8 mit Parteien (rot = auf Sendung, orange = nächster Start) · ◀ KANTON, MENU |
| **Wahlen Videowand** (5) | wie Schweiz, für die Videowand National: EIN, WEITER (nächste Partei), ZURÜCK, AUS, VON VORNE, DATEN NEU, LEEREN, Anzeige («ab FDP») · SEITE 1–8 mit Parteien · MENU |
| **Wahlen Bauchbinden** (4) | 24 Namen aus der Liste (blau = gewählt, rot = auf Sendung) · SEITE ▶, ▲ VORH., ▼ NÄCHSTE, EIN, AUS, AUTO-AUS, MENU, LEEREN |

Dazu: Verbindung **Wahlen2027** (Modul «Generic HTTP»), 44 Benutzervariablen und ein Trigger
**«Wahlen 2027: Zustand holen»**, der jede Sekunde Beschriftungen und Farben vom Grafik-Server holt.
Läuft der Grafik-Server nicht, bleiben die Tasten einfach grau – nichts stürzt ab.

## Importieren (Companion-Weboberfläche → Import / Export → Import)

Diese Companion-Instanz gehört nur der Wahlgrafik – deshalb einfach der **vollständige Import**:

1. Datei `Wahlen2027.companionconfig` wählen.
2. Reiter **Full Import** (vollständiger Import): alle Bereiche auf **Import** bzw. **Reset** lassen und importieren.
   Danach liegen die drei Seiten auf **Seite 1, 2 und 3**, die Verbindung *Wahlen2027*, die Benutzervariablen
   und der Trigger sind angelegt.
3. Die **Elgato-Software beenden** (sie belegt das Stream Deck sonst) und in Companion unter *Surfaces*
   beim Stream Deck XL die **Startseite 1** einstellen.

Muss die Konfiguration später neu eingespielt werden (z. B. nach Änderungen am Generator): genauso, der
vollständige Import ersetzt den alten Stand.

## Prüfen

Grafik-Server läuft → nach etwa einer Sekunde stehen auf der Bauchbinden-Seite die Namen, auf der
Schweiz-Seite die Parteien je Seite. Kanton antippen → Taste wird blau, EIN → rot.
