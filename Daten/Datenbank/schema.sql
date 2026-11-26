-- Wahlen-Datenbank (SQLite) für Nationalrats- und Ständeratswahlen, mehrere Wahljahre
-- Schlüssel sind die BFS-Nummern (partei_id, kanton_nummer, gemeinde_nummer, liste_nummer_bfs).
-- Jede Tabelle mit Resultaten trägt wahl_jahr. Ein Import ersetzt immer alle Zeilen eines Wahljahres.

PRAGMA foreign_keys = ON;

-- ---------- Wahljahre ----------
CREATE TABLE IF NOT EXISTS wahl (
  wahl_jahr       INTEGER PRIMARY KEY,
  vorwahl_jahr    INTEGER,            -- Vergleichswahl für Veränderungen
  wahltag         TEXT,               -- ISO-Datum
  bemerkung       TEXT
);

-- ---------- Stammdaten ----------
CREATE TABLE IF NOT EXISTS kanton (
  kanton_nummer   INTEGER PRIMARY KEY,
  kuerzel         TEXT NOT NULL,
  name_bfs        TEXT,               -- Bezeichnung laut BFS, z. B. «Bern / Berne»
  name_de         TEXT                -- redaktionell, z. B. «Bern»
);

CREATE TABLE IF NOT EXISTS partei (
  partei_id       INTEGER PRIMARY KEY,
  kurz_de TEXT, kurz_fr TEXT, kurz_it TEXT, kurz_en TEXT,
  name_de TEXT, name_fr TEXT, name_it TEXT, name_en TEXT,
  parteigruppen_id INTEGER, gruppe_kurz_de TEXT, gruppe_kurz_fr TEXT, gruppe_kurz_it TEXT,
  lager_id        INTEGER, lager_kurz_de TEXT, lager_kurz_fr TEXT, lager_kurz_it TEXT,
  -- redaktionelle Felder (werden beim Import nie überschrieben, kommen aus Grist):
  anzeige_de TEXT, anzeige_fr TEXT, anzeige_it TEXT,   -- Name in Grafiken, leer = BFS-Kurzname
  farbe           TEXT,
  reihenfolge     INTEGER,
  links_rechts    INTEGER
);

CREATE TABLE IF NOT EXISTS kandidat_status (
  kandidat_status_id INTEGER PRIMARY KEY,
  text_de TEXT, text_fr TEXT, text_it TEXT, text_en TEXT
);

-- Gemeinden ändern sich (Fusionen), deshalb pro Wahljahr
CREATE TABLE IF NOT EXISTS gemeinde (
  wahl_jahr       INTEGER NOT NULL,
  gemeinde_nummer INTEGER NOT NULL,
  name            TEXT,
  kanton_nummer   INTEGER NOT NULL,
  PRIMARY KEY (wahl_jahr, gemeinde_nummer)
);

-- Soll-Sitze pro Kanton und Wahljahr (Verordnung des Bundesrats)
CREATE TABLE IF NOT EXISTS kanton_sitze (
  wahl_jahr       INTEGER NOT NULL,
  kanton_nummer   INTEGER NOT NULL,
  nr_sitze        INTEGER NOT NULL,
  sr_sitze        INTEGER,
  quelle          TEXT,
  geprueft        INTEGER DEFAULT 0,   -- 1 = gegen amtliche Quelle geprüft
  PRIMARY KEY (wahl_jahr, kanton_nummer)
);

-- ---------- Nationalrat: Stand ----------
CREATE TABLE IF NOT EXISTS nr_stand (
  wahl_jahr       INTEGER PRIMARY KEY,
  timestamp       TEXT,
  importiert_um   TEXT,
  wahl_abgeschlossen INTEGER,
  kantone_total INTEGER, kantone_abgeschlossen INTEGER,
  gemeinden_total INTEGER, gemeinden_abgeschlossen INTEGER
);

CREATE TABLE IF NOT EXISTS nr_stand_kanton (
  wahl_jahr       INTEGER NOT NULL,
  kanton_nummer   INTEGER NOT NULL,
  kanton_abgeschlossen INTEGER,
  gemeinden_total INTEGER, gemeinden_abgeschlossen INTEGER,
  PRIMARY KEY (wahl_jahr, kanton_nummer)
);

-- ---------- Nationalrat: Listen und Kandidierende ----------
CREATE TABLE IF NOT EXISTS nr_liste (
  wahl_jahr       INTEGER NOT NULL,
  kanton_nummer   INTEGER NOT NULL,
  liste_nummer_bfs INTEGER NOT NULL,
  liste_nummer_kanton TEXT,
  liste_bezeichnung TEXT,
  liste_verbindung TEXT,
  liste_unterlistenverbindung TEXT,
  partei_id       INTEGER,
  anzahl_gewaehlte INTEGER,
  stimmen_liste   INTEGER,
  listen_staerke  REAL,
  PRIMARY KEY (wahl_jahr, kanton_nummer, liste_nummer_bfs)
);

