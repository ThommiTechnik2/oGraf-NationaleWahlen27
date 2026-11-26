-- Ansichten für die Grafiken. Immer: aktuelles Jahr (wahl.wahl_jahr) gegen wahl.vorwahl_jahr.
-- Die oGraf-Komponenten lesen nur diese Ansichten, nie die Rohtabellen.

DROP VIEW IF EXISTS v_sitze_kanton;
CREATE VIEW v_sitze_kanton AS
SELECT w.wahl_jahr, k.kanton_nummer, k.kuerzel, k.name_de,
       s.nr_sitze                               AS sitze,
       sv.nr_sitze                              AS sitze_vorwahl,
       s.nr_sitze - sv.nr_sitze                 AS sitze_veraenderung,
       CASE WHEN s.nr_sitze = 1 THEN 'Majorz' ELSE 'Proporz' END AS wahlverfahren,
       s.geprueft
FROM wahl w
JOIN kanton_sitze s  ON s.wahl_jahr = w.wahl_jahr
JOIN kanton k        ON k.kanton_nummer = s.kanton_nummer
LEFT JOIN kanton_sitze sv ON sv.wahl_jahr = w.vorwahl_jahr AND sv.kanton_nummer = s.kanton_nummer;

-- «x von y Sitzen vergeben» pro Kanton, auch im Zwischenstand
DROP VIEW IF EXISTS v_kanton_fortschritt;
CREATE VIEW v_kanton_fortschritt AS
SELECT s.wahl_jahr, k.kanton_nummer, k.kuerzel, k.name_de,
       s.nr_sitze AS sitze_total,
       COALESCE(st.kanton_abgeschlossen, 0) AS abgeschlossen,
       CASE WHEN st.kanton_abgeschlossen = 1
            THEN (SELECT COUNT(*) FROM nr_kandidat c WHERE c.wahl_jahr = s.wahl_jahr
                    AND c.kanton_nummer = s.kanton_nummer AND c.gewaehlt = 1)
            ELSE 0 END AS sitze_vergeben,
       st.gemeinden_abgeschlossen, st.gemeinden_total
FROM kanton_sitze s
JOIN kanton k ON k.kanton_nummer = s.kanton_nummer
LEFT JOIN nr_stand_kanton st ON st.wahl_jahr = s.wahl_jahr AND st.kanton_nummer = s.kanton_nummer;

-- Parteien Schweiz: Sitze und Stärke mit Veränderung gegenüber Vorwahl (aus eigenen Daten)
DROP VIEW IF EXISTS v_partei_ch;
CREATE VIEW v_partei_ch AS
SELECT w.wahl_jahr, p.partei_id, p.kurz_de, p.kurz_fr, p.kurz_it,
       COALESCE(p.anzeige_de, p.kurz_de) AS name_de, COALESCE(p.anzeige_fr, p.kurz_fr) AS name_fr,
       COALESCE(p.anzeige_it, p.kurz_it) AS name_it, p.farbe, p.reihenfolge,
       a.sitze,
       COALESCE(v.sitze, a.bfs_letzte_wahl_sitze) AS sitze_vorwahl,
       a.sitze - COALESCE(v.sitze, a.bfs_letzte_wahl_sitze) AS sitze_veraenderung,
       a.partei_staerke,
       COALESCE(v.partei_staerke, a.bfs_letzte_wahl_partei_staerke) AS staerke_vorwahl,
       ROUND(a.partei_staerke - COALESCE(v.partei_staerke, a.bfs_letzte_wahl_partei_staerke), 2) AS staerke_veraenderung,
       CASE WHEN v.partei_id IS NOT NULL THEN 'eigene Daten'
            WHEN a.bfs_letzte_wahl_sitze IS NOT NULL THEN 'BFS-Vergleichswert' END AS vorwahl_quelle,
       a.partei_rang
FROM wahl w
JOIN nr_partei_ch a ON a.wahl_jahr = w.wahl_jahr
JOIN partei p       ON p.partei_id = a.partei_id
LEFT JOIN nr_partei_ch v ON v.wahl_jahr = w.vorwahl_jahr AND v.partei_id = a.partei_id;

