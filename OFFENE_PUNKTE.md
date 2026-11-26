# Wahlen 2027 – Offene Punkte

Stand: 22.11.2026

## ⚠️ Mit den Statistik-Leuten klären: «±» statt Vorzeichen

**Beobachtung** in den SRF-Grafiken der 1. Hochrechnung 2023 (16 Uhr, Videowand und Insert Schweiz):

| Partei | Wert | Veränderung zu 2019 | angezeigt |
|---|---|---|---|
| SVP | 29.0 % | +3.4 | **+3.4%** |
| SP | 17.2 % | +0.4 | **±0.4%** |
| FDP | 14.6 % | −0.5 | **-0.5%** |
| Mitte | 14.7 % | +0.9 | **+0.9%** |
| Grüne | 9.1 % | −4.1 | **-4.1%** |
| GLP | 7.1 % | −0.7 | **-0.7%** |
| EVP | 2.0 % | −0.1 | **±0.1%** |
| EDU | 1.3 % | +0.3 | **±0.3%** |
| PdA/Sol. | 0.8 % | −0.2 | **±0.2%** |
| Lega | 0.5 % | −0.3 | **±0.3%** |
| Übrige | 3.7 % | | **+0.9%** |

**Vermutung:** «±» steht, wenn die Veränderung kleiner ist als der Fehlerbereich (Unsicherheit) der Hochrechnung,
also nicht signifikant ist. Das ist aus den Zahlen abgeleitet, nicht bestätigt.

**Fragen an die Statistik:**
1. Stimmt die Regel? Und gilt sie nur für Hochrechnungen oder auch für Teilresultate?
2. Woher kommt der Fehlerbereich pro Partei – liefert gfs.bern ihn mit jeder Hochrechnung?
3. Grenzfall: Veränderung *gleich* gross wie der Fehlerbereich – «±» oder Vorzeichen?
4. Übrige: SRF zeigte +0.9, nach BFS-Zahlen 2019 wären es +1.9 (andere Abgrenzung von «Übrige»?).

**Stand in der Anlage:** schon eingebaut, aber nur aktiv, wenn in Grist (Tabelle *Hochrechnungen*) die Spalte
**«± Prozentpunkte»** ausgefüllt ist. Ohne Wert: normales Vorzeichen. Grenzfall heute: gleich gross → «±».
Gilt für Insert Kanton, Insert Schweiz und Videowand National. Anpassung nach der Antwort: Funktion
`diff_unsicher` in `Daten/Datenbank/wahlen_api.py` (eine Stelle).

---

## Weitere offene Punkte

- [ ] **SRF-Schrift** in `fonts/` jeder Grafik legen (bauchbinde, hochrechnung-kanton, hochrechnung-schweiz,
      hochrechnung-national) – danach Abstände prüfen
- [ ] **Kantonswappen** `ZH.svg` … `JU.svg` nach `Komponenten/hochrechnung-kanton/wappen/`
- [ ] **Videowand:** eigene Parteifarben nötig? (SP war 2023 auf der Wand pinker als im Insert)
- [ ] **Companion:** Seite für die Videowand (vom selben Stream Deck aus oder von einem anderen Platz?)
- [ ] **BFS-Schnittstelle 2027:** Anfang 2027 definieren; am 05.07.2027 die BFS-Daten prüfen (Kalender-Eintrag)
- [ ] **Soll-Sitze 2027** mit dem Text der Verordnung abgleichen (`Daten/sitze_nationalrat_2023_2027.csv`)
- [ ] **Ständerat SH:** Korrektur Neuwahl 2025 in Grist (*SR_Korrekturen*), Name bestätigen
- [ ] **Touch-Oberfläche** für die Moderation (später)
- [x] Wahlbeteiligung (Videowand) – gebaut
- [x] Auszählungsstand (Videowand, Karte) – gebaut. Kartengrundlage: swisstopo/BFS generalisierte Grenzen (npm «swiss-maps», Stand 2026). Quellenangabe on air nötig? Mit Grafik/Recht klären
- [ ] Noch nicht gebaut: Hochrechnung Kanton (Monitor), QR-Insert «srf.ch/wahlen»
- [ ] Recherche: Parteifamilien in `Daten/Datenbank/parteifamilie.csv` mit der Statistik prüfen (v. a. historische Kürzel mit *, Demokraten, Kleinparteien). Nach Änderungen: `python3 historie_laden.py --nur familien`