CREATE TABLE IF NOT EXISTS nr_kandidat (
  wahl_jahr       INTEGER NOT NULL,
  kanton_nummer   INTEGER NOT NULL,
  liste_nummer_bfs INTEGER NOT NULL,
  kandidat_nummer INTEGER NOT NULL,
  liste_nummer_kanton TEXT,
  kandidat_listenplatz_1 INTEGER, kandidat_listenplatz_2 INTEGER,
  name TEXT, vorname TEXT, geschlecht TEXT,
  geburtsdatum TEXT, geburtsjahr INTEGER,
  wohnort_gemeinde_nummer INTEGER, wohnort TEXT, beruf TEXT,
  kandidat_status_id INTEGER,
  partei_id       INTEGER,
  stimmen         INTEGER,
  gewaehlt        INTEGER,
  PRIMARY KEY (wahl_jahr, kanton_nummer, liste_nummer_bfs, kandidat_nummer)
);

CREATE TABLE IF NOT EXISTS nr_kandidat_gemeinde (
  wahl_jahr       INTEGER NOT NULL,
  gemeinde_nummer INTEGER NOT NULL,
  kanton_nummer   INTEGER NOT NULL,
  liste_nummer_bfs INTEGER NOT NULL,
  kandidat_nummer INTEGER NOT NULL,
  stimmen         INTEGER,
  PRIMARY KEY (wahl_jahr, gemeinde_nummer, liste_nummer_bfs, kandidat_nummer)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS nr_liste_gemeinde (
  wahl_jahr       INTEGER NOT NULL,
  gemeinde_nummer INTEGER NOT NULL,
  kanton_nummer   INTEGER NOT NULL,
  liste_nummer_bfs INTEGER NOT NULL,
  partei_id       INTEGER,
  stimmen_liste   INTEGER,
  PRIMARY KEY (wahl_jahr, gemeinde_nummer, liste_nummer_bfs)
) WITHOUT ROWID;

-- ---------- Nationalrat: Parteien ----------
CREATE TABLE IF NOT EXISTS nr_partei_ch (
  wahl_jahr       INTEGER NOT NULL,
  partei_id       INTEGER NOT NULL,
  anzahl_listen INTEGER, anzahl_kandidierende INTEGER, anzahl_kandidierende_f INTEGER, anzahl_kandidierende_m INTEGER,
  sitze INTEGER, sitze_f INTEGER, sitze_m INTEGER,
  fiktive_waehlende REAL,
  partei_staerke  REAL,
  partei_rang     INTEGER,
  staerkste_partei INTEGER,
  -- vom BFS mitgelieferte Vergleichswerte (Vorwahl):
  bfs_letzte_wahl_sitze INTEGER, bfs_letzte_wahl_partei_staerke REAL,
  PRIMARY KEY (wahl_jahr, partei_id)
);

CREATE TABLE IF NOT EXISTS nr_partei_kanton (
  wahl_jahr       INTEGER NOT NULL,
  kanton_nummer   INTEGER NOT NULL,
  partei_id       INTEGER NOT NULL,
  anzahl_listen INTEGER, anzahl_kandidierende INTEGER, anzahl_kandidierende_f INTEGER, anzahl_kandidierende_m INTEGER,
  sitze INTEGER, sitze_f INTEGER, sitze_m INTEGER,
  fiktive_waehlende REAL,
  stimmen         INTEGER,
  partei_staerke  REAL,
  partei_rang     INTEGER,
  staerkste_partei INTEGER,
  bfs_letzte_wahl_sitze INTEGER, bfs_letzte_wahl_partei_staerke REAL,
  PRIMARY KEY (wahl_jahr, kanton_nummer, partei_id)
);

CREATE TABLE IF NOT EXISTS nr_partei_gemeinde (
  wahl_jahr       INTEGER NOT NULL,
  gemeinde_nummer INTEGER NOT NULL,
  kanton_nummer   INTEGER NOT NULL,
  partei_id       INTEGER NOT NULL,
  stimmen         INTEGER,
  partei_staerke  REAL,
  partei_rang     INTEGER,
  staerkste_partei INTEGER,
  bfs_letzte_wahl_partei_staerke REAL,
  PRIMARY KEY (wahl_jahr, gemeinde_nummer, partei_id)
) WITHOUT ROWID;

-- ---------- Nationalrat: Wahlbeteiligung ----------
CREATE TABLE IF NOT EXISTS nr_beteiligung (
  wahl_jahr       INTEGER NOT NULL,
  ebene           TEXT NOT NULL,       -- 'CH', 'kanton', 'gemeinde'
  nummer          INTEGER NOT NULL,    -- 0 für CH, sonst Kantons- bzw. Gemeindenummer
  kanton_nummer   INTEGER,
  wahlberechtigte INTEGER, eingelegte_wahlzettel INTEGER, leere_wahlzettel INTEGER,
  ungueltige_wahlzettel INTEGER, gueltige_wahlzettel INTEGER,
  wahlbeteiligung REAL,
  bfs_letzte_wahl_wahlbeteiligung REAL,
  PRIMARY KEY (wahl_jahr, ebene, nummer)
);

-- ---------- Nationalrat: Zeitreihen ab 1991 ----------
CREATE TABLE IF NOT EXISTS nr_zeitreihe_partei (
  wahl_jahr INTEGER NOT NULL, kanton_nummer INTEGER NOT NULL,  -- 0 = CH
  partei_id INTEGER NOT NULL,
  anzahl_listen INTEGER, anzahl_kandidierende INTEGER, partei_staerke REAL,
  sitze INTEGER, sitze_f INTEGER, sitze_m INTEGER, frauen_anteil REAL, staerkste_partei INTEGER,
  PRIMARY KEY (wahl_jahr, kanton_nummer, partei_id)
);

CREATE TABLE IF NOT EXISTS nr_zeitreihe_beteiligung (
  wahl_jahr INTEGER NOT NULL, kanton_nummer INTEGER NOT NULL,  -- 0 = CH
  wahlbeteiligung REAL, frauen_anteil REAL, anzahl_listen INTEGER, anzahl_kandidierende INTEGER,
  anzahl_kandidierende_f INTEGER, sitze INTEGER, sitze_f INTEGER,
  PRIMARY KEY (wahl_jahr, kanton_nummer)
);

-- ---------- Ständerat ----------
CREATE TABLE IF NOT EXISTS sr_stand_kanton (
  wahl_jahr       INTEGER NOT NULL,
  wahlgang        INTEGER NOT NULL,
  kanton_nummer   INTEGER NOT NULL,
  wahlgang_datum  TEXT,
  stille_wahl     INTEGER,
  zweiter_wahlgang_noetig INTEGER,
  wahlgang_abgeschlossen INTEGER,
  PRIMARY KEY (wahl_jahr, wahlgang, kanton_nummer)
);

CREATE TABLE IF NOT EXISTS sr_kandidat (
  wahl_jahr       INTEGER NOT NULL,
  wahlgang        INTEGER NOT NULL,
  kanton_nummer   INTEGER NOT NULL,
  laufnummer      INTEGER NOT NULL,    -- BFS liefert keine Kandidatennummer
  name TEXT, vorname TEXT, geschlecht TEXT, geburtsdatum TEXT, geburtsjahr INTEGER,
  kandidat_status_id INTEGER,
  partei_id       INTEGER,
  stimmen         INTEGER,
  gewaehlt        INTEGER,
  vereinzelte     INTEGER,             -- 1 = Sammelzeile «Vereinzelte»
  PRIMARY KEY (wahl_jahr, wahlgang, kanton_nummer, laufnummer)
);

-- Redaktionelle Korrekturen, die die BFS-Daten nicht kennen (z. B. Nachwahl SH 2025)
CREATE TABLE IF NOT EXISTS sr_korrektur (
  wahl_jahr       INTEGER NOT NULL,
  kanton_nummer   INTEGER NOT NULL,
  name TEXT NOT NULL, vorname TEXT NOT NULL,
  partei_id       INTEGER,
  gewaehlt        INTEGER NOT NULL,     -- 1 = gilt als gewählt, 0 = gilt nicht (mehr) als gewählt
  gueltig_ab      TEXT,
  grund           TEXT,
  PRIMARY KEY (wahl_jahr, kanton_nummer, name, vorname)
);

-- ---------- Redaktionelle Daten aus Grist (vom Abgleich-Skript gepflegt) ----------
CREATE TABLE IF NOT EXISTS hochrechnung (
  grist_id        INTEGER PRIMARY KEY,   -- Zeilen-ID in Grist
  wahl_jahr       INTEGER NOT NULL,
  rat             TEXT NOT NULL,         -- 'NR' oder 'SR'
  kanton_nummer   INTEGER,               -- leer/0 = Schweiz, sonst Kanton (BFS-Nr.)
  institut        TEXT,
  nummer          INTEGER,               -- 1., 2., 3. Hochrechnung
  zeitpunkt       TEXT,                  -- ISO-Zeit
  partei_id       INTEGER,
  staerke         REAL,                  -- Wähleranteil in %
  staerke_fehler  REAL,                  -- ± Prozentpunkte
  sitze           INTEGER,
  freigegeben     INTEGER DEFAULT 0      -- nur freigegebene Zeilen gehen in Grafiken
);

-- Hochrechnung der Wahlbeteiligung Schweiz (aus Grist «Hochrechnung_Beteiligung»)
CREATE TABLE IF NOT EXISTS hochrechnung_beteiligung (
  grist_id        INTEGER PRIMARY KEY,
  wahl_jahr       INTEGER NOT NULL,
  institut        TEXT,
  nummer          INTEGER,
  zeitpunkt       TEXT,
  beteiligung     REAL,                  -- in %
  fehler          REAL,                  -- ± Prozentpunkte
  freigegeben     INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bauchbinde (
  grist_id        INTEGER PRIMARY KEY,
  zeile1          TEXT,
  zeile2          TEXT,
  kategorie       TEXT,                  -- z. B. Gast, Politik, Moderation, Ort
  sprache         TEXT DEFAULT 'de',
  partei_id       INTEGER,
  kanton_nummer   INTEGER,
  freigegeben     INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sync_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  zeit TEXT, richtung TEXT, tabelle TEXT, zeilen INTEGER, meldung TEXT
);

-- ---------- Import-Protokoll ----------
CREATE TABLE IF NOT EXISTS import_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  importiert_um TEXT, wahl_jahr INTEGER, datei TEXT, bfs_timestamp TEXT, zeilen INTEGER
);

-- Indizes für die Abfragen der Grafiken
CREATE INDEX IF NOT EXISTS ix_kand_gewaehlt ON nr_kandidat(wahl_jahr, gewaehlt);
CREATE INDEX IF NOT EXISTS ix_kand_person ON nr_kandidat(name, vorname, geburtsjahr);
CREATE INDEX IF NOT EXISTS ix_kg_kandidat ON nr_kandidat_gemeinde(wahl_jahr, kanton_nummer, liste_nummer_bfs, kandidat_nummer);
CREATE INDEX IF NOT EXISTS ix_pg_partei ON nr_partei_gemeinde(wahl_jahr, partei_id);

-- ---------- Historie (Recherche für die Moderation, geladen mit historie_laden.py) ----------
-- Ratsmitglieder seit 1848, eine Zeile pro Amtszeit (Quelle: Parlamentsdienste, ws.parlament.ch, MemberCouncilHistory)
CREATE TABLE IF NOT EXISTS hist_mitglied (
  id          TEXT PRIMARY KEY,
  person_nr   INTEGER,
  vorname     TEXT, nachname TEXT,
  geschlecht  TEXT,               -- 'f' / 'm'
  kanton      TEXT,               -- Kürzel, z. B. 'LU'
  rat         TEXT,               -- 'NR' / 'SR' (andere Werte möglich, z. B. Bundesrat)
  partei      TEXT,               -- Kürzel laut Parlament, z. B. 'BGB', 'CVP', 'M-E'
  partei_name TEXT,
  fraktion    TEXT,
  eintritt    TEXT, austritt TEXT, -- ISO-Datum, austritt leer = im Amt
  geburt      TEXT, tod TEXT
);
CREATE INDEX IF NOT EXISTS hist_mitglied_suche ON hist_mitglied (rat, kanton, geschlecht);

-- Parteistärke Nationalrat seit 1971 (Quelle: BFS px-x-1702020000_104), kanton_nummer 0 = Schweiz
CREATE TABLE IF NOT EXISTS hist_partei_staerke (
  wahl_jahr     INTEGER NOT NULL,
  kanton_nummer INTEGER NOT NULL,
  partei        TEXT NOT NULL,     -- Bezeichnung laut BFS, z. B. 'FDP', 'CVP', 'GPS'
  staerke       REAL,
  PRIMARY KEY (wahl_jahr, kanton_nummer, partei)
);

-- Welche Kürzel zur selben Parteifamilie gehören (z. B. BGB → SVP, CVP/BDP → Mitte); aus parteifamilie.csv
CREATE TABLE IF NOT EXISTS partei_familie (
  schluessel TEXT PRIMARY KEY,     -- Kürzel normalisiert: klein, ohne Leerzeichen und Punkte
  kuerzel    TEXT,
  familie    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hist_quelle (
  quelle TEXT PRIMARY KEY, geladen_um TEXT, zeilen INTEGER, hinweis TEXT
);