-- Parteien pro Kanton mit Veränderung
DROP VIEW IF EXISTS v_partei_kanton;
CREATE VIEW v_partei_kanton AS
SELECT w.wahl_jahr, k.kanton_nummer, k.kuerzel, p.partei_id, p.kurz_de,
       COALESCE(p.anzeige_de, p.kurz_de) AS name_de, COALESCE(p.anzeige_fr, p.kurz_fr) AS name_fr,
       COALESCE(p.anzeige_it, p.kurz_it) AS name_it, p.farbe, p.reihenfolge,
       a.sitze,
       COALESCE(v.sitze, a.bfs_letzte_wahl_sitze) AS sitze_vorwahl,
       a.sitze - COALESCE(v.sitze, a.bfs_letzte_wahl_sitze) AS sitze_veraenderung,
       a.stimmen, a.partei_staerke,
       COALESCE(v.partei_staerke, a.bfs_letzte_wahl_partei_staerke) AS staerke_vorwahl,
       ROUND(a.partei_staerke - COALESCE(v.partei_staerke, a.bfs_letzte_wahl_partei_staerke), 2) AS staerke_veraenderung,
       a.partei_rang,
       COALESCE(st.kanton_abgeschlossen, 0) AS kanton_abgeschlossen
FROM wahl w
JOIN nr_partei_kanton a ON a.wahl_jahr = w.wahl_jahr
JOIN kanton k  ON k.kanton_nummer = a.kanton_nummer
JOIN partei p  ON p.partei_id = a.partei_id
LEFT JOIN nr_partei_kanton v ON v.wahl_jahr = w.vorwahl_jahr AND v.kanton_nummer = a.kanton_nummer AND v.partei_id = a.partei_id
LEFT JOIN nr_stand_kanton st ON st.wahl_jahr = w.wahl_jahr AND st.kanton_nummer = a.kanton_nummer;

-- Teilresultat eines Kantons aus den bereits gemeldeten Gemeinden (für nicht abgeschlossene Kantone)
DROP VIEW IF EXISTS v_partei_kanton_teilresultat;
CREATE VIEW v_partei_kanton_teilresultat AS
SELECT g.wahl_jahr, g.kanton_nummer, g.partei_id,
       SUM(g.stimmen) AS stimmen,
       ROUND(100.0 * SUM(g.stimmen) / NULLIF((SELECT SUM(x.stimmen) FROM nr_partei_gemeinde x
              WHERE x.wahl_jahr = g.wahl_jahr AND x.kanton_nummer = g.kanton_nummer), 0), 2) AS staerke_teilresultat,
       COUNT(DISTINCT g.gemeinde_nummer) AS gemeinden_gemeldet
FROM nr_partei_gemeinde g
WHERE g.stimmen IS NOT NULL
GROUP BY g.wahl_jahr, g.kanton_nummer, g.partei_id;

-- Gewählte Nationalrät:innen mit bisherig/neu und Partei
DROP VIEW IF EXISTS v_nr_gewaehlte;
CREATE VIEW v_nr_gewaehlte AS
SELECT c.wahl_jahr, k.kuerzel AS kanton, c.kanton_nummer, c.vorname, c.name, c.geschlecht, c.geburtsjahr,
       c.beruf, c.wohnort, COALESCE(p.anzeige_de, p.kurz_de) AS partei, p.partei_id, p.farbe,
       c.stimmen, c.liste_nummer_kanton,
       CASE WHEN c.kandidat_status_id = 2 THEN 'bisherig' ELSE 'neu' END AS status
FROM nr_kandidat c
JOIN kanton k ON k.kanton_nummer = c.kanton_nummer
LEFT JOIN partei p ON p.partei_id = c.partei_id
WHERE c.gewaehlt = 1;

-- Abgewählte: 2023 gewählt (Vorwahl), im aktuellen Jahr wieder angetreten, aber nicht gewählt
DROP VIEW IF EXISTS v_nr_abgewaehlte;
CREATE VIEW v_nr_abgewaehlte AS
SELECT w.wahl_jahr, k.kuerzel AS kanton, c.vorname, c.name, COALESCE(p.anzeige_de, p.kurz_de) AS partei, c.stimmen
FROM wahl w
JOIN nr_kandidat c ON c.wahl_jahr = w.wahl_jahr AND c.kandidat_status_id = 2 AND c.gewaehlt = 0
JOIN kanton k ON k.kanton_nummer = c.kanton_nummer
LEFT JOIN partei p ON p.partei_id = c.partei_id
JOIN nr_stand_kanton st ON st.wahl_jahr = c.wahl_jahr AND st.kanton_nummer = c.kanton_nummer AND st.kanton_abgeschlossen = 1;

-- Ständerat: gewählte Personen (letzter Wahlgang je Kanton), mit redaktionellen Korrekturen
DROP VIEW IF EXISTS v_sr_gewaehlte;
CREATE VIEW v_sr_gewaehlte AS
SELECT s.wahl_jahr, k.kuerzel AS kanton, s.kanton_nummer, s.vorname, s.name, s.geschlecht,
       COALESCE(p.anzeige_de, p.kurz_de) AS partei, s.partei_id, s.stimmen, s.wahlgang,
       CASE WHEN s.kandidat_status_id = 2 THEN 'bisherig' ELSE 'neu' END AS status,
       NULL AS korrektur
FROM sr_kandidat s
JOIN kanton k ON k.kanton_nummer = s.kanton_nummer
LEFT JOIN partei p ON p.partei_id = s.partei_id
WHERE s.gewaehlt = 1
  AND NOT EXISTS (SELECT 1 FROM sr_korrektur x WHERE x.wahl_jahr = s.wahl_jahr AND x.kanton_nummer = s.kanton_nummer
                  AND x.name = s.name AND x.vorname = s.vorname AND x.gewaehlt = 0)
UNION ALL
SELECT x.wahl_jahr, k.kuerzel, x.kanton_nummer, x.vorname, x.name, NULL, COALESCE(p.anzeige_de, p.kurz_de), x.partei_id, NULL, NULL,
       'neu', x.grund
FROM sr_korrektur x
JOIN kanton k ON k.kanton_nummer = x.kanton_nummer
LEFT JOIN partei p ON p.partei_id = x.partei_id
WHERE x.gewaehlt = 1;

-- Ständerat: Sitze pro Partei mit Veränderung
DROP VIEW IF EXISTS v_sr_partei;
CREATE VIEW v_sr_partei AS
WITH a AS (SELECT wahl_jahr, partei_id, partei, COUNT(*) AS sitze FROM v_sr_gewaehlte GROUP BY 1, 2, 3)
SELECT w.wahl_jahr, a.partei_id, a.partei, a.sitze,
       v.sitze AS sitze_vorwahl, a.sitze - COALESCE(v.sitze, 0) AS sitze_veraenderung
FROM wahl w
JOIN a ON a.wahl_jahr = w.wahl_jahr
LEFT JOIN a v ON v.wahl_jahr = w.vorwahl_jahr AND v.partei_id = a.partei_id;

DROP VIEW IF EXISTS v_beteiligung_kanton;
CREATE VIEW v_beteiligung_kanton AS
SELECT w.wahl_jahr, b.nummer AS kanton_nummer, k.kuerzel, b.wahlbeteiligung,
       v.wahlbeteiligung AS beteiligung_vorwahl,
       ROUND(b.wahlbeteiligung - v.wahlbeteiligung, 2) AS veraenderung
FROM wahl w
JOIN nr_beteiligung b ON b.wahl_jahr = w.wahl_jahr AND b.ebene = 'kanton'
JOIN kanton k ON k.kanton_nummer = b.nummer
LEFT JOIN nr_beteiligung v ON v.wahl_jahr = w.vorwahl_jahr AND v.ebene = 'kanton' AND v.nummer = b.nummer;

-- Hochrechnungen: jeweils die neueste freigegebene Hochrechnung pro Institut und Rat,
-- mit Vergleich zum Resultat der Vorwahl
DROP VIEW IF EXISTS v_hochrechnung_aktuell;
CREATE VIEW v_hochrechnung_aktuell AS
WITH letzte AS (
  SELECT wahl_jahr, rat, institut, MAX(nummer) AS nummer
  FROM hochrechnung WHERE freigegeben = 1 AND kanton_nummer IS NULL GROUP BY wahl_jahr, rat, institut)
SELECT h.wahl_jahr, h.rat, h.institut, h.nummer, h.zeitpunkt, h.partei_id,
       COALESCE(p.anzeige_de, p.kurz_de) AS name_de, COALESCE(p.anzeige_fr, p.kurz_fr) AS name_fr,
       COALESCE(p.anzeige_it, p.kurz_it) AS name_it, p.farbe, p.reihenfolge,
       h.staerke, h.staerke_fehler, h.sitze,
       COALESCE(v.partei_staerke, a.bfs_letzte_wahl_partei_staerke) AS staerke_vorwahl,
       ROUND(h.staerke - COALESCE(v.partei_staerke, a.bfs_letzte_wahl_partei_staerke), 2) AS staerke_veraenderung,
       COALESCE(v.sitze, a.bfs_letzte_wahl_sitze) AS sitze_vorwahl,
       h.sitze - COALESCE(v.sitze, a.bfs_letzte_wahl_sitze) AS sitze_veraenderung
FROM hochrechnung h
JOIN letzte l USING (wahl_jahr, rat, institut, nummer)
JOIN wahl w ON w.wahl_jahr = h.wahl_jahr
LEFT JOIN partei p ON p.partei_id = h.partei_id
LEFT JOIN nr_partei_ch v ON v.wahl_jahr = w.vorwahl_jahr AND v.partei_id = h.partei_id AND h.rat = 'NR'
-- Fallback: Vergleichswert, den das BFS mit dem laufenden Jahr liefert (falls Vorwahl nicht in der DB)
LEFT JOIN nr_partei_ch a ON a.wahl_jahr = h.wahl_jahr AND a.partei_id = h.partei_id AND h.rat = 'NR'
WHERE h.freigegeben = 1 AND h.kanton_nummer IS NULL;

-- Hochrechnungen pro Kanton (Nationalrat): neueste freigegebene Nummer pro Kanton, mit Vergleich zur Vorwahl
DROP VIEW IF EXISTS v_hochrechnung_kanton;
CREATE VIEW v_hochrechnung_kanton AS
WITH letzte AS (
  SELECT wahl_jahr, kanton_nummer, MAX(nummer) AS nummer
  FROM hochrechnung WHERE freigegeben = 1 AND rat = 'NR' AND kanton_nummer IS NOT NULL
  GROUP BY wahl_jahr, kanton_nummer)
SELECT h.wahl_jahr, h.kanton_nummer, h.institut, h.nummer, h.zeitpunkt, h.partei_id,
       h.staerke, h.staerke_fehler, h.sitze,
       COALESCE(v.partei_staerke, a.bfs_letzte_wahl_partei_staerke) AS staerke_vorwahl,
       COALESCE(v.sitze, a.bfs_letzte_wahl_sitze) AS sitze_vorwahl
FROM hochrechnung h
JOIN letzte l USING (wahl_jahr, kanton_nummer, nummer)
JOIN wahl w ON w.wahl_jahr = h.wahl_jahr
LEFT JOIN nr_partei_kanton v ON v.wahl_jahr = w.vorwahl_jahr AND v.kanton_nummer = h.kanton_nummer AND v.partei_id = h.partei_id
LEFT JOIN nr_partei_kanton a ON a.wahl_jahr = h.wahl_jahr AND a.kanton_nummer = h.kanton_nummer AND a.partei_id = h.partei_id
WHERE h.freigegeben = 1 AND h.rat = 'NR';

DROP VIEW IF EXISTS v_bauchbinde;
CREATE VIEW v_bauchbinde AS
SELECT b.grist_id AS id, b.zeile1, b.zeile2, b.kategorie, b.sprache,
       COALESCE(p.anzeige_de, p.kurz_de) AS partei, p.farbe AS partei_farbe, k.kuerzel AS kanton
FROM bauchbinde b
LEFT JOIN partei p ON p.partei_id = b.partei_id
LEFT JOIN kanton k ON k.kanton_nummer = b.kanton_nummer
WHERE b.freigegeben = 1;
